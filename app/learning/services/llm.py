import os
import json
import re
import time
import logging
import requests
from groq import Groq
from pydantic import BaseModel
from dotenv import load_dotenv

# Ensure environment variables are loaded
load_dotenv()

logger = logging.getLogger(__name__)

# =====================================================================
# 1. API CLIENT & ENVIRONMENT INITIALIZATION
# =====================================================================

groq_api_key = os.environ.get("GROQ_API_KEY", "").strip("\"' \t\n\r")
gemini_api_key = os.environ.get("GEMINI_API_KEY", "").strip("\"' \t\n\r")

groq_client = None
if groq_api_key:
    try:
        groq_client = Groq(api_key=groq_api_key, max_retries=1)
        logger.info("Groq client initialized successfully.")
    except Exception as e:
        logger.warning("Failed to initialize Groq client: %s", e)

# =====================================================================
# 2. MODEL POOLS (Cascading Fallback Order)
# =====================================================================

GROQ_MODELS = [
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "qwen/qwen3.6-27b",
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
]

GEMINI_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-1.5-flash-latest",
]

class LLMGenerationError(Exception):
    """Raised when all configured LLM providers fail."""
    pass

# =====================================================================
# 3. JSON CLEANING & SCHEMA PARSING HELPERS
# =====================================================================

def _clean_model_json(raw: str) -> str:
    """Clean markdown code fences, thinking tags, and extraneous wrapping."""
    if not raw:
        raise ValueError("LLM returned an empty response.")

    cleaned = raw.strip()

    # Strip thinking/reasoning tags
    cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL | re.IGNORECASE)

    # Strip markdown code fences
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    cleaned = re.sub(r"```(?:json)?", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"```", "", cleaned)

    return cleaned.strip()


def _parse_schema_response(
    raw: str,
    schema: type[BaseModel],
    provider: str,
) -> BaseModel:
    """Parse raw LLM output into a Pydantic schema using multiple fallback strategies."""
    cleaned = _clean_model_json(raw)

    # Attempt 1: Direct Pydantic JSON validation
    try:
        return schema.model_validate_json(cleaned)
    except Exception:
        pass

    # Attempt 2: Extract first JSON object/array substring
    start_index = cleaned.find("{")
    if start_index != -1:
        try:
            decoder = json.JSONDecoder(strict=False)
            obj, _ = decoder.raw_decode(cleaned[start_index:])
            return schema.model_validate(obj)
        except Exception:
            pass

    # Attempt 3: Standard json.loads fallback
    try:
        parsed = json.loads(cleaned)
        return schema.model_validate(parsed)
    except Exception as e:
        raise ValueError(
            f"{provider} returned invalid JSON for {schema.__name__}: {cleaned[:1000]}"
        ) from e


# =====================================================================
# 4. STRUCTURED CALLS (Groq & Gemini REST)
# =====================================================================

def _call_groq_json(
    prompt: str,
    schema: type[BaseModel],
    model: str,
    max_tokens: int = 4096,
) -> BaseModel:
    if not groq_client:
        raise ValueError("Groq client is not initialized.")

    schema_json = schema.model_json_schema()
    schema_instruction = (
        "\n\nSTRICT OUTPUT REQUIREMENTS:\n"
        "1. Return ONLY a single raw valid JSON object matching the schema below.\n"
        "2. Do NOT enclose the output in markdown code blocks or backticks.\n"
        "3. Do NOT include any conversational intro or conclusion.\n"
        f"JSON Schema: {json.dumps(schema_json, ensure_ascii=False)}"
    )

    call_kwargs = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "You are a JSON-only API. You return strictly valid JSON matching the exact schema requested.",
            },
            {"role": "user", "content": prompt + schema_instruction},
        ],
        "temperature": 0.2,
        "max_tokens": min(max_tokens, 4096),
    }

    if "qwen" in model.lower():
        call_kwargs["reasoning_effort"] = "none"
    else:
        call_kwargs["response_format"] = {"type": "json_object"}

    completion = groq_client.chat.completions.create(**call_kwargs)
    raw = completion.choices[0].message.content or ""
    return _parse_schema_response(raw, schema, f"Groq ({model})")


def _call_gemini_json(
    prompt: str,
    schema: type[BaseModel],
    model: str,
    max_tokens: int = 4096,
) -> BaseModel:
    if not gemini_api_key:
        raise ValueError("GEMINI_API_KEY is not configured.")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    headers = {
        "x-goog-api-key": gemini_api_key,
        "Content-Type": "application/json",
    }

    schema_json = schema.model_json_schema()
    schema_instruction = (
        "\n\nSTRICT OUTPUT REQUIREMENTS:\n"
        "1. Return ONLY valid JSON matching this schema.\n"
        "2. Do NOT use markdown code blocks.\n"
        f"Schema: {json.dumps(schema_json, ensure_ascii=False)}"
    )

    payload = {
        "contents": [{"parts": [{"text": prompt + schema_instruction}]}],
        "generationConfig": {
            "maxOutputTokens": max_tokens,
            "responseMimeType": "application/json",
            "temperature": 0.2,
        },
    }

    response = requests.post(url, headers=headers, json=payload, timeout=45)
    if response.status_code != 200:
        raise RuntimeError(f"Gemini API Error {response.status_code}: {response.text[:500]}")

    data = response.json()
    candidates = data.get("candidates", [])
    if not candidates:
        raise RuntimeError(f"Gemini returned no candidates: {data}")

    parts = candidates[0].get("content", {}).get("parts", [])
    if not parts:
        raise RuntimeError(f"Gemini returned no content parts: {data}")

    text = parts[0].get("text")
    if not text:
        raise RuntimeError("Gemini returned empty text.")

    return _parse_schema_response(text, schema, f"Gemini ({model})")


# =====================================================================
# 5. DISPATCHERS (Structured & Conversational)
# =====================================================================

def call_llm(
    prompt: str,
    schema: type[BaseModel],
    model_type: str = "thinking",
    retries: int = 2,
    max_tokens: int = 4096,
) -> BaseModel:
    """
    Intelligent Dual-Engine Structured Dispatch:
    Tries configured providers with an active model cascade pool.
    """
    del retries
    errors = []

    providers = []
    if groq_client:
        providers.append(("groq", GROQ_MODELS))
    if gemini_api_key:
        providers.append(("gemini", GEMINI_MODELS))

    for provider, model_list in providers:
        for model_name in model_list:
            try:
                if provider == "groq":
                    return _call_groq_json(prompt, schema, model=model_name, max_tokens=max_tokens)
                elif provider == "gemini":
                    return _call_gemini_json(prompt, schema, model=model_name, max_tokens=max_tokens)
            except Exception as e:
                errors.append(f"{provider.capitalize()} {model_name}: {e}")
                logger.warning("LLM model %s (%s) failed: %s. Trying next in pool...", model_name, provider, e)
                time.sleep(0.3)
                continue

    error_summary = " | ".join(errors) if errors else "No LLM provider is configured."
    raise LLMGenerationError(f"LLM generation failed across providers: {error_summary}")


def _call_groq_text(prompt: str, model: str, max_tokens: int = 2048) -> str:
    if not groq_client:
        raise ValueError("Groq client is not initialized.")
    call_kwargs = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.4,
        "max_tokens": max_tokens,
    }
    if "qwen" in model.lower():
        call_kwargs["reasoning_effort"] = "none"
    completion = groq_client.chat.completions.create(**call_kwargs)
    raw = completion.choices[0].message.content or ""
    return re.sub(r"<think>.*?", "", raw, flags=re.DOTALL).strip()


def _call_gemini_text(prompt: str, model: str, max_tokens: int = 2048) -> str:
    if not gemini_api_key:
        raise ValueError("GEMINI_API_KEY is not configured.")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    headers = {
        "x-goog-api-key": gemini_api_key,
        "Content-Type": "application/json",
    }
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "maxOutputTokens": max_tokens,
            "temperature": 0.4,
        },
    }
    response = requests.post(url, headers=headers, json=payload, timeout=45)
    if response.status_code != 200:
        raise RuntimeError(f"Gemini API Error {response.status_code}: {response.text[:500]}")
    data = response.json()
    candidates = data.get("candidates", [])
    if not candidates:
        raise RuntimeError("Gemini returned no candidates.")
    parts = candidates[0].get("content", {}).get("parts", [])
    if not parts:
        raise RuntimeError("Gemini returned no content parts.")
    return (parts[0].get("text") or "").strip()


def call_llm_text(prompt: str, model_type: str = "fast", retries: int = 1) -> str:
    """
    Intelligent Dual-Engine Text Dispatch:
    Cascades through available Groq and Gemini models.
    """
    del retries
    errors = []

    providers = []
    if groq_client:
        providers.append(("groq", GROQ_MODELS))
    if gemini_api_key:
        providers.append(("gemini", GEMINI_MODELS))

    for provider, model_list in providers:
        for model_name in model_list:
            try:
                if provider == "groq":
                    return _call_groq_text(prompt, model=model_name)
                elif provider == "gemini":
                    return _call_gemini_text(prompt, model=model_name)
            except Exception as e:
                errors.append(f"{provider.capitalize()} {model_name}: {e}")
                time.sleep(0.3)
                continue

    error_summary = " | ".join(errors) if errors else "No LLM provider is configured."
    raise LLMGenerationError(f"LLM text generation failed: {error_summary}")

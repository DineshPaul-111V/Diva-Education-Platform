import os
import json
import re
import logging

import requests
from groq import Groq
from pydantic import BaseModel
from dotenv import load_dotenv


# ============================================================
# 1. ENVIRONMENT & LOGGING
# ============================================================

load_dotenv()
logger = logging.getLogger(__name__)


# ============================================================
# 2. API KEYS
# ============================================================

groq_api_key = os.environ.get("GROQ_API_KEY", "").strip("\"' \t\n\r")
gemini_api_key = os.environ.get("GEMINI_API_KEY", "").strip("\"' \t\n\r")


# ============================================================
# 3. CLIENT INITIALIZATION
# ============================================================

groq_client = None

if groq_api_key:
    try:
        groq_client = Groq(
            api_key=groq_api_key,
            max_retries=0,
        )
        logger.info("Groq client initialized successfully.")
    except Exception as e:
        logger.exception("Failed to initialize Groq client: %s", e)
else:
    logger.warning("GROQ_API_KEY is not configured.")

if gemini_api_key:
    logger.info("Gemini API key detected.")
else:
    logger.warning("GEMINI_API_KEY is not configured.")

if not groq_client and not gemini_api_key:
    logger.critical("Neither GROQ_API_KEY nor GEMINI_API_KEY is configured.")


# ============================================================
# 4. MODEL CONFIGURATION
# ============================================================

GEMINI_MODEL = "gemini-2.0-flash"
GROQ_MODEL = "llama-3.1-70b-versatile"


# ============================================================
# 5. CUSTOM ERROR
# ============================================================

class LLMGenerationError(Exception):
    """Raised when all configured LLM providers fail."""
    pass


# ============================================================
# 6. JSON CLEANING HELPERS
# ============================================================

def _clean_model_json(raw: str) -> str:
    """Clean common Markdown code fences and thinking tags from raw JSON strings."""
    if not raw:
        raise ValueError("LLM returned an empty response.")

    cleaned = raw.strip()
    cleaned = re.sub(r"<think>.*?</think>", "", cleaned, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r"```(?:json)?", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"```", "", cleaned)

    return cleaned.strip()


def _parse_schema_response(
    raw: str,
    schema: type[BaseModel],
    provider: str,
) -> BaseModel:
    cleaned = _clean_model_json(raw)

    try:
        return schema.model_validate_json(cleaned)
    except Exception:
        pass

    start_index = cleaned.find("{")
    if start_index != -1:
        try:
            decoder = json.JSONDecoder(strict=False)
            obj, _ = decoder.raw_decode(cleaned[start_index:])
            return schema.model_validate(obj)
        except Exception:
            pass

    try:
        parsed = json.loads(cleaned)
        return schema.model_validate(parsed)
    except Exception as e:
        raise ValueError(
            f"{provider} returned invalid JSON for {schema.__name__}: {cleaned[:1500]}"
        ) from e


# ============================================================
# 7. GEMINI REST API
# ============================================================

def _call_gemini_rest(
    prompt: str,
    model: str = GEMINI_MODEL,
    max_tokens: int = 4096,
    json_mode: bool = True,
) -> str:
    if not gemini_api_key:
        raise ValueError("GEMINI_API_KEY is not configured.")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    headers = {
        "x-goog-api-key": gemini_api_key,
        "Content-Type": "application/json",
    }

    generation_config = {"maxOutputTokens": max_tokens}
    if json_mode:
        generation_config["responseMimeType"] = "application/json"

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": generation_config,
    }

    logger.info("Calling Gemini model: %s", model)

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=45)
    except requests.RequestException as e:
        raise RuntimeError(f"Gemini network error: {e}") from e

    if response.status_code != 200:
        raise RuntimeError(f"Gemini API Error {response.status_code}: {response.text}")

    try:
        data = response.json()
    except Exception as e:
        raise RuntimeError("Gemini returned non-JSON HTTP response.") from e

    candidates = data.get("candidates", [])
    if not candidates:
        raise RuntimeError(f"Gemini returned no candidates: {data}")

    parts = candidates[0].get("content", {}).get("parts", [])
    if not parts:
        raise RuntimeError(f"Gemini returned no content parts: {data}")

    text = parts[0].get("text")
    if not text:
        raise RuntimeError(f"Gemini returned empty text: {data}")

    return text


def _call_gemini_json(
    prompt: str,
    schema: type[BaseModel],
    model: str = GEMINI_MODEL,
    max_tokens: int = 4096,
) -> BaseModel:
    schema_json = schema.model_json_schema()
    schema_instruction = (
        "\n\nSTRICT OUTPUT REQUIREMENTS:\n"
        "1. Return valid JSON only matching this schema.\n"
        "2. Do NOT use markdown code blocks.\n"
        f"Schema: {json.dumps(schema_json, ensure_ascii=False)}"
    )

    raw = _call_gemini_rest(
        prompt + schema_instruction,
        model=model,
        max_tokens=max_tokens,
        json_mode=True,
    )

    return _parse_schema_response(raw, schema, "Gemini")


# ============================================================
# 8. GROQ STRUCTURED JSON
# ============================================================

def _call_groq_json(
    prompt: str,
    schema: type[BaseModel],
    model: str = GROQ_MODEL,
    max_tokens: int = 4096,
) -> BaseModel:
    if not groq_client:
        raise ValueError("Groq client is not initialized.")

    schema_json = schema.model_json_schema()
    schema_instruction = (
        "\n\nSTRICT OUTPUT REQUIREMENTS:\n"
        "1. Return exactly ONE valid JSON object matching the target schema.\n"
        "2. Ensure all array items are properly structured JSON objects with valid keys.\n"
        "3. Do NOT wrap output in backticks or markdown fences.\n"
        f"Schema: {json.dumps(schema_json, ensure_ascii=False)}"
    )

    messages = [
        {
            "role": "system",
            "content": "You are a JSON-only API. You output raw valid JSON matching the exact provided schema without markdown formatting.",
        },
        {"role": "user", "content": prompt + schema_instruction},
    ]

    logger.info("Calling Groq model: %s", model)

    try:
        completion = groq_client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.1,
            max_tokens=max_tokens,
        )
    except Exception as e:
        raise RuntimeError(f"Groq request failed: {e}") from e

    if not completion.choices:
        raise RuntimeError("Groq returned no choices.")

    raw = completion.choices[0].message.content or ""
    if not raw.strip():
        raise RuntimeError("Groq returned an empty response.")

    return _parse_schema_response(raw, schema, "Groq")


# ============================================================
# 9. DISPATCHERS
# ============================================================

def call_llm(
    prompt: str,
    schema: type[BaseModel],
    model_type: str = "thinking",
    retries: int = 1,
    max_tokens: int = 4096,
) -> BaseModel:
    del retries
    errors = []

    if model_type == "fast":
        if groq_client:
            try:
                return _call_groq_json(prompt, schema, model=GROQ_MODEL, max_tokens=max_tokens)
            except Exception as e:
                errors.append(f"Groq {GROQ_MODEL}: {e}")
                logger.exception("Groq generation failed.")

        if gemini_api_key:
            try:
                return _call_gemini_json(prompt, schema, model=GEMINI_MODEL, max_tokens=max_tokens)
            except Exception as e:
                errors.append(f"Gemini {GEMINI_MODEL}: {e}")
                logger.exception("Gemini fallback failed.")
    else:
        if gemini_api_key:
            try:
                return _call_gemini_json(prompt, schema, model=GEMINI_MODEL, max_tokens=max_tokens)
            except Exception as e:
                errors.append(f"Gemini {GEMINI_MODEL}: {e}")
                logger.exception("Gemini generation failed.")

        if groq_client:
            try:
                return _call_groq_json(prompt, schema, model=GROQ_MODEL, max_tokens=max_tokens)
            except Exception as e:
                errors.append(f"Groq {GROQ_MODEL}: {e}")
                logger.exception("Groq fallback failed.")

    error_message = " | ".join(errors) if errors else "No LLM provider is configured."
    raise LLMGenerationError("LLM generation failed across providers: " + error_message)


def _call_groq_text(prompt: str, model: str = GROQ_MODEL, max_tokens: int = 2000) -> str:
    if not groq_client:
        raise ValueError("Groq client is not initialized.")
    completion = groq_client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.4,
        max_tokens=max_tokens,
    )
    raw = completion.choices[0].message.content or ""
    return re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()


def _call_gemini_text(prompt: str, model: str = GEMINI_MODEL, max_tokens: int = 2000) -> str:
    raw = _call_gemini_rest(prompt=prompt, model=model, max_tokens=max_tokens, json_mode=False)
    return (raw or "").strip()


def call_llm_text(prompt: str, model_type: str = "fast", retries: int = 1) -> str:
    del retries
    errors = []

    if model_type == "fast":
        if groq_client:
            try:
                return _call_groq_text(prompt, model=GROQ_MODEL)
            except Exception as e:
                errors.append(f"Groq {GROQ_MODEL}: {e}")
        if gemini_api_key:
            try:
                return _call_gemini_text(prompt, model=GEMINI_MODEL)
            except Exception as e:
                errors.append(f"Gemini {GEMINI_MODEL}: {e}")
    else:
        if gemini_api_key:
            try:
                return _call_gemini_text(prompt, model=GEMINI_MODEL)
            except Exception as e:
                errors.append(f"Gemini {GEMINI_MODEL}: {e}")
        if groq_client:
            try:
                return _call_groq_text(prompt, model=GROQ_MODEL)
            except Exception as e:
                errors.append(f"Groq {GROQ_MODEL}: {e}")

    error_message = " | ".join(errors) if errors else "No LLM provider is configured."
    raise LLMGenerationError("LLM text generation failed: " + error_message)

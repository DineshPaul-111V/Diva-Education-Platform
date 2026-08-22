import os
import json
import re
import time
import logging
import requests
from groq import Groq
from pydantic import BaseModel
from dotenv import load_dotenv

from app.config import Config
from app.learning.services.key_manager import KeyPool
from app.learning.services.cache import get_cached_response, set_cached_response
from app.learning.services.fallback_manager import FallbackStateManager

# Ensure environment variables are loaded
load_dotenv()

logger = logging.getLogger(__name__)

# =====================================================================
# 1. API CLIENT & ENVIRONMENT INITIALIZATION
# =====================================================================

# Initialize Key Pools
groq_pool = KeyPool("Groq", Config.GROQ_API_KEYS)
gemini_pool = KeyPool("Gemini", Config.GEMINI_API_KEYS)
hf_pool = KeyPool("HuggingFace", Config.HF_TOKENS)


# =====================================================================
# 2. MODEL POOLS (Cascading Fallback Order)
# =====================================================================

GEMINI_MODELS = [
    "gemini-2.5-flash",       # confirmed working, cheap, fast
    "gemini-3.5-flash-lite",  # cheapest of the 3.x family
    "gemini-3.6-flash",
    "gemini-3.7-flash",       # most capable, use last/only if needed
]

GROQ_MODELS = [
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "gemma2-9b-it",
]

HF_MODELS = [
    "meta-llama/Meta-Llama-3-8B-Instruct",
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
    api_key: str,
    max_tokens: int = 4096,
) -> BaseModel:
    if not api_key:
        raise ValueError("Groq API key is missing.")
    
    groq_client = Groq(api_key=api_key, max_retries=0, timeout=15.0)

    schema_json = schema.model_json_schema()
    schema_instruction = (
        "\n\nSTRICT OUTPUT REQUIREMENTS:\n"
        "1. Return ONLY a single raw valid JSON object matching the schema below.\n"
        "2. Do NOT enclose the output in markdown code blocks or backticks.\n"
        "3. Do NOT include any conversational intro or conclusion.\n"
        "4. CRITICAL: Preserve all indentation spaces in code blocks. Escape newlines properly as \\n.\n"
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
    elif "gpt-oss-20b" not in model.lower():
        call_kwargs["response_format"] = {"type": "json_object"}

    try:
        completion = groq_client.chat.completions.create(**call_kwargs)
    except Exception as e:
        err_str = str(e)
        # If response_format caused 400 json_validate_failed, retry without response_format
        if "response_format" in call_kwargs and "json_validate_failed" in err_str:
            call_kwargs.pop("response_format", None)
            completion = groq_client.chat.completions.create(**call_kwargs)
        else:
            raise e

    raw = completion.choices[0].message.content or ""
    return _parse_schema_response(raw, schema, f"Groq ({model})")


def _call_gemini_json(
    prompt: str,
    schema: type[BaseModel],
    model: str,
    api_key: str,
    max_tokens: int = 4096,
) -> BaseModel:
    if not api_key:
        raise ValueError("Gemini API key is missing.")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    headers = {
        "x-goog-api-key": api_key,
        "Content-Type": "application/json",
    }

    schema_json = schema.model_json_schema()
    schema_instruction = (
        "\n\nSTRICT OUTPUT REQUIREMENTS:\n"
        "1. Return ONLY valid JSON matching this schema.\n"
        "2. Do NOT use markdown code blocks.\n"
        "3. CRITICAL: Preserve all indentation spaces in code blocks. Escape newlines properly as \\n.\n"
        f"Schema: {json.dumps(schema_json, ensure_ascii=False)}"
    )

    payload = {
        "contents": [{"parts": [{"text": prompt + schema_instruction}]}],
        "generationConfig": {
            "maxOutputTokens": max_tokens,
            "temperature": 0.2,
            "responseMimeType": "application/json",
        },
    }

    response = requests.post(url, headers=headers, json=payload, timeout=20.0)
    if response.status_code == 401:
        raise RuntimeError("Gemini API authentication failed (401).")
    elif response.status_code != 200:
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


def _call_hf_json(
    prompt: str,
    schema: type[BaseModel],
    model: str,
    api_key: str,
    max_tokens: int = 4096,
) -> BaseModel:
    if not api_key:
        raise ValueError("Hugging Face API key is missing.")

    url = f"https://api-inference.huggingface.co/models/{model}/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    
    schema_json = schema.model_json_schema()
    schema_instruction = (
        "\n\nSTRICT OUTPUT REQUIREMENTS:\n"
        "1. Return ONLY a single raw valid JSON object matching the schema below.\n"
        "2. Do NOT enclose the output in markdown code blocks or backticks.\n"
        "3. Do NOT include any conversational intro or conclusion.\n"
        "4. CRITICAL: Preserve all indentation spaces in code blocks. Escape newlines properly as \\n.\n"
        f"JSON Schema: {json.dumps(schema_json, ensure_ascii=False)}"
    )

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt + schema_instruction}],
        "max_tokens": min(max_tokens, 4096),
        "temperature": 0.2
    }

    response = requests.post(url, headers=headers, json=payload, timeout=20.0)
    if response.status_code != 200:
        raise RuntimeError(f"HF API Error {response.status_code}: {response.text[:500]}")
    
    data = response.json()
    if not data.get("choices"):
        raise RuntimeError(f"HF returned no choices: {data}")
        
    text = data["choices"][0]["message"]["content"]
    return _parse_schema_response(text, schema, f"HuggingFace ({model})")


def _call_hf_text(prompt: str, model: str, api_key: str, max_tokens: int = 2048) -> str:
    if not api_key:
        raise ValueError("Hugging Face API key is missing.")

    url = f"https://api-inference.huggingface.co/models/{model}/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.4
    }

    response = requests.post(url, headers=headers, json=payload, timeout=20.0)
    if response.status_code != 200:
        raise RuntimeError(f"HF API Error {response.status_code}: {response.text[:500]}")
    
    data = response.json()
    if not data.get("choices"):
        raise RuntimeError(f"HF returned no choices: {data}")
        
    raw = data["choices"][0]["message"]["content"]
    return re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()


# =====================================================================
# 5. DISPATCHERS (Structured & Conversational)
# =====================================================================

def call_llm(
    prompt: str,
    schema: type[BaseModel],
    model_type: str = "fast",
    retries: int = 1,
    max_tokens: int = 4096,
) -> BaseModel:
    """
    Intelligent Dual-Engine Structured Dispatch:
    Tries configured providers with an active model cascade pool.
    """
    del retries
    
    # 1. Check cache
    cached = get_cached_response(prompt, schema.__name__, model_type)
    if cached:
        return cached

    errors = []
    
    # 2. Get provider priority from config
    provider_priority = Config.PROVIDERS.get(model_type, Config.PROVIDERS["fast"])

    for provider in provider_priority:
        if provider == "groq" and groq_pool.has_keys:
            for model_name in GROQ_MODELS:
                api_key = groq_pool.get_key()
                if not api_key:
                    continue
                try:
                    res = _call_groq_json(prompt, schema, model=model_name, api_key=api_key, max_tokens=max_tokens)
                    set_cached_response(prompt, schema.__name__, model_type, res)
                    return res
                except Exception as e:
                    err_str = str(e)
                    errors.append(f"Groq {model_name}: {err_str[:120]}")
                    if "429" in err_str or "503" in err_str:
                        FallbackStateManager.log_fallback_event("Groq", model_name, err_str[:200], prompt[:100])
                        groq_pool.mark_rate_limited(api_key)
                    continue

        elif provider == "gemini" and gemini_pool.has_keys:
            for model_name in GEMINI_MODELS:
                api_key = gemini_pool.get_key()
                if not api_key:
                    continue
                try:
                    res = _call_gemini_json(prompt, schema, model=model_name, api_key=api_key, max_tokens=max_tokens)
                    set_cached_response(prompt, schema.__name__, model_type, res)
                    return res
                except Exception as e:
                    err_str = str(e)
                    errors.append(f"Gemini {model_name}: {err_str[:120]}")
                    if "401" in err_str or "UNAUTHENTICATED" in err_str or "400" in err_str:
                        gemini_pool.mark_rate_limited(api_key, 3600) # Invalid key, sleep for 1hr
                        break # Stop trying other gemini models on this key
                    if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "503" in err_str:
                        FallbackStateManager.log_fallback_event("Gemini", model_name, err_str[:200], prompt[:100])
                        gemini_pool.mark_rate_limited(api_key)
                    continue
                    
        elif provider == "huggingface" and hf_pool.has_keys:
            for model_name in HF_MODELS:
                api_key = hf_pool.get_key()
                if not api_key:
                    continue
                try:
                    res = _call_hf_json(prompt, schema, model=model_name, api_key=api_key, max_tokens=max_tokens)
                    set_cached_response(prompt, schema.__name__, model_type, res)
                    return res
                except Exception as e:
                    err_str = str(e)
                    errors.append(f"HuggingFace {model_name}: {err_str[:120]}")
                    if "429" in err_str or "503" in err_str:
                        FallbackStateManager.log_fallback_event("HuggingFace", model_name, err_str[:200], prompt[:100])
                        hf_pool.mark_rate_limited(api_key)
                    continue

    error_summary = " | ".join(errors) if errors else "No valid keys available."
    raise LLMGenerationError(f"LLM structured generation failed across providers: {error_summary}")


def _call_groq_text(prompt: str, model: str, api_key: str, max_tokens: int = 2048) -> str:
    if not api_key:
        raise ValueError("Groq API key is missing.")
    groq_client = Groq(api_key=api_key, max_retries=0, timeout=15.0)
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
    return re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()


def _call_gemini_text(prompt: str, model: str, api_key: str, max_tokens: int = 2048) -> str:
    if not api_key:
        raise ValueError("Gemini API key is missing.")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    headers = {
        "x-goog-api-key": api_key,
        "Content-Type": "application/json",
    }
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "maxOutputTokens": max_tokens,
            "temperature": 0.4,
        },
    }
    response = requests.post(url, headers=headers, json=payload, timeout=20.0)
    if response.status_code == 401:
        raise RuntimeError("Gemini API authentication failed (401).")
    elif response.status_code != 200:
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
    Intelligent Dual-Engine Text Dispatch with Caching.
    """
    del retries
    
    cached = get_cached_response(prompt, "text", model_type)
    if cached:
        return cached
        
    errors = []
    provider_priority = Config.PROVIDERS.get(model_type, Config.PROVIDERS["fast"])

    for provider in provider_priority:
        if provider == "groq" and groq_pool.has_keys:
            for model_name in GROQ_MODELS:
                api_key = groq_pool.get_key()
                if not api_key:
                    continue
                try:
                    res = _call_groq_text(prompt, model=model_name, api_key=api_key)
                    set_cached_response(prompt, "text", model_type, res)
                    return res
                except Exception as e:
                    err_str = str(e)
                    errors.append(f"Groq {model_name}: {err_str[:120]}")
                    if "429" in err_str or "503" in err_str:
                        FallbackStateManager.log_fallback_event("Groq", model_name, err_str[:200], prompt[:100])
                        groq_pool.mark_rate_limited(api_key)
                    continue

        elif provider == "gemini" and gemini_pool.has_keys:
            for model_name in GEMINI_MODELS:
                api_key = gemini_pool.get_key()
                if not api_key:
                    continue
                try:
                    res = _call_gemini_text(prompt, model=model_name, api_key=api_key)
                    set_cached_response(prompt, "text", model_type, res)
                    return res
                except Exception as e:
                    err_str = str(e)
                    errors.append(f"Gemini {model_name}: {err_str[:120]}")
                    if "401" in err_str or "UNAUTHENTICATED" in err_str or "400" in err_str:
                        gemini_pool.mark_rate_limited(api_key, 3600)
                        break
                    if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "503" in err_str:
                        FallbackStateManager.log_fallback_event("Gemini", model_name, err_str[:200], prompt[:100])
                        gemini_pool.mark_rate_limited(api_key)
                    continue
                    
        elif provider == "huggingface" and hf_pool.has_keys:
            for model_name in HF_MODELS:
                api_key = hf_pool.get_key()
                if not api_key:
                    continue
                try:
                    res = _call_hf_text(prompt, model=model_name, api_key=api_key)
                    set_cached_response(prompt, "text", model_type, res)
                    return res
                except Exception as e:
                    err_str = str(e)
                    errors.append(f"HuggingFace {model_name}: {err_str[:120]}")
                    if "429" in err_str or "503" in err_str:
                        FallbackStateManager.log_fallback_event("HuggingFace", model_name, err_str[:200], prompt[:100])
                        hf_pool.mark_rate_limited(api_key)
                    continue

    error_summary = " | ".join(errors) if errors else "No valid keys available."
    raise LLMGenerationError(f"LLM text generation failed: {error_summary}")

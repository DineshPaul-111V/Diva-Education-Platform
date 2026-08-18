import os
import json
import re
import time
import logging
from groq import Groq
from pydantic import BaseModel, ValidationError
from dotenv import load_dotenv

# Ensure environment variables are loaded
load_dotenv(override=True)

logger = logging.getLogger(__name__)

def get_gemini_api_key() -> str:
    load_dotenv(override=True)
    return os.environ.get("GEMINI_API_KEY", "").strip("\"' \t\n\r")

def get_groq_client():
    load_dotenv(override=True)
    key = os.environ.get("GROQ_API_KEY", "").strip("\"' \t\n\r")
    if key:
        try:
            return Groq(api_key=key)
        except Exception as e:
            logger.warning("Failed to initialize Groq client: %s", e)
    return None

# =====================================================================
# 2. MODEL DEFINITIONS & POOLS
# =====================================================================

GEMINI_MODELS = [
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-2.0-flash-lite",
    "gemini-1.5-pro"
]

GROQ_MODELS = [
    "qwen/qwen3.6-27b",
    "openai/gpt-oss-20b",
    "openai/gpt-oss-120b"
]

class LLMGenerationError(Exception):
    pass

# =====================================================================
# 3. STRUCTURED JSON CALLS (Gemini First -> Groq Fallback)
# =====================================================================

def _call_gemini_rest(prompt: str, model: str = "gemini-2.0-flash", max_tokens: int = 4000, json_mode: bool = True) -> str:
    """Execute direct Gemini API REST call using x-goog-api-key header for full AQ./AIza. key compatibility."""
    import requests
    key = get_gemini_api_key()
    if not key:
        raise ValueError("GEMINI_API_KEY is not set in environment or .env file")
        
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    headers = {
        "x-goog-api-key": key,
        "Content-Type": "application/json"
    }
    gen_config = {
        "temperature": 0.2,
        "maxOutputTokens": max_tokens
    }
    if json_mode:
        gen_config["responseMimeType"] = "application/json"
        
    payload = {
        "contents": [{
            "parts": [{"text": prompt}]
        }],
        "generationConfig": gen_config
    }
    
    resp = requests.post(url, headers=headers, json=payload, timeout=30)
    if resp.status_code != 200:
        raise Exception(f"Gemini API Error ({resp.status_code}): {resp.text}")
        
    data = resp.json()
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as ke:
        raise Exception(f"Malformed Gemini API response: {data}") from ke

def _call_gemini_json(prompt: str, schema: type[BaseModel], model: str = "gemini-2.0-flash", max_tokens: int = 4000) -> BaseModel:
    """Execute structured JSON call via Google Gemini API."""
    schema_hint = f"\n\nReturn ONLY a JSON object strictly matching this schema definition:\n{json.dumps(schema.model_json_schema())}"
    full_prompt = prompt + schema_hint
    
    raw = _call_gemini_rest(full_prompt, model=model, max_tokens=max_tokens, json_mode=True)
    cleaned = re.sub(r"```json|```", "", raw).strip()
    
    try:
        return schema.model_validate_json(cleaned)
    except Exception:
        start_idx = cleaned.find("{")
        if start_idx != -1:
            try:
                obj, _ = json.JSONDecoder(strict=False).raw_decode(cleaned[start_idx:])
                return schema.model_validate(obj)
            except Exception:
                pass
        parsed = json.loads(cleaned)
        return schema.model_validate(parsed)

def _call_groq_json(prompt: str, schema: type[BaseModel], model: str = "qwen/qwen3.6-27b", max_tokens: int = 4000) -> BaseModel:
    """Execute structured JSON call via Groq API."""
    groq_client = get_groq_client()
    if not groq_client:
        raise ValueError("GROQ_API_KEY is not set or invalid")
        
    schema_hint = f"\n\nReturn ONLY valid JSON matching this schema:\n{json.dumps(schema.model_json_schema())}"
    
    call_kwargs = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a precise JSON-generating educational API. Return ONLY strictly valid JSON matching the requested schema. Do not enclose in markdown fences, do not output explanatory prose outside JSON."},
            {"role": "user", "content": prompt + schema_hint},
        ],
        "temperature": 0.2,
        "max_tokens": min(max_tokens, 4000)
    }
    
    if "qwen" in model.lower():
        call_kwargs["extra_body"] = {"reasoning_effort": "none"}
        
    completion = groq_client.chat.completions.create(**call_kwargs)
    raw = completion.choices[0].message.content or ""
    
    cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    cleaned = re.sub(r"```json|```", "", raw).strip()
    
    try:
        return schema.model_validate_json(cleaned)
    except Exception:
        start_idx = cleaned.find("{")
        end_idx = cleaned.rfind("}")
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            sub = cleaned[start_idx:end_idx+1]
            try:
                obj, _ = json.JSONDecoder(strict=False).raw_decode(sub)
                return schema.model_validate(obj)
            except Exception:
                try:
                    parsed = json.loads(sub)
                    return schema.model_validate(parsed)
                except Exception:
                    pass
        parsed = json.loads(cleaned)
        return schema.model_validate(parsed)

def call_llm(prompt: str, schema: type[BaseModel], model_type: str = "thinking", retries: int = 2, max_tokens: int = 3600) -> BaseModel:
    """
    Intelligent Dual-Engine Dispatch:
    1. If GEMINI_API_KEY is active: Attempts Gemini 2.0 Flash / 1.5 Flash.
    2. If Gemini fails / rate-limits / auth-fails: Cascades to Groq.
    3. Fails fast on 401/403 auth errors to prevent Gunicorn worker timeout.
    """
    gemini_key = get_gemini_api_key()
    groq_client = get_groq_client()
    
    if not gemini_key and not groq_client:
        raise LLMGenerationError("No LLM API keys found. Please add GEMINI_API_KEY or GROQ_API_KEY to your .env file.")
        
    last_error = None
    
    # 1. Try Gemini first if available
    if gemini_key:
        for g_model in GEMINI_MODELS:
            try:
                logger.info("Executing structured generation with Google Gemini (%s)...", g_model)
                return _call_gemini_json(prompt, schema, model=g_model, max_tokens=max_tokens)
            except Exception as ge:
                last_error = ge
                err_str = str(ge)
                logger.warning("Gemini model %s encountered error: %s", g_model, ge)
                # If authentication failed, stop trying other Gemini models
                if "401" in err_str or "UNAUTHENTICATED" in err_str or "403" in err_str:
                    logger.error("Gemini authentication failed. Skipping Gemini pool.")
                    break
                continue
                
    # 2. Try Groq Model Pool
    if groq_client:
        for g_model in GROQ_MODELS:
            try:
                logger.info("Executing structured generation with Groq (%s)...", g_model)
                return _call_groq_json(prompt, schema, model=g_model, max_tokens=max_tokens)
            except Exception as qe:
                last_error = qe
                err_str = str(qe)
                logger.warning("Groq model %s failed: %s", g_model, qe)
                if "401" in err_str or "Invalid API Key" in err_str:
                    logger.error("Groq authentication failed. Skipping Groq pool.")
                    break
                continue

    logger.error("All Dual-Engine LLM generation attempts failed: %s", last_error)
    raise LLMGenerationError(f"LLM generation failed across providers: {last_error}")

# =====================================================================
# 4. CONVERSATIONAL & REAL-TIME CALLS
# =====================================================================

def _call_groq_text(prompt: str, model: str = "qwen/qwen3.6-27b", max_tokens: int = 2000) -> str:
    """Execute text generation with Groq."""
    groq_client = get_groq_client()
    if not groq_client:
        raise ValueError("GROQ_API_KEY is not set")
    call_kwargs = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.4,
        "max_tokens": max_tokens
    }
    if "qwen" in model.lower():
        call_kwargs["extra_body"] = {"reasoning_effort": "none"}
    completion = groq_client.chat.completions.create(**call_kwargs)
    raw = completion.choices[0].message.content or ""
    return re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()

def _call_gemini_text(prompt: str, model: str = "gemini-2.0-flash", max_tokens: int = 2000) -> str:
    """Execute text generation with Gemini."""
    raw = _call_gemini_rest(prompt, model=model, max_tokens=max_tokens, json_mode=False)
    return (raw or "").strip()

def call_llm_text(prompt: str, model_type: str = "fast", retries: int = 1) -> str:
    gemini_key = get_gemini_api_key()
    groq_client = get_groq_client()
    
    if not gemini_key and not groq_client:
        raise LLMGenerationError("No LLM API keys found. Please set GEMINI_API_KEY or GROQ_API_KEY.")
        
    last_error = None
    
    # 1. Try Gemini first
    if gemini_key:
        for gemini_model in ["gemini-2.0-flash", "gemini-1.5-flash"]:
            try:
                return _call_gemini_text(prompt, model=gemini_model)
            except Exception as ge:
                last_error = ge
                err_str = str(ge)
                logger.warning("Gemini text model %s failed: %s", gemini_model, ge)
                if "401" in err_str or "UNAUTHENTICATED" in err_str or "403" in err_str:
                    break
                continue

    # 2. Try Groq fallback
    if groq_client:
        for g_model in ["openai/gpt-oss-120b", "qwen/qwen3.6-27b", "openai/gpt-oss-20b"]:
            try:
                return _call_groq_text(prompt, model=g_model)
            except Exception as qe:
                last_error = qe
                err_str = str(qe)
                logger.warning("Groq text model %s failed: %s", g_model, qe)
                if "401" in err_str or "Invalid API Key" in err_str:
                    break
                continue

    logger.error("LLM text generation failed across all Dual-Engine providers: %s", last_error)
    raise LLMGenerationError(f"LLM text generation failed: {last_error}")

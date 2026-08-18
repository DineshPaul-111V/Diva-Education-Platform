import os
import json
import re
import time
import logging
from groq import Groq
from pydantic import BaseModel, ValidationError
from dotenv import load_dotenv

# Ensure environment variables are loaded
load_dotenv()

logger = logging.getLogger(__name__)

# =====================================================================
# 1. API CLIENT INITIALIZATION (Dual-Engine: Groq + Google Gemini)
# =====================================================================

# Groq Client
groq_api_key = os.environ.get("GROQ_API_KEY", "").strip("\"' \t\n\r")
groq_client = None
if groq_api_key:
    try:
        groq_client = Groq(api_key=groq_api_key)
    except Exception as e:
        logger.warning("Failed to initialize Groq client: %s", e)

# Google Gemini Client
gemini_api_key = os.environ.get("GEMINI_API_KEY", "").strip("\"' \t\n\r")
gemini_client = None
if gemini_api_key:
    try:
        from google import genai
        from google.genai import types
        gemini_client = genai.Client(api_key=gemini_api_key)
        logger.info("Google Gemini Client initialized successfully.")
    except Exception as e:
        logger.warning("Failed to initialize Google Gemini client: %s", e)

if not groq_client and not gemini_client:
    logger.critical("Neither GROQ_API_KEY nor GEMINI_API_KEY is configured. LLM calls will fail.")

# =====================================================================
# 2. MODEL DEFINITIONS & POOLS (Task Specialized)
# =====================================================================

# Primary for Deep Reasoning, Large Context & Structured Synthesis (Skill Maps, Chapters, Diagnostic)
GEMINI_MODELS = [
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-2.0-flash-lite",
    "gemini-1.5-pro"
]

# Primary for Real-Time, Sub-Second Speed (Tutor Chat, Compiler Feedback, Live Evaluation)
GROQ_FAST_MODELS = [
    "llama-3.1-8b-instant",
    "mixtral-8x7b-32768",
    "gemma2-9b-it",
    "llama-3.3-70b-versatile"
]

GROQ_STRUCTURED_MODELS = [
    "llama-3.1-8b-instant",
    "mixtral-8x7b-32768",
    "gemma2-9b-it",
    "llama-3.3-70b-versatile"
]

class LLMGenerationError(Exception):
    pass

# =====================================================================
# 3. STRUCTURED JSON CALLS (Gemini First for Deep Depth -> Groq Fallback)
# =====================================================================

def _call_gemini_rest(prompt: str, model: str = "gemini-2.0-flash", max_tokens: int = 4000, json_mode: bool = True) -> str:
    """Execute direct Gemini API REST call using x-goog-api-key header for full AQ./AIza. key compatibility."""
    import requests
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    headers = {
        "x-goog-api-key": gemini_api_key,
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
    
    resp = requests.post(url, headers=headers, json=payload, timeout=25)
    if resp.status_code != 200:
        raise Exception(f"Gemini API Error {resp.status_code}: {resp.text}")
        
    data = resp.json()
    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as ke:
        raise Exception(f"Malformed Gemini API response: {data}") from ke

def _call_gemini_json(prompt: str, schema: type[BaseModel], model: str = "gemini-2.0-flash", max_tokens: int = 4000) -> BaseModel:
    """Execute structured JSON call via Google Gemini API."""
    if not gemini_api_key:
        raise ValueError("Gemini API key not configured")
        
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

def _call_groq_json(prompt: str, schema: type[BaseModel], model: str = "llama-3.1-8b-instant", max_tokens: int = 3500) -> BaseModel:
    """Execute structured JSON call via Groq API."""
    if not groq_client:
        raise ValueError("Groq client not initialized")
        
    schema_hint = f"\n\nReturn ONLY valid JSON matching this schema:\n{json.dumps(schema.model_json_schema())}"
    
    call_kwargs = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a precise JSON-generating educational API. Return ONLY strictly valid JSON matching the requested schema. Do not enclose in markdown fences, do not output explanatory prose outside JSON."},
            {"role": "user", "content": prompt + schema_hint},
        ],
        "temperature": 0.2,
        "max_tokens": min(max_tokens, 3500)
    }
        
    completion = groq_client.chat.completions.create(**call_kwargs)
    raw = completion.choices[0].message.content or ""
    
    cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    cleaned = re.sub(r"```json|```", "", cleaned).strip()
    
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

def call_llm(prompt: str, schema: type[BaseModel], model_type: str = "thinking", retries: int = 2, max_tokens: int = 3600) -> BaseModel:
    """
    Intelligent Task-Specialized Dual-Engine Dispatch:
    - model_type="fast": Uses Groq first (sub-second generation for diagnostics, skill maps, quizzes),
      with Gemini as reliable fallback.
    - model_type="thinking" (default): Uses Google Gemini first (deep context & chapter textbook depth),
      with Groq as reliable fallback.
    """
    last_error = None
    
    # Strategy A: Fast tasks prioritize Groq -> Gemini fallback
    if model_type == "fast":
        if groq_client:
            for g_model in GROQ_STRUCTURED_MODELS:
                try:
                    logger.info("Executing fast structured generation with Groq (%s)...", g_model)
                    return _call_groq_json(prompt, schema, model=g_model, max_tokens=max_tokens)
                except Exception as qe:
                    last_error = qe
                    err_str = str(qe)
                    logger.warning("Groq model %s failed: %s", g_model, qe)
                    if "401" in err_str or "Invalid API Key" in err_str:
                        break
                    continue
        if gemini_api_key:
            for g_model in GEMINI_MODELS:
                try:
                    logger.info("Executing structured fallback with Google Gemini (%s)...", g_model)
                    return _call_gemini_json(prompt, schema, model=g_model, max_tokens=max_tokens)
                except Exception as ge:
                    last_error = ge
                    err_str = str(ge)
                    logger.warning("Gemini model %s failed: %s", g_model, ge)
                    if "401" in err_str or "UNAUTHENTICATED" in err_str or "403" in err_str:
                        break
                    continue

    # Strategy B: Deep/Thinking tasks prioritize Gemini -> Groq fallback
    else:
        if gemini_api_key:
            for g_model in GEMINI_MODELS:
                try:
                    logger.info("Executing deep structured generation with Google Gemini (%s)...", g_model)
                    return _call_gemini_json(prompt, schema, model=g_model, max_tokens=max_tokens)
                except Exception as ge:
                    last_error = ge
                    err_str = str(ge)
                    logger.warning("Gemini model %s encountered error: %s", g_model, ge)
                    if "401" in err_str or "UNAUTHENTICATED" in err_str or "403" in err_str:
                        break
                    continue
                    
        if groq_client:
            for g_model in GROQ_STRUCTURED_MODELS:
                try:
                    logger.info("Executing deep generation fallback with Groq (%s)...", g_model)
                    return _call_groq_json(prompt, schema, model=g_model, max_tokens=max_tokens)
                except Exception as qe:
                    last_error = qe
                    err_str = str(qe)
                    logger.warning("Groq model %s failed: %s", g_model, qe)
                    if "401" in err_str or "Invalid API Key" in err_str:
                        break
                    continue

    logger.error("All Dual-Engine LLM generation attempts failed: %s", last_error)
    raise LLMGenerationError(f"LLM generation failed across providers: {last_error}")

# =====================================================================
# 4. CONVERSATIONAL & REAL-TIME CALLS (Task Specialized)
# =====================================================================

def _call_groq_text(prompt: str, model: str = "llama-3.1-8b-instant", max_tokens: int = 2000) -> str:
    """Execute text generation with Groq."""
    if not groq_client:
        raise ValueError("Groq client not initialized")
    call_kwargs = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.4,
        "max_tokens": max_tokens
    }
    completion = groq_client.chat.completions.create(**call_kwargs)
    raw = completion.choices[0].message.content or ""
    return re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()

def _call_gemini_text(prompt: str, model: str = "gemini-2.0-flash", max_tokens: int = 2000) -> str:
    """Execute text generation with Gemini."""
    if not gemini_api_key:
        raise ValueError("Gemini API key not configured")
    raw = _call_gemini_rest(prompt, model=model, max_tokens=max_tokens, json_mode=False)
    return (raw or "").strip()

def call_llm_text(prompt: str, model_type: str = "fast", retries: int = 1) -> str:
    """
    Conversational / Real-Time Dispatch:
    - model_type="fast": Groq (sub-second Socratic chat, compiler feedback, hints) -> Gemini fallback.
    - model_type="thinking": Gemini (in-depth conversational tutoring) -> Groq fallback.
    """
    last_error = None
    
    if model_type == "fast":
        # 1. Try Groq first for real-time interactive speed
        if groq_client:
            for g_model in GROQ_FAST_MODELS:
                try:
                    return _call_groq_text(prompt, model=g_model)
                except Exception as qe:
                    last_error = qe
                    err_str = str(qe)
                    logger.warning("Groq text model %s failed: %s", g_model, qe)
                    if "401" in err_str or "Invalid API Key" in err_str:
                        break
                    continue
        # 2. Try Gemini fallback
        if gemini_api_key:
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
    else:
        # Deep/Thinking text generation (Gemini first -> Groq fallback)
        if gemini_api_key:
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
        if groq_client:
            for g_model in GROQ_FAST_MODELS:
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


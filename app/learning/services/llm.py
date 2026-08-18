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
# 2. MODEL DEFINITIONS & POOLS
# =====================================================================

GEMINI_MODELS = [
    "gemini-flash-lite-latest",
    "gemini-2.5-flash",
    "gemini-flash-latest",
    "gemini-3.7-flash"
]

GROQ_MODELS = [
    "llama-3.3-70b-versatile",
    "openai/gpt-oss-120b",
    "llama-3.1-8b-instant",
    "openai/gpt-oss-20b",
    "qwen/qwen3.6-27b"
]

class LLMGenerationError(Exception):
    pass

# =====================================================================
# 3. STRUCTURED JSON CALLS (Gemini First for Deep Depth -> Groq Fallback)
# =====================================================================

def _call_gemini_json(prompt: str, schema: type[BaseModel], model: str = "gemini-flash-latest", max_tokens: int = 4000) -> BaseModel:
    """Execute structured JSON call via Google Gemini API with native schema validation."""
    if not gemini_client:
        raise ValueError("Gemini client not initialized")
        
    from google.genai import types
    
    # Configure Gemini structured JSON generation with native Pydantic schema
    config = types.GenerateContentConfig(
        temperature=0.2,
        max_output_tokens=max_tokens,
        response_mime_type="application/json",
        response_schema=schema
    )
    
    response = gemini_client.models.generate_content(
        model=model,
        contents=prompt,
        config=config
    )
    
    raw = response.text or ""
    try:
        return schema.model_validate_json(raw)
    except Exception:
        cleaned = re.sub(r"```json|```", "", raw).strip()
        start_idx = cleaned.find("{")
        if start_idx != -1:
            try:
                obj, _ = json.JSONDecoder(strict=False).raw_decode(cleaned[start_idx:])
                return schema.model_validate(obj)
            except Exception:
                pass
        try:
            parsed = json.loads(cleaned)
            return schema.model_validate(parsed)
        except Exception as pe:
            logger.warning("Gemini JSON validation failed on %s: %s", model, pe)
            raise pe

def _call_groq_json(prompt: str, schema: type[BaseModel], model: str = "llama-3.3-70b-versatile", max_tokens: int = 3500) -> BaseModel:
    """Execute structured JSON call via Groq API."""
    if not groq_client:
        raise ValueError("Groq client not initialized")
        
    call_kwargs = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a precise JSON-generating educational API. Return ONLY strictly valid JSON matching the requested schema. Do not enclose in markdown fences, do not output explanatory prose outside JSON."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.3,
        "max_tokens": min(max_tokens, 3500)
    }
    if "qwen" in model.lower():
        call_kwargs["reasoning_effort"] = "none"
        
    completion = groq_client.chat.completions.create(**call_kwargs)
    raw = completion.choices[0].message.content or ""
    
    cleaned = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    cleaned = re.sub(r"```json|```", "", cleaned).strip()
    
    start_idx = cleaned.find("{")
    if start_idx != -1:
        try:
            obj, _ = json.JSONDecoder(strict=False).raw_decode(cleaned[start_idx:])
            return schema.model_validate(obj)
        except Exception as pe:
            logger.warning("Groq JSON decode raw_decode failed on %s: %s", model, pe)
            
    parsed = json.loads(cleaned)
    return schema.model_validate(parsed)

def call_llm(prompt: str, schema: type[BaseModel], model_type: str = "thinking", retries: int = 4, max_tokens: int = 3600) -> BaseModel:
    """
    Intelligent Dual-Engine Dispatch:
    1. If GEMINI_API_KEY is active: Attempts Gemini Flash Latest / 3.7 Flash / Flash Lite (highest depth, 1M context, robust JSON).
    2. If Gemini is unavailable or rate-limited: Seamlessly cascades through Groq Llama 3.3 70B / GPT-OSS pool.
    3. If only Groq is configured: Directly executes Groq model pool cascade.
    """
    last_error = None
    
    # 1. Try Gemini first if available (Superior for textbook chapter depth and structured JSON)
    if gemini_client:
        for g_model in GEMINI_MODELS:
            try:
                logger.info("Executing structured generation with Google Gemini (%s)...", g_model)
                return _call_gemini_json(prompt, schema, model=g_model, max_tokens=max_tokens)
            except Exception as ge:
                last_error = ge
                logger.warning("Gemini model %s encountered error (%s). Trying next Gemini model in pool...", g_model, ge)
                time.sleep(0.5)
                continue
                
    # 2. Try Groq Model Pool
    if groq_client:
        for g_model in GROQ_MODELS:
            try:
                logger.info("Executing structured generation with Groq (%s)...", g_model)
                return _call_groq_json(prompt, schema, model=g_model, max_tokens=max_tokens)
            except Exception as qe:
                last_error = qe
                logger.warning("Groq model %s failed (%s). Cycling to next model...", g_model, qe)
                time.sleep(1.0)
                continue

    logger.error("All Dual-Engine LLM generation attempts failed: %s", last_error)
    raise LLMGenerationError(f"LLM generation failed across both Gemini and Groq providers: {last_error}")

# =====================================================================
# 4. CONVERSATIONAL & REAL-TIME CALLS (Groq First for Sub-Second Speed)
# =====================================================================

def _call_groq_text(prompt: str, model: str = "llama-3.3-70b-versatile", max_tokens: int = 2000) -> str:
    """Execute text generation with Groq."""
    if not groq_client:
        raise ValueError("Groq client not initialized")
    call_kwargs = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.4,
        "max_tokens": max_tokens
    }
    if "qwen" in model.lower():
        call_kwargs["reasoning_effort"] = "none"
    completion = groq_client.chat.completions.create(**call_kwargs)
    raw = completion.choices[0].message.content or ""
    return re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()

def _call_gemini_text(prompt: str, model: str = "gemini-2.5-flash", max_tokens: int = 2000) -> str:
    """Execute text generation with Gemini."""
    if not gemini_client:
        raise ValueError("Gemini client not initialized")
    from google.genai import types
    config = types.GenerateContentConfig(
        temperature=0.4,
        max_output_tokens=max_tokens
    )
    response = gemini_client.models.generate_content(
        model=model,
        contents=prompt,
        config=config
    )
    return (response.text or "").strip()

def call_llm_text(prompt: str, model_type: str = "fast", retries: int = 1) -> str:
    """
    Intelligent Dual-Engine Text Dispatch:
    1. Attempts Google Gemini Flash for sub-second, highly coherent tutoring responses.
    2. Falls back to Groq models if Gemini hits quota/errors.
    """
    last_error = None
    
    # 1. Try Gemini first for ultra-fast, rich conversational responses
    if gemini_client:
        for gemini_model in ["gemini-flash-lite-latest", "gemini-2.5-flash", "gemini-flash-latest"]:
            try:
                return _call_gemini_text(prompt, model=gemini_model)
            except Exception as ge:
                last_error = ge
                logger.warning("Gemini text model %s failed (%s). Trying fallback...", gemini_model, ge)
                continue

    # 2. Try Groq as robust fallback
    if groq_client:
        for g_model in ["llama-3.1-8b-instant", "llama-3.3-70b-versatile", "qwen/qwen3.6-27b"]:
            try:
                return _call_groq_text(prompt, model=g_model)
            except Exception as qe:
                last_error = qe
                logger.warning("Groq text model %s failed (%s)...", g_model, qe)
                continue

    logger.error("LLM text generation failed across all Dual-Engine providers: %s", last_error)
    raise LLMGenerationError(f"LLM text generation failed across Gemini and Groq providers: {last_error}")

import os
import json
import re
import logging

import requests
from groq import Groq
from pydantic import BaseModel
from dotenv import load_dotenv


# ============================================================
# 1. ENVIRONMENT
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
        groq_client = Groq(api_key=groq_api_key)
        logger.info("Groq client initialized successfully.")
    except Exception as e:
        logger.exception("Failed to initialize Groq client: %s", e)
else:
    logger.warning("GROQ_API_KEY is not configured.")


# Gemini is intentionally called through REST below.
# This avoids SDK authentication/configuration conflicts.
if gemini_api_key:
    logger.info("Gemini API key detected.")
else:
    logger.warning("GEMINI_API_KEY is not configured.")


if not groq_client and not gemini_api_key:
    logger.critical(
        "Neither GROQ_API_KEY nor GEMINI_API_KEY is configured. "
        "All LLM calls will fail."
    )


# ============================================================
# 4. CURRENT MODEL CONFIGURATION
# ============================================================

# Gemini 2.5 Flash is currently available through the Gemini API
# and supports structured JSON output.
#
# We intentionally use ONE stable model instead of cycling through
# many old/deprecated models.
GEMINI_MODEL = "gemini-2.5-flash"


# Groq production model.
# Supports JSON Object Mode and is suitable for educational apps.
GROQ_MODEL = "openai/gpt-oss-20b"


# ============================================================
# 5. CUSTOM ERROR
# ============================================================

class LLMGenerationError(Exception):
    """Raised when all configured LLM providers fail."""

    pass


# ============================================================
# 6. GEMINI REST API
# ============================================================

def _call_gemini_rest(
    prompt: str,
    model: str = GEMINI_MODEL,
    max_tokens: int = 4000,
    json_mode: bool = True,
) -> str:
    """
    Call Gemini directly through the Gemini REST API.

    This intentionally uses the x-goog-api-key header instead of
    OAuth credentials.
    """

    if not gemini_api_key:
        raise ValueError("GEMINI_API_KEY is not configured.")

    url = (
        "https://generativelanguage.googleapis.com/"
        f"v1beta/models/{model}:generateContent"
    )

    headers = {
        "x-goog-api-key": gemini_api_key,
        "Content-Type": "application/json",
    }

    generation_config = {
        "maxOutputTokens": max_tokens,
    }

    if json_mode:
        generation_config["responseMimeType"] = "application/json"

    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "text": prompt
                    }
                ]
            }
        ],
        "generationConfig": generation_config,
    }

    logger.info("Calling Gemini model: %s", model)

    response = requests.post(
        url,
        headers=headers,
        json=payload,
        timeout=45,
    )

    if response.status_code != 200:
        raise Exception(
            f"Gemini API Error {response.status_code}: {response.text}"
        )

    data = response.json()

    try:
        candidates = data.get("candidates", [])

        if not candidates:
            raise Exception(
                f"Gemini returned no candidates: {data}"
            )

        content = candidates[0].get("content", {})
        parts = content.get("parts", [])

        if not parts:
            raise Exception(
                f"Gemini returned no content parts: {data}"
            )

        text = parts[0].get("text")

        if not text:
            raise Exception(
                f"Gemini returned empty text: {data}"
            )

        return text

    except Exception as e:
        raise Exception(
            f"Malformed Gemini API response: {data}"
        ) from e


# ============================================================
# 7. GEMINI STRUCTURED JSON
# ============================================================

def _call_gemini_json(
    prompt: str,
    schema: type[BaseModel],
    model: str = GEMINI_MODEL,
    max_tokens: int = 4000,
) -> BaseModel:
    """
    Generate structured JSON using Gemini and validate it
    against the supplied Pydantic model.
    """

    if not gemini_api_key:
        raise ValueError("GEMINI_API_KEY is not configured.")

    schema_json = schema.model_json_schema()

    schema_hint = (
        "\n\n"
        "IMPORTANT:\n"
        "Return ONLY one valid JSON object.\n"
        "Do not use Markdown.\n"
        "Do not use ```json fences.\n"
        "The JSON must match this schema:\n"
        f"{json.dumps(schema_json, ensure_ascii=False)}"
    )

    full_prompt = prompt + schema_hint

    raw = _call_gemini_rest(
        full_prompt,
        model=model,
        max_tokens=max_tokens,
        json_mode=True,
    )

    cleaned = raw.strip()

    # Remove accidental Markdown fences.
    cleaned = re.sub(
        r"^```json\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    cleaned = re.sub(
        r"^```\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    cleaned = re.sub(
        r"\s*```$",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    cleaned = cleaned.strip()

    # First attempt: Pydantic JSON validation.
    try:
        return schema.model_validate_json(cleaned)
    except Exception:
        pass

    # Second attempt: extract the first JSON object.
    start_index = cleaned.find("{")

    if start_index != -1:
        try:
            decoder = json.JSONDecoder(strict=False)

            obj, _ = decoder.raw_decode(
                cleaned[start_index:]
            )

            return schema.model_validate(obj)

        except Exception:
            pass

    # Third attempt: regular JSON parsing.
    try:
        parsed = json.loads(cleaned)
        return schema.model_validate(parsed)

    except Exception as e:
        raise ValueError(
            "Gemini returned invalid JSON that does not match "
            f"{schema.__name__}: {cleaned[:1000]}"
        ) from e


# ============================================================
# 8. GROQ STRUCTURED JSON
# ============================================================

def _call_groq_json(
    prompt: str,
    schema: type[BaseModel],
    model: str = GROQ_MODEL,
    max_tokens: int = 3500,
) -> BaseModel:
    """
    Generate structured JSON using Groq.
    """

    if not groq_client:
        raise ValueError("Groq client is not initialized.")

    schema_json = schema.model_json_schema()

    schema_hint = (
        "\n\n"
        "Return ONLY one valid JSON object.\n"
        "Do not use Markdown.\n"
        "Do not use ```json fences.\n"
        "The JSON must match this schema:\n"
        f"{json.dumps(schema_json, ensure_ascii=False)}"
    )

    call_kwargs = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a precise JSON-generating educational API. "
                    "Return ONLY valid JSON matching the requested schema. "
                    "Do not return explanations or Markdown."
                ),
            },
            {
                "role": "user",
                "content": prompt + schema_hint,
            },
        ],
        "temperature": 0.2,
        "max_tokens": min(max_tokens, 3500),

        # llama-3.1-8b-instant supports JSON Object Mode.
        "response_format": {
            "type": "json_object"
        },
    }

    logger.info("Calling Groq model: %s", model)

    completion = groq_client.chat.completions.create(
        **call_kwargs
    )

    raw = completion.choices[0].message.content or ""

    # Remove thinking tags if a model happens to return them.
    cleaned = re.sub(
        r"<think>.*?</think>",
        "",
        raw,
        flags=re.DOTALL,
    ).strip()

    # Remove Markdown fences.
    cleaned = re.sub(
        r"^```json\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    cleaned = re.sub(
        r"^```\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    cleaned = re.sub(
        r"\s*```$",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    cleaned = cleaned.strip()

    # First attempt.
    try:
        return schema.model_validate_json(cleaned)
    except Exception:
        pass

    # Second attempt: extract JSON object.
    start_index = cleaned.find("{")

    if start_index != -1:
        try:
            decoder = json.JSONDecoder(strict=False)

            obj, _ = decoder.raw_decode(
                cleaned[start_index:]
            )

            return schema.model_validate(obj)

        except Exception:
            pass

    # Third attempt.
    try:
        parsed = json.loads(cleaned)
        return schema.model_validate(parsed)

    except Exception as e:
        raise ValueError(
            "Groq returned invalid JSON that does not match "
            f"{schema.__name__}: {cleaned[:1000]}"
        ) from e


# ============================================================
# 9. MAIN STRUCTURED LLM DISPATCHER
# ============================================================

def call_llm(
    prompt: str,
    schema: type[BaseModel],
    model_type: str = "thinking",
    retries: int = 1,
    max_tokens: int = 3600,
) -> BaseModel:
    """
    Main structured LLM dispatcher.

    FAST:
        Groq -> Gemini

    THINKING:
        Gemini -> Groq

    Only one model per provider is used.
    This prevents long fallback chains and worker timeouts.
    """

    errors = []

    # ========================================================
    # FAST MODE
    # ========================================================

    if model_type == "fast":

        # ----------------------------------------------------
        # 1. Groq
        # ----------------------------------------------------

        if groq_client:

            try:
                logger.info(
                    "Fast LLM request -> Groq (%s)",
                    GROQ_MODEL,
                )

                return _call_groq_json(
                    prompt,
                    schema,
                    model=GROQ_MODEL,
                    max_tokens=max_tokens,
                )

            except Exception as e:

                errors.append(
                    f"Groq {GROQ_MODEL}: {e}"
                )

                logger.warning(
                    "Groq failed: %s",
                    e,
                )

        # ----------------------------------------------------
        # 2. Gemini fallback
        # ----------------------------------------------------

        if gemini_api_key:

            try:
                logger.info(
                    "Fast LLM fallback -> Gemini (%s)",
                    GEMINI_MODEL,
                )

                return _call_gemini_json(
                    prompt,
                    schema,
                    model=GEMINI_MODEL,
                    max_tokens=max_tokens,
                )

            except Exception as e:

                errors.append(
                    f"Gemini {GEMINI_MODEL}: {e}"
                )

                logger.warning(
                    "Gemini fallback failed: %s",
                    e,
                )

    # ========================================================
    # THINKING MODE
    # ========================================================

    else:

        # ----------------------------------------------------
        # 1. Gemini
        # ----------------------------------------------------

        if gemini_api_key:

            try:
                logger.info(
                    "Thinking LLM request -> Gemini (%s)",
                    GEMINI_MODEL,
                )

                return _call_gemini_json(
                    prompt,
                    schema,
                    model=GEMINI_MODEL,
                    max_tokens=max_tokens,
                )

            except Exception as e:

                errors.append(
                    f"Gemini {GEMINI_MODEL}: {e}"
                )

                logger.warning(
                    "Gemini failed: %s",
                    e,
                )

        # ----------------------------------------------------
        # 2. Groq fallback
        # ----------------------------------------------------

        if groq_client:

            try:
                logger.info(
                    "Thinking LLM fallback -> Groq (%s)",
                    GROQ_MODEL,
                )

                return _call_groq_json(
                    prompt,
                    schema,
                    model=GROQ_MODEL,
                    max_tokens=max_tokens,
                )

            except Exception as e:

                errors.append(
                    f"Groq {GROQ_MODEL}: {e}"
                )

                logger.warning(
                    "Groq fallback failed: %s",
                    e,
                )

    # ========================================================
    # COMPLETE FAILURE
    # ========================================================

    error_message = " | ".join(errors)

    logger.error(
        "All LLM generation attempts failed: %s",
        error_message,
    )

    raise LLMGenerationError(
        "LLM generation failed across providers: "
        + (error_message or "No LLM provider is configured.")
    )


# ============================================================
# 10. GROQ TEXT GENERATION
# ============================================================

def _call_groq_text(
    prompt: str,
    model: str = GROQ_MODEL,
    max_tokens: int = 2000,
) -> str:
    """
    Plain text generation using Groq.
    """

    if not groq_client:
        raise ValueError("Groq client is not initialized.")

    completion = groq_client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
        temperature=0.4,
        max_tokens=max_tokens,
    )

    raw = completion.choices[0].message.content or ""

    return re.sub(
        r"<think>.*?</think>",
        "",
        raw,
        flags=re.DOTALL,
    ).strip()


# ============================================================
# 11. GEMINI TEXT GENERATION
# ============================================================

def _call_gemini_text(
    prompt: str,
    model: str = GEMINI_MODEL,
    max_tokens: int = 2000,
) -> str:
    """
    Plain text generation using Gemini REST API.
    """

    if not gemini_api_key:
        raise ValueError("GEMINI_API_KEY is not configured.")

    raw = _call_gemini_rest(
        prompt,
        model=model,
        max_tokens=max_tokens,
        json_mode=False,
    )

    return (raw or "").strip()


# ============================================================
# 12. TEXT LLM DISPATCHER
# ============================================================

def call_llm_text(
    prompt: str,
    model_type: str = "fast",
    retries: int = 1,
) -> str:
    """
    Text-generation dispatcher.

    FAST:
        Groq -> Gemini

    THINKING:
        Gemini -> Groq
    """

    errors = []

    # ========================================================
    # FAST
    # ========================================================

    if model_type == "fast":

        if groq_client:

            try:
                logger.info(
                    "Fast text request -> Groq (%s)",
                    GROQ_MODEL,
                )

                return _call_groq_text(
                    prompt,
                    model=GROQ_MODEL,
                )

            except Exception as e:

                errors.append(
                    f"Groq {GROQ_MODEL}: {e}"
                )

                logger.warning(
                    "Groq text generation failed: %s",
                    e,
                )

        if gemini_api_key:

            try:
                logger.info(
                    "Fast text fallback -> Gemini (%s)",
                    GEMINI_MODEL,
                )

                return _call_gemini_text(
                    prompt,
                    model=GEMINI_MODEL,
                )

            except Exception as e:

                errors.append(
                    f"Gemini {GEMINI_MODEL}: {e}"
                )

                logger.warning(
                    "Gemini text generation failed: %s",
                    e,
                )

    # ========================================================
    # THINKING
    # ========================================================

    else:

        if gemini_api_key:

            try:
                logger.info(
                    "Thinking text request -> Gemini (%s)",
                    GEMINI_MODEL,
                )

                return _call_gemini_text(
                    prompt,
                    model=GEMINI_MODEL,
                )

            except Exception as e:

                errors.append(
                    f"Gemini {GEMINI_MODEL}: {e}"
                )

                logger.warning(
                    "Gemini text generation failed: %s",
                    e,
                )

        if groq_client:

            try:
                logger.info(
                    "Thinking text fallback -> Groq (%s)",
                    GROQ_MODEL,
                )

                return _call_groq_text(
                    prompt,
                    model=GROQ_MODEL,
                )

            except Exception as e:

                errors.append(
                    f"Groq {GROQ_MODEL}: {e}"
                )

                logger.warning(
                    "Groq text generation failed: %s",
                    e,
                )

    # ========================================================
    # COMPLETE FAILURE
    # ========================================================

    error_message = " | ".join(errors)

    logger.error(
        "LLM text generation failed: %s",
        error_message,
    )

    raise LLMGenerationError(
        "LLM text generation failed: "
        + (error_message or "No LLM provider is configured.")
    )

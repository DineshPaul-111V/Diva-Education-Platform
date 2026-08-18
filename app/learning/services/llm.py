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

groq_api_key = os.environ.get(
    "GROQ_API_KEY",
    ""
).strip("\"' \t\n\r")

gemini_api_key = os.environ.get(
    "GEMINI_API_KEY",
    ""
).strip("\"' \t\n\r")


# ============================================================
# 3. CLIENT INITIALIZATION
# ============================================================

groq_client = None

if groq_api_key:
    try:
        # IMPORTANT:
        # Disable SDK automatic retries.
        # Otherwise a 429 can block the Gunicorn worker
        # until the worker timeout is reached.
        groq_client = Groq(
            api_key=groq_api_key,
            max_retries=0,
        )

        logger.info(
            "Groq client initialized successfully."
        )

    except Exception as e:
        logger.exception(
            "Failed to initialize Groq client: %s",
            e,
        )
else:
    logger.warning(
        "GROQ_API_KEY is not configured."
    )


# Gemini is called through REST.
# This keeps authentication simple and explicit.
if gemini_api_key:
    logger.info(
        "Gemini API key detected."
    )
else:
    logger.warning(
        "GEMINI_API_KEY is not configured."
    )


if not groq_client and not gemini_api_key:
    logger.critical(
        "Neither GROQ_API_KEY nor GEMINI_API_KEY is configured."
    )


# ============================================================
# 4. MODEL CONFIGURATION
# ============================================================

# Current Gemini model.
# Gemini 2.5 Flash is still available through the Gemini API.
GEMINI_MODEL = "gemini-2.5-flash"


# Current Groq model.
# GPT-OSS 20B supports JSON and structured output capabilities.
GROQ_MODEL = "openai/gpt-oss-20b"


# ============================================================
# 5. CUSTOM ERROR
# ============================================================

class LLMGenerationError(Exception):
    """
    Raised when all configured LLM providers fail.
    """

    pass


# ============================================================
# 6. JSON CLEANING HELPERS
# ============================================================

def _clean_model_json(raw: str) -> str:
    """
    Clean common Markdown/thinking wrappers around JSON.
    """

    if not raw:
        raise ValueError(
            "LLM returned an empty response."
        )

    cleaned = raw.strip()

    # Remove <think>...</think>
    cleaned = re.sub(
        r"<think>.*?</think>",
        "",
        cleaned,
        flags=re.DOTALL | re.IGNORECASE,
    ).strip()

    # Remove ```json
    cleaned = re.sub(
        r"^```json\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    # Remove ```
    cleaned = re.sub(
        r"^```\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    # Remove closing ```
    cleaned = re.sub(
        r"\s*```$",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    return cleaned.strip()


def _parse_schema_response(
    raw: str,
    schema: type[BaseModel],
    provider: str,
) -> BaseModel:
    """
    Convert an LLM response into a Pydantic model.

    Attempts:
      1. Direct Pydantic JSON validation
      2. Extract first JSON object
      3. Standard json.loads
    """

    cleaned = _clean_model_json(raw)

    # --------------------------------------------------------
    # Attempt 1: direct Pydantic validation
    # --------------------------------------------------------

    try:
        return schema.model_validate_json(
            cleaned
        )

    except Exception:
        pass

    # --------------------------------------------------------
    # Attempt 2: extract first JSON object
    # --------------------------------------------------------

    start_index = cleaned.find("{")

    if start_index != -1:

        try:
            decoder = json.JSONDecoder(
                strict=False
            )

            obj, _ = decoder.raw_decode(
                cleaned[start_index:]
            )

            return schema.model_validate(
                obj
            )

        except Exception:
            pass

    # --------------------------------------------------------
    # Attempt 3: normal JSON parser
    # --------------------------------------------------------

    try:
        parsed = json.loads(cleaned)

        return schema.model_validate(
            parsed
        )

    except Exception as e:

        raise ValueError(
            f"{provider} returned invalid JSON "
            f"for {schema.__name__}: "
            f"{cleaned[:1500]}"
        ) from e


# ============================================================
# 7. GEMINI REST API
# ============================================================

def _call_gemini_rest(
    prompt: str,
    model: str = GEMINI_MODEL,
    max_tokens: int = 3500,
    json_mode: bool = True,
) -> str:
    """
    Call Gemini through the REST API.
    """

    if not gemini_api_key:
        raise ValueError(
            "GEMINI_API_KEY is not configured."
        )

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

    # Gemini JSON MIME type.
    if json_mode:
        generation_config[
            "responseMimeType"
        ] = "application/json"

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

    logger.info(
        "Calling Gemini model: %s",
        model,
    )

    try:

        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=45,
        )

    except requests.RequestException as e:

        raise RuntimeError(
            f"Gemini network error: {e}"
        ) from e

    # --------------------------------------------------------
    # HTTP error handling
    # --------------------------------------------------------

    if response.status_code != 200:

        raise RuntimeError(
            f"Gemini API Error "
            f"{response.status_code}: "
            f"{response.text}"
        )

    # --------------------------------------------------------
    # Parse response
    # --------------------------------------------------------

    try:
        data = response.json()

    except Exception as e:

        raise RuntimeError(
            "Gemini returned a non-JSON HTTP response."
        ) from e

    candidates = data.get(
        "candidates",
        []
    )

    if not candidates:

        raise RuntimeError(
            f"Gemini returned no candidates: {data}"
        )

    content = candidates[0].get(
        "content",
        {}
    )

    parts = content.get(
        "parts",
        []
    )

    if not parts:

        raise RuntimeError(
            f"Gemini returned no content parts: {data}"
        )

    text = parts[0].get(
        "text"
    )

    if not text:

        raise RuntimeError(
            f"Gemini returned empty text: {data}"
        )

    return text


# ============================================================
# 8. GEMINI STRUCTURED JSON
# ============================================================

def _call_gemini_json(
    prompt: str,
    schema: type[BaseModel],
    model: str = GEMINI_MODEL,
    max_tokens: int = 3500,
) -> BaseModel:
    """
    Call Gemini and validate the JSON against a Pydantic schema.
    """

    if not gemini_api_key:
        raise ValueError(
            "GEMINI_API_KEY is not configured."
        )

    schema_json = schema.model_json_schema()

    schema_instruction = (
        "\n\n"
        "STRICT OUTPUT REQUIREMENTS:\n"
        "1. Return exactly ONE JSON object.\n"
        "2. Do NOT return Markdown.\n"
        "3. Do NOT return ```json fences.\n"
        "4. Do NOT return explanations.\n"
        "5. The JSON must match this schema:\n"
        f"{json.dumps(schema_json, ensure_ascii=False)}"
    )

    full_prompt = (
        prompt +
        schema_instruction
    )

    raw = _call_gemini_rest(
        full_prompt,
        model=model,
        max_tokens=max_tokens,
        json_mode=True,
    )

    return _parse_schema_response(
        raw,
        schema,
        "Gemini",
    )


# ============================================================
# 9. GROQ STRUCTURED JSON
# ============================================================

def _call_groq_json(
    prompt: str,
    schema: type[BaseModel],
    model: str = GROQ_MODEL,
    max_tokens: int = 3000,
) -> BaseModel:
    """
    Call Groq and validate the returned JSON ourselves.

    IMPORTANT:
    We deliberately DO NOT use Groq response_format here.

    The previous deployment returned:
        json_validate_failed

    So we avoid provider-side JSON schema validation and
    validate the response locally with Pydantic.
    """

    if not groq_client:
        raise ValueError(
            "Groq client is not initialized."
        )

    schema_json = schema.model_json_schema()

    schema_instruction = (
        "\n\n"
        "STRICT OUTPUT REQUIREMENTS:\n"
        "1. Return exactly ONE JSON object.\n"
        "2. Return ONLY JSON.\n"
        "3. Do NOT return Markdown.\n"
        "4. Do NOT use ```json fences.\n"
        "5. Do NOT include explanations.\n"
        "6. Do NOT include reasoning.\n"
        "7. Your response must match this schema:\n"
        f"{json.dumps(schema_json, ensure_ascii=False)}"
    )

    messages = [
        {
            "role": "system",
            "content": (
                "You are a JSON-only educational AI API. "
                "Your entire response must be one valid JSON "
                "object matching the supplied schema. "
                "Never output Markdown, explanations, "
                "reasoning, comments, or code fences."
            ),
        },
        {
            "role": "user",
            "content": (
                prompt +
                schema_instruction
            ),
        },
    ]

    logger.info(
        "Calling Groq model: %s",
        model,
    )

    try:

        completion = (
            groq_client
            .chat
            .completions
            .create(
                model=model,
                messages=messages,
                temperature=0.2,
                max_tokens=min(
                    max_tokens,
                    3000,
                ),
            )
        )

    except Exception as e:

        # Do not retry here.
        # max_retries=0 was set during client creation.
        raise RuntimeError(
            f"Groq request failed: {e}"
        ) from e

    # --------------------------------------------------------
    # Extract response
    # --------------------------------------------------------

    if not completion.choices:

        raise RuntimeError(
            "Groq returned no choices."
        )

    raw = (
        completion
        .choices[0]
        .message
        .content
        or ""
    )

    if not raw.strip():

        raise RuntimeError(
            "Groq returned an empty response."
        )

    return _parse_schema_response(
        raw,
        schema,
        "Groq",
    )


# ============================================================
# 10. MAIN STRUCTURED LLM DISPATCHER
# ============================================================

def call_llm(
    prompt: str,
    schema: type[BaseModel],
    model_type: str = "thinking",
    retries: int = 1,
    max_tokens: int = 3000,
) -> BaseModel:
    """
    Main structured LLM dispatcher.

    FAST:
        Groq -> Gemini

    THINKING:
        Gemini -> Groq

    Only one model per provider is attempted.
    """

    del retries  # Intentionally unused.

    errors = []

    # ========================================================
    # FAST MODE
    # ========================================================

    if model_type == "fast":

        # ----------------------------------------------------
        # Provider 1: Groq
        # ----------------------------------------------------

        if groq_client:

            try:

                logger.info(
                    "Fast LLM request -> Groq (%s)",
                    GROQ_MODEL,
                )

                result = _call_groq_json(
                    prompt=prompt,
                    schema=schema,
                    model=GROQ_MODEL,
                    max_tokens=max_tokens,
                )

                logger.info(
                    "Groq generation successful."
                )

                return result

            except Exception as e:

                errors.append(
                    f"Groq {GROQ_MODEL}: {e}"
                )

                logger.exception(
                    "Groq generation failed."
                )

        # ----------------------------------------------------
        # Provider 2: Gemini
        # ----------------------------------------------------

        if gemini_api_key:

            try:

                logger.info(
                    "Fast LLM fallback -> Gemini (%s)",
                    GEMINI_MODEL,
                )

                result = _call_gemini_json(
                    prompt=prompt,
                    schema=schema,
                    model=GEMINI_MODEL,
                    max_tokens=max_tokens,
                )

                logger.info(
                    "Gemini fallback successful."
                )

                return result

            except Exception as e:

                errors.append(
                    f"Gemini {GEMINI_MODEL}: {e}"
                )

                logger.exception(
                    "Gemini fallback failed."
                )

    # ========================================================
    # THINKING MODE
    # ========================================================

    else:

        # ----------------------------------------------------
        # Provider 1: Gemini
        # ----------------------------------------------------

        if gemini_api_key:

            try:

                logger.info(
                    "Thinking LLM request -> Gemini (%s)",
                    GEMINI_MODEL,
                )

                result = _call_gemini_json(
                    prompt=prompt,
                    schema=schema,
                    model=GEMINI_MODEL,
                    max_tokens=max_tokens,
                )

                logger.info(
                    "Gemini generation successful."
                )

                return result

            except Exception as e:

                errors.append(
                    f"Gemini {GEMINI_MODEL}: {e}"
                )

                logger.exception(
                    "Gemini generation failed."
                )

        # ----------------------------------------------------
        # Provider 2: Groq
        # ----------------------------------------------------

        if groq_client:

            try:

                logger.info(
                    "Thinking LLM fallback -> Groq (%s)",
                    GROQ_MODEL,
                )

                result = _call_groq_json(
                    prompt=prompt,
                    schema=schema,
                    model=GROQ_MODEL,
                    max_tokens=max_tokens,
                )

                logger.info(
                    "Groq fallback successful."
                )

                return result

            except Exception as e:

                errors.append(
                    f"Groq {GROQ_MODEL}: {e}"
                )

                logger.exception(
                    "Groq fallback failed."
                )

    # ========================================================
    # COMPLETE FAILURE
    # ========================================================

    if not errors:

        errors.append(
            "No LLM provider is configured."
        )

    error_message = " | ".join(
        errors
    )

    logger.error(
        "All LLM generation attempts failed: %s",
        error_message,
    )

    raise LLMGenerationError(
        "LLM generation failed across providers: "
        + error_message
    )


# ============================================================
# 11. GROQ PLAIN TEXT GENERATION
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
        raise ValueError(
            "Groq client is not initialized."
        )

    logger.info(
        "Calling Groq text model: %s",
        model,
    )

    completion = (
        groq_client
        .chat
        .completions
        .create(
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
    )

    if not completion.choices:

        raise RuntimeError(
            "Groq returned no choices."
        )

    raw = (
        completion
        .choices[0]
        .message
        .content
        or ""
    )

    return re.sub(
        r"<think>.*?</think>",
        "",
        raw,
        flags=re.DOTALL,
    ).strip()


# ============================================================
# 12. GEMINI PLAIN TEXT GENERATION
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

        raise ValueError(
            "GEMINI_API_KEY is not configured."
        )

    logger.info(
        "Calling Gemini text model: %s",
        model,
    )

    raw = _call_gemini_rest(
        prompt=prompt,
        model=model,
        max_tokens=max_tokens,
        json_mode=False,
    )

    return (raw or "").strip()


# ============================================================
# 13. TEXT LLM DISPATCHER
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

    del retries

    errors = []

    # ========================================================
    # FAST
    # ========================================================

    if model_type == "fast":

        # ----------------------------------------------------
        # Groq
        # ----------------------------------------------------

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

                logger.exception(
                    "Groq text generation failed."
                )

        # ----------------------------------------------------
        # Gemini fallback
        # ----------------------------------------------------

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

                logger.exception(
                    "Gemini text generation failed."
                )

    # ========================================================
    # THINKING
    # ========================================================

    else:

        # ----------------------------------------------------
        # Gemini
        # ----------------------------------------------------

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

                logger.exception(
                    "Gemini text generation failed."
                )

        # ----------------------------------------------------
        # Groq fallback
        # ----------------------------------------------------

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

                logger.exception(
                    "Groq text fallback failed."
                )

    # ========================================================
    # COMPLETE FAILURE
    # ========================================================

    if not errors:

        errors.append(
            "No LLM provider is configured."
        )

    error_message = " | ".join(
        errors
    )

    logger.error(
        "LLM text generation failed: %s",
        error_message,
    )

    raise LLMGenerationError(
        "LLM text generation failed: "
        + error_message
    )

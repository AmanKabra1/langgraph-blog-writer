"""Provider clients.

Groq goes through langchain-groq (we need structured output). Tavily and Gemini
are called over plain REST with `requests` — both APIs are simple, and dropping
their SDKs keeps the deploy image small and immune to SDK churn.
"""

from __future__ import annotations

import base64
from typing import Any, Dict, List, Optional, Tuple, Type, TypeVar

import requests
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_groq import ChatGroq
from pydantic import BaseModel

from .config import RunConfig

T = TypeVar("T", bound=BaseModel)

GROQ_MODELS_URL = "https://api.groq.com/openai/v1/models"
TAVILY_SEARCH_URL = "https://api.tavily.com/search"
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"


# ======================================================================
# Groq
# ======================================================================
def make_llm(cfg: RunConfig) -> BaseChatModel:
    return ChatGroq(
        model=cfg.model,
        api_key=cfg.groq_api_key,
        temperature=cfg.temperature,
        max_tokens=cfg.max_tokens,
        timeout=cfg.request_timeout,
        max_retries=cfg.max_retries,
    )


def structured(llm: BaseChatModel, schema: Type[T], messages: list) -> T:
    """Invoke `llm` for a structured `schema`, degrading through methods.

    Groq's function-calling path is the most reliable but not every model
    exposes it, so fall back to json_schema and then json_mode rather than
    failing the whole run.
    """
    last_error: Optional[Exception] = None
    for method in ("function_calling", "json_schema", "json_mode"):
        try:
            runnable = llm.with_structured_output(schema, method=method)
            result = runnable.invoke(messages)
            if isinstance(result, schema):
                return result
            if isinstance(result, dict):
                return schema(**result)
        except Exception as exc:  # noqa: BLE001 - try the next method
            last_error = exc
    raise RuntimeError(
        f"Could not get a valid {schema.__name__} from the model. Last error: {last_error}"
    ) from last_error


def validate_groq_key(api_key: str, timeout: int = 15) -> Tuple[bool, str]:
    if not api_key.strip():
        return False, "No key provided."
    try:
        resp = requests.get(
            GROQ_MODELS_URL,
            headers={"Authorization": f"Bearer {api_key.strip()}"},
            timeout=timeout,
        )
    except requests.RequestException as exc:
        return False, f"Network error: {exc}"
    if resp.status_code == 200:
        ids = [m.get("id", "") for m in resp.json().get("data", [])]
        return True, f"Valid — {len(ids)} models available."
    if resp.status_code in (401, 403):
        return False, "Rejected — key is invalid or revoked."
    return False, f"HTTP {resp.status_code}: {resp.text[:180]}"


# ======================================================================
# Tavily
# ======================================================================
def tavily_search(
    api_key: str,
    query: str,
    max_results: int = 5,
    search_depth: str = "basic",
    days: Optional[int] = None,
    timeout: int = 30,
) -> List[Dict[str, Any]]:
    """Run one Tavily search. Returns [] on any failure — research is optional."""
    if not api_key.strip():
        return []

    payload: Dict[str, Any] = {
        "query": query,
        "max_results": max(1, min(int(max_results), 20)),
        "search_depth": search_depth,
        "include_answer": False,
        "include_raw_content": False,
    }
    # `days` only applies to the news topic; sending it otherwise is a 4xx.
    if days is not None and days <= 365:
        payload["topic"] = "news"
        payload["days"] = max(1, int(days))

    try:
        resp = requests.post(
            TAVILY_SEARCH_URL,
            headers={
                "Authorization": f"Bearer {api_key.strip()}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException:
        return []
    except ValueError:
        return []

    out: List[Dict[str, Any]] = []
    for item in data.get("results", []) or []:
        url = item.get("url") or ""
        if not url:
            continue
        out.append(
            {
                "title": item.get("title") or url,
                "url": url,
                "snippet": (item.get("content") or "")[:600],
                "published_at": item.get("published_date") or item.get("published_at"),
                "source": item.get("source"),
            }
        )
    return out


def validate_tavily_key(api_key: str, timeout: int = 20) -> Tuple[bool, str]:
    if not api_key.strip():
        return False, "No key provided."
    try:
        resp = requests.post(
            TAVILY_SEARCH_URL,
            headers={"Authorization": f"Bearer {api_key.strip()}"},
            json={"query": "test", "max_results": 1},
            timeout=timeout,
        )
    except requests.RequestException as exc:
        return False, f"Network error: {exc}"
    if resp.status_code == 200:
        return True, "Valid — search is live."
    if resp.status_code in (401, 403):
        return False, "Rejected — key is invalid."
    if resp.status_code == 432:
        return False, "Valid key, but the free search quota is exhausted."
    return False, f"HTTP {resp.status_code}: {resp.text[:180]}"


# ======================================================================
# Gemini images
# ======================================================================
def gemini_generate_image(
    api_key: str,
    prompt: str,
    model: str = "gemini-2.5-flash-image",
    timeout: int = 120,
) -> bytes:
    """Generate one image and return raw bytes. Raises on failure."""
    if not api_key.strip():
        raise RuntimeError("No Google API key provided.")

    url = f"{GEMINI_BASE}/models/{model}:generateContent"
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"responseModalities": ["IMAGE"]},
    }

    resp = requests.post(
        url,
        headers={"x-goog-api-key": api_key.strip(), "Content-Type": "application/json"},
        json=body,
        timeout=timeout,
    )
    if resp.status_code != 200:
        detail = resp.text[:300]
        if resp.status_code == 429:
            raise RuntimeError("Gemini rate limit / daily free quota reached.")
        if resp.status_code in (401, 403):
            raise RuntimeError("Google API key rejected for image generation.")
        raise RuntimeError(f"Gemini HTTP {resp.status_code}: {detail}")

    data = resp.json()
    candidates = data.get("candidates") or []
    if not candidates:
        reason = (data.get("promptFeedback") or {}).get("blockReason", "unknown")
        raise RuntimeError(f"No image returned (blocked: {reason}).")

    parts = ((candidates[0].get("content") or {}).get("parts")) or []
    for part in parts:
        inline = part.get("inlineData") or part.get("inline_data")
        if inline and inline.get("data"):
            return base64.b64decode(inline["data"])

    finish = candidates[0].get("finishReason", "unknown")
    raise RuntimeError(f"Response contained no image data (finishReason={finish}).")


def validate_google_key(api_key: str, timeout: int = 20) -> Tuple[bool, str]:
    if not api_key.strip():
        return False, "No key provided."
    try:
        resp = requests.get(
            f"{GEMINI_BASE}/models",
            headers={"x-goog-api-key": api_key.strip()},
            timeout=timeout,
        )
    except requests.RequestException as exc:
        return False, f"Network error: {exc}"
    if resp.status_code == 200:
        names = [m.get("name", "") for m in resp.json().get("models", [])]
        image_models = [n for n in names if "image" in n]
        return True, f"Valid — {len(names)} models, {len(image_models)} image-capable."
    if resp.status_code in (400, 401, 403):
        return False, "Rejected — key is invalid or the Generative Language API is not enabled."
    return False, f"HTTP {resp.status_code}: {resp.text[:180]}"

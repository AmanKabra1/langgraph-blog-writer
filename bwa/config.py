"""Runtime configuration.

Everything here is driven by the UI. Nothing is read from the environment at
import time, so the app can boot with zero credentials and ask for them in the
browser instead.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date
from typing import List, Literal, Optional

# ------------------------------------------------------------------
# Model catalogues
#
# Groq retires models aggressively. Everything listed here is a current
# production model as of August 2026; `llama-3.3-70b-versatile` and
# `llama-3.1-8b-instant` are both scheduled for shutdown on 2026-08-16, so they
# are deliberately excluded.
# ------------------------------------------------------------------
TEXT_MODELS: List[str] = [
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "qwen/qwen3.6-27b",
    "groq/compound",
    "groq/compound-mini",
]

DEFAULT_TEXT_MODEL = "openai/gpt-oss-120b"

# gemini-2.5-flash-image ("Nano Banana") has a free tier of ~500 images/day.
# gemini-3-pro-image-preview is paid-only — offered but flagged in the UI.
IMAGE_MODELS: List[str] = [
    "gemini-2.5-flash-image",
    "gemini-3.1-flash-image-preview",
    "gemini-3-pro-image-preview",
]

DEFAULT_IMAGE_MODEL = "gemini-2.5-flash-image"

FREE_TIER_IMAGE_MODELS = {"gemini-2.5-flash-image", "gemini-3.1-flash-image-preview"}

Mode = Literal["auto", "closed_book", "hybrid", "open_book"]
BlogKind = Literal[
    "auto", "explainer", "tutorial", "news_roundup", "comparison", "system_design"
]


@dataclass
class RunConfig:
    """One generation run's settings. Built from the sidebar, never from disk."""

    # --- credentials (all UI-supplied) ---
    groq_api_key: str = ""
    tavily_api_key: str = ""
    google_api_key: str = ""

    # --- text model ---
    model: str = DEFAULT_TEXT_MODEL
    temperature: float = 0.4
    max_tokens: Optional[int] = None
    request_timeout: int = 120
    max_retries: int = 3

    # --- research ---
    enable_research: bool = True
    force_mode: Mode = "auto"
    max_queries: int = 6
    results_per_query: int = 5
    search_depth: Literal["basic", "advanced"] = "basic"

    # --- images ---
    enable_images: bool = True
    image_model: str = DEFAULT_IMAGE_MODEL
    max_images: int = 3

    # --- editorial ---
    as_of: str = field(default_factory=lambda: date.today().isoformat())
    blog_kind: BlogKind = "auto"
    audience: str = ""
    tone: str = ""
    min_sections: int = 5
    max_sections: int = 9
    constraints: List[str] = field(default_factory=list)

    # ------------------------------------------------------------------
    @property
    def research_available(self) -> bool:
        return bool(self.enable_research and self.tavily_api_key.strip())

    @property
    def images_available(self) -> bool:
        return bool(self.enable_images and self.google_api_key.strip())

    def validate(self) -> List[str]:
        """Return a list of human-readable problems, empty if good to run."""
        problems: List[str] = []
        if not self.groq_api_key.strip():
            problems.append("A Groq API key is required — the writer cannot run without it.")
        if self.model not in TEXT_MODELS:
            problems.append(f"Unknown text model: {self.model}")
        if self.min_sections < 3:
            problems.append("Minimum sections must be at least 3.")
        if self.max_sections < self.min_sections:
            problems.append("Maximum sections must be >= minimum sections.")
        if not (1 <= self.max_images <= 6):
            problems.append("Image count must be between 1 and 6.")
        try:
            date.fromisoformat(self.as_of)
        except ValueError:
            problems.append(f"As-of date is not a valid ISO date: {self.as_of!r}")
        return problems


def env_default(name: str) -> str:
    """Seed a UI field from the environment or Streamlit secrets, if present.

    This is a convenience only — the app never *requires* it. On Streamlit
    Community Cloud, values set in the app's Secrets panel show up as env vars,
    so a deployed instance can pre-fill its own keys.
    """
    value = os.environ.get(name, "")
    if value:
        return value
    try:  # pragma: no cover - streamlit is optional at import time
        import streamlit as st

        return str(st.secrets.get(name, ""))
    except Exception:
        return ""

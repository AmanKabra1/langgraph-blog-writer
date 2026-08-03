"""Pydantic schemas shared by the graph nodes and the UI."""

from __future__ import annotations

import operator
from typing import Annotated, List, Literal, Optional, Tuple, TypedDict

from pydantic import BaseModel, Field


class Task(BaseModel):
    id: int
    title: str
    goal: str = Field(..., description="One sentence: what the reader should do or understand.")
    bullets: List[str] = Field(..., min_length=3, max_length=6)
    target_words: int = Field(300, description="Target words (120-550).")

    tags: List[str] = Field(default_factory=list)
    requires_research: bool = False
    requires_citations: bool = False
    requires_code: bool = False


class Plan(BaseModel):
    blog_title: str
    audience: str
    tone: str
    blog_kind: Literal[
        "explainer", "tutorial", "news_roundup", "comparison", "system_design"
    ] = "explainer"
    constraints: List[str] = Field(default_factory=list)
    tasks: List[Task]


class EvidenceItem(BaseModel):
    title: str
    url: str
    published_at: Optional[str] = None  # ISO "YYYY-MM-DD" preferred
    snippet: Optional[str] = None
    source: Optional[str] = None


class RouterDecision(BaseModel):
    needs_research: bool
    mode: Literal["closed_book", "hybrid", "open_book"]
    reason: str
    queries: List[str] = Field(default_factory=list)


class EvidencePack(BaseModel):
    evidence: List[EvidenceItem] = Field(default_factory=list)


class ImageSpec(BaseModel):
    placeholder: str = Field(..., description="e.g. [[IMAGE_1]]")
    filename: str = Field(..., description="e.g. qkv_flow.png")
    alt: str
    caption: str
    prompt: str = Field(..., description="Prompt to send to the image model.")


class GlobalImagePlan(BaseModel):
    md_with_placeholders: str
    images: List[ImageSpec] = Field(default_factory=list)


class State(TypedDict, total=False):
    topic: str

    # routing / research
    mode: str
    needs_research: bool
    router_reason: str
    queries: List[str]
    evidence: List[dict]
    plan: Optional[dict]

    # recency
    as_of: str
    recency_days: int

    # workers — reduced with `+` so parallel branches can all append
    sections: Annotated[List[Tuple[int, str]], operator.add]

    # reducer / images
    merged_md: str
    md_with_placeholders: str
    image_specs: List[dict]
    # filename -> base64 PNG. Kept in memory so the app works on read-only hosts.
    images_b64: dict
    image_errors: List[str]

    final: str
    warnings: Annotated[List[str], operator.add]

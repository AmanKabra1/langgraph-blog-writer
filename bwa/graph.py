"""The LangGraph pipeline.

    router -> [research] -> orchestrator -> N x worker -> merge -> plan_images -> render

The graph is built per run by `build_graph(cfg)` so that UI-supplied keys and
model choices are captured in the node closures. Nothing is read from the
environment and nothing is written to disk — generated images live in state as
base64, which is what lets this run unchanged on a read-only cloud host.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from .config import RunConfig
from .providers import gemini_generate_image, make_llm, structured, tavily_search
from .schemas import (
    EvidenceItem,
    EvidencePack,
    GlobalImagePlan,
    Plan,
    RouterDecision,
    State,
    Task,
)

RECENCY_BY_MODE = {"open_book": 7, "hybrid": 45, "closed_book": 3650}


# ======================================================================
# Prompts
# ======================================================================
ROUTER_SYSTEM = """You are a routing module for a technical blog planner.

Decide whether web research is needed BEFORE planning.

Modes:
- closed_book (needs_research=false): evergreen concepts that do not depend on current events.
- hybrid (needs_research=true): evergreen core, but needs up-to-date examples, tools, models or numbers.
- open_book (needs_research=true): volatile — weekly news, "latest", pricing, policy, releases.

If needs_research=true, output 3-10 high-signal, scoped search queries.
For an open_book weekly roundup, phrase queries so they surface the last 7 days.
"""

RESEARCH_SYSTEM = """You are a research synthesizer.

Given raw web search results, produce EvidenceItem objects.

Rules:
- Only include items with a non-empty url.
- Prefer relevant and authoritative sources.
- Normalize published_at to ISO YYYY-MM-DD only if reliably inferable; otherwise null. Never guess a date.
- Keep snippets under 40 words.
- Deduplicate by URL.
"""

ORCH_SYSTEM = """You are a senior technical writer and developer advocate.
Produce a highly actionable outline for a technical blog post.

Requirements:
- Between {min_sections} and {max_sections} tasks, each with a goal, 3-6 bullets, and target_words.
- target_words must be between 120 and 550.
- Task ids must start at 1 and increase by 1.
- Tags are flexible; do not force a fixed taxonomy.

Grounding:
- closed_book: evergreen, no dependence on evidence.
- hybrid: use evidence for up-to-date examples; mark those tasks requires_research=true and requires_citations=true.
- open_book: weekly/news roundup —
  - set blog_kind="news_roundup"
  - no tutorial content unless explicitly requested
  - if evidence is weak, say so in the plan; never invent events.
"""

WORKER_SYSTEM = """You are a senior technical writer and developer advocate.
Write ONE section of a technical blog post in Markdown.

Constraints:
- Cover ALL bullets, in order.
- Hit the target word count within 15%.
- Output only the section markdown, starting with "## <Section Title>". No preamble, no closing remarks.

Scope guard:
- If blog_kind == "news_roundup", do not drift into tutorials (scraping, RSS, how to fetch).
  Focus on the events and their implications.

Grounding:
- If mode == "open_book": do not state any specific event, company, model, funding or policy claim
  unless it is supported by a provided Evidence URL. Attach a Markdown link ([Source](URL)) to each
  supported claim. If a bullet cannot be supported, write "Not found in provided sources."
- If requires_citations is true, cite Evidence URLs for every external claim.

Code:
- If requires_code is true, include at least one minimal, runnable snippet in a fenced block.
"""

DECIDE_IMAGES_SYSTEM = """You are an expert technical editor deciding on diagrams for a blog post.

Rules:
- At most {max_images} images.
- Each image must materially improve understanding: an architecture diagram, a data flow, a
  comparison visual. Never decorative.
- Insert placeholders into the markdown exactly as [[IMAGE_1]], [[IMAGE_2]], ... on their own line,
  immediately after the paragraph they illustrate.
- md_with_placeholders must be the FULL original markdown with only the placeholder lines added.
  Do not summarize, truncate, or rewrite the prose.
- If no images are warranted, return md_with_placeholders unchanged and images=[].
- filename must be lowercase, end in .png, and be unique.
- prompt must describe a clean, labelled technical diagram on a plain background — no photorealism.
"""


# ======================================================================
# Helpers
# ======================================================================
def safe_slug(title: str) -> str:
    s = (title or "").strip().lower()
    s = re.sub(r"[^a-z0-9 _-]+", "", s)
    s = re.sub(r"\s+", "_", s).strip("_")
    return s or "blog"


def _iso_to_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _safe_filename(name: str, index: int) -> str:
    stem = re.sub(r"[^a-z0-9_-]+", "_", (name or "").lower().rsplit(".", 1)[0]).strip("_")
    return f"{stem or f'figure_{index}'}.png"


# ======================================================================
# Graph factory
# ======================================================================
def build_graph(cfg: RunConfig):
    """Compile a graph whose nodes close over this run's configuration."""

    llm = make_llm(cfg)

    # ---------------- router ----------------
    def router_node(state: State) -> dict:
        # An explicit mode from the UI skips the routing LLM call entirely.
        if cfg.force_mode != "auto":
            mode = cfg.force_mode
            needs = mode != "closed_book"
            queries: List[str] = []
            if needs:
                queries = [state["topic"]]
                try:
                    decision = structured(
                        llm,
                        RouterDecision,
                        [
                            SystemMessage(content=ROUTER_SYSTEM),
                            HumanMessage(
                                content=(
                                    f"Topic: {state['topic']}\n"
                                    f"As-of date: {state['as_of']}\n"
                                    f"The mode is already fixed to {mode}. "
                                    f"Return that mode and produce the search queries."
                                )
                            ),
                        ],
                    )
                    queries = decision.queries or queries
                except Exception:
                    pass  # a single-query fallback is better than failing the run
            return {
                "mode": mode,
                "needs_research": needs and cfg.research_available,
                "router_reason": f"Mode forced to {mode} from the UI.",
                "queries": queries[: cfg.max_queries],
                "recency_days": RECENCY_BY_MODE[mode],
            }

        decision = structured(
            llm,
            RouterDecision,
            [
                SystemMessage(content=ROUTER_SYSTEM),
                HumanMessage(
                    content=f"Topic: {state['topic']}\nAs-of date: {state['as_of']}"
                ),
            ],
        )

        warnings: List[str] = []
        needs = decision.needs_research
        if needs and not cfg.research_available:
            warnings.append(
                "The router wanted web research, but no Tavily key is configured — "
                "falling back to closed-book. Claims will not be sourced."
            )
            needs = False

        return {
            "mode": decision.mode,
            "needs_research": needs,
            "router_reason": decision.reason,
            "queries": decision.queries[: cfg.max_queries],
            "recency_days": RECENCY_BY_MODE.get(decision.mode, 3650),
            "warnings": warnings,
        }

    def route_next(state: State) -> str:
        return "research" if state.get("needs_research") else "orchestrator"

    # ---------------- research ----------------
    def research_node(state: State) -> dict:
        queries = (state.get("queries") or [])[: cfg.max_queries]
        mode = state.get("mode", "hybrid")
        days = int(state.get("recency_days", 3650)) if mode == "open_book" else None

        raw: List[Dict[str, Any]] = []
        for query in queries:
            raw.extend(
                tavily_search(
                    cfg.tavily_api_key,
                    query,
                    max_results=cfg.results_per_query,
                    search_depth=cfg.search_depth,
                    days=days,
                )
            )

        if not raw:
            return {
                "evidence": [],
                "warnings": [
                    "Web search returned nothing. Check the Tavily key/quota, or the "
                    "queries were too narrow. The post will be written unsourced."
                ],
            }

        try:
            pack = structured(
                llm,
                EvidencePack,
                [
                    SystemMessage(content=RESEARCH_SYSTEM),
                    HumanMessage(
                        content=(
                            f"As-of date: {state['as_of']}\n"
                            f"Recency window: {state.get('recency_days')} days\n\n"
                            f"Raw results:\n{raw[:40]}"
                        )
                    ),
                ],
            )
            items = pack.evidence
        except Exception:
            # If synthesis fails, the raw hits are still perfectly usable.
            items = [EvidenceItem(**r) for r in raw]

        dedup: Dict[str, EvidenceItem] = {}
        for item in items:
            if item.url:
                dedup.setdefault(item.url, item)
        evidence = list(dedup.values())

        warnings: List[str] = []
        if mode == "open_book":
            as_of = _iso_to_date(state["as_of"]) or date.today()
            cutoff = as_of - timedelta(days=int(state.get("recency_days", 7)))
            fresh = [
                e for e in evidence if (d := _iso_to_date(e.published_at)) and d >= cutoff
            ]
            if fresh:
                evidence = fresh
            elif evidence:
                warnings.append(
                    f"No source carried a confirmed date within {state.get('recency_days')} days. "
                    "Keeping undated results rather than dropping all evidence — verify recency manually."
                )

        return {"evidence": [e.model_dump() for e in evidence], "warnings": warnings}

    # ---------------- orchestrator ----------------
    def orchestrator_node(state: State) -> dict:
        mode = state.get("mode", "closed_book")
        evidence = state.get("evidence", []) or []

        editorial = []
        if cfg.audience.strip():
            editorial.append(f"Audience must be: {cfg.audience.strip()}")
        if cfg.tone.strip():
            editorial.append(f"Tone must be: {cfg.tone.strip()}")
        if cfg.blog_kind != "auto":
            editorial.append(f"blog_kind must be exactly: {cfg.blog_kind}")
        if cfg.constraints:
            editorial.append("Extra constraints: " + "; ".join(cfg.constraints))

        forced_kind = "news_roundup" if mode == "open_book" and cfg.blog_kind == "auto" else None

        plan = structured(
            llm,
            Plan,
            [
                SystemMessage(
                    content=ORCH_SYSTEM.format(
                        min_sections=cfg.min_sections, max_sections=cfg.max_sections
                    )
                ),
                HumanMessage(
                    content=(
                        f"Topic: {state['topic']}\n"
                        f"Mode: {mode}\n"
                        f"As-of: {state['as_of']} (recency_days={state.get('recency_days')})\n"
                        + ("\n".join(editorial) + "\n" if editorial else "")
                        + (f"Force blog_kind=news_roundup\n" if forced_kind else "")
                        + f"\nEvidence ({len(evidence)} items):\n{evidence[:16]}"
                    )
                ),
            ],
        )

        if forced_kind:
            plan.blog_kind = "news_roundup"
        elif cfg.blog_kind != "auto":
            plan.blog_kind = cfg.blog_kind
        if cfg.audience.strip():
            plan.audience = cfg.audience.strip()
        if cfg.tone.strip():
            plan.tone = cfg.tone.strip()

        # Normalize ids so ordering in the reducer is deterministic.
        for index, task in enumerate(plan.tasks, start=1):
            task.id = index
            task.target_words = max(120, min(int(task.target_words or 300), 550))

        warnings: List[str] = []
        if len(plan.tasks) < cfg.min_sections:
            warnings.append(
                f"The planner produced {len(plan.tasks)} sections, below your minimum of {cfg.min_sections}."
            )

        return {"plan": plan.model_dump(), "warnings": warnings}

    # ---------------- fanout ----------------
    def fanout(state: State):
        plan = state.get("plan")
        if not plan:
            raise ValueError("Orchestrator produced no plan.")
        return [
            Send(
                "worker",
                {
                    "task": task,
                    "topic": state["topic"],
                    "mode": state.get("mode"),
                    "as_of": state.get("as_of"),
                    "recency_days": state.get("recency_days"),
                    "plan": plan,
                    "evidence": state.get("evidence", []),
                },
            )
            for task in plan["tasks"]
        ]

    # ---------------- worker ----------------
    def worker_node(payload: dict) -> dict:
        task = Task(**payload["task"])
        plan = Plan(**payload["plan"])
        evidence = [EvidenceItem(**e) for e in payload.get("evidence", [])]

        bullets_text = "\n- " + "\n- ".join(task.bullets)
        evidence_text = (
            "\n".join(
                f"- {e.title} | {e.url} | {e.published_at or 'date:unknown'}"
                for e in evidence[:20]
            )
            or "(none provided)"
        )

        try:
            section_md = llm.invoke(
                [
                    SystemMessage(content=WORKER_SYSTEM),
                    HumanMessage(
                        content=(
                            f"Blog title: {plan.blog_title}\n"
                            f"Audience: {plan.audience}\n"
                            f"Tone: {plan.tone}\n"
                            f"Blog kind: {plan.blog_kind}\n"
                            f"Constraints: {plan.constraints}\n"
                            f"Topic: {payload['topic']}\n"
                            f"Mode: {payload.get('mode')}\n"
                            f"As-of: {payload.get('as_of')} "
                            f"(recency_days={payload.get('recency_days')})\n\n"
                            f"Section title: {task.title}\n"
                            f"Goal: {task.goal}\n"
                            f"Target words: {task.target_words}\n"
                            f"Tags: {task.tags}\n"
                            f"requires_research: {task.requires_research}\n"
                            f"requires_citations: {task.requires_citations}\n"
                            f"requires_code: {task.requires_code}\n"
                            f"Bullets:{bullets_text}\n\n"
                            f"Evidence (ONLY cite these URLs):\n{evidence_text}\n"
                        )
                    ),
                ]
            ).content
        except Exception as exc:  # one failed section must not kill the post
            return {
                "sections": [
                    (
                        task.id,
                        f"## {task.title}\n\n> This section could not be generated: {exc}\n",
                    )
                ],
                "warnings": [f"Section {task.id} ({task.title}) failed: {exc}"],
            }

        section_md = (section_md or "").strip()
        if not section_md.lstrip().startswith("#"):
            section_md = f"## {task.title}\n\n{section_md}"

        return {"sections": [(task.id, section_md)]}

    # ---------------- merge ----------------
    def merge_content(state: State) -> dict:
        plan = state.get("plan")
        if not plan:
            raise ValueError("merge_content ran without a plan.")
        ordered = [md for _, md in sorted(state.get("sections", []), key=lambda x: x[0])]
        body = "\n\n".join(ordered).strip()
        return {"merged_md": f"# {plan['blog_title']}\n\n{body}\n"}

    # ---------------- image planning ----------------
    def plan_images(state: State) -> dict:
        merged = state.get("merged_md", "")
        if not cfg.images_available:
            return {"md_with_placeholders": merged, "image_specs": []}

        plan = state.get("plan") or {}
        try:
            image_plan = structured(
                llm,
                GlobalImagePlan,
                [
                    SystemMessage(
                        content=DECIDE_IMAGES_SYSTEM.format(max_images=cfg.max_images)
                    ),
                    HumanMessage(
                        content=(
                            f"Blog kind: {plan.get('blog_kind')}\n"
                            f"Topic: {state['topic']}\n\n"
                            "Return the full markdown with placeholders inserted, plus the image specs.\n\n"
                            f"{merged}"
                        )
                    ),
                ],
            )
        except Exception as exc:
            return {
                "md_with_placeholders": merged,
                "image_specs": [],
                "warnings": [f"Image planning failed, continuing without images: {exc}"],
            }

        specs = image_plan.images[: cfg.max_images]
        md = image_plan.md_with_placeholders or merged

        warnings: List[str] = []
        # Guard against the model rewriting/truncating the post under the guise of
        # "inserting placeholders" — fall back to the merged text if it shrank.
        if len(md) < len(merged) * 0.8:
            md = merged
            specs = []
            warnings.append(
                "The image planner rewrote the article instead of only adding placeholders. "
                "Kept the original text and skipped images."
            )

        seen: set[str] = set()
        cleaned = []
        for index, spec in enumerate(specs, start=1):
            spec.placeholder = f"[[IMAGE_{index}]]"
            filename = _safe_filename(spec.filename, index)
            while filename in seen:
                filename = f"{filename[:-4]}_{index}.png"
            seen.add(filename)
            spec.filename = filename
            if spec.placeholder in md:
                cleaned.append(spec)

        return {
            "md_with_placeholders": md,
            "image_specs": [s.model_dump() for s in cleaned],
            "warnings": warnings,
        }

    # ---------------- render ----------------
    def render_final(state: State) -> dict:
        md = state.get("md_with_placeholders") or state.get("merged_md", "")
        specs = state.get("image_specs", []) or []

        if not specs:
            md = re.sub(r"\[\[IMAGE_\d+\]\]\n?", "", md)
            return {"final": md, "images_b64": {}, "image_errors": []}

        import base64

        images_b64: Dict[str, str] = {}
        errors: List[str] = []

        for spec in specs:
            placeholder = spec["placeholder"]
            filename = spec["filename"]
            try:
                data = gemini_generate_image(
                    cfg.google_api_key, spec["prompt"], model=cfg.image_model
                )
                images_b64[filename] = base64.b64encode(data).decode("ascii")
                md = md.replace(
                    placeholder,
                    f"![{spec['alt']}](images/{filename})\n*{spec['caption']}*",
                )
            except Exception as exc:
                errors.append(f"{filename}: {exc}")
                md = md.replace(
                    placeholder,
                    (
                        f"> **[Image not generated]** {spec.get('caption', '')}\n>\n"
                        f"> _Prompt:_ {spec.get('prompt', '')}\n>\n"
                        f"> _Reason:_ {exc}\n"
                    ),
                )

        md = re.sub(r"\[\[IMAGE_\d+\]\]\n?", "", md)
        return {
            "final": md,
            "images_b64": images_b64,
            "image_errors": errors,
            "warnings": [f"{len(errors)} image(s) failed to generate."] if errors else [],
        }

    # ---------------- wiring ----------------
    graph = StateGraph(State)
    graph.add_node("router", router_node)
    graph.add_node("research", research_node)
    graph.add_node("orchestrator", orchestrator_node)
    graph.add_node("worker", worker_node)
    graph.add_node("merge", merge_content)
    graph.add_node("plan_images", plan_images)
    graph.add_node("render", render_final)

    graph.add_edge(START, "router")
    graph.add_conditional_edges(
        "router", route_next, {"research": "research", "orchestrator": "orchestrator"}
    )
    graph.add_edge("research", "orchestrator")
    graph.add_conditional_edges("orchestrator", fanout, ["worker"])
    graph.add_edge("worker", "merge")
    graph.add_edge("merge", "plan_images")
    graph.add_edge("plan_images", "render")
    graph.add_edge("render", END)

    return graph.compile()


def initial_state(topic: str, cfg: RunConfig) -> dict:
    return {
        "topic": topic.strip(),
        "mode": "",
        "needs_research": False,
        "router_reason": "",
        "queries": [],
        "evidence": [],
        "plan": None,
        "as_of": cfg.as_of,
        "recency_days": 3650,
        "sections": [],
        "merged_md": "",
        "md_with_placeholders": "",
        "image_specs": [],
        "images_b64": {},
        "image_errors": [],
        "final": "",
        "warnings": [],
    }

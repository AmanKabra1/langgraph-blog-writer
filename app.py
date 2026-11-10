"""Blog Writing Agent — Streamlit front end.

Everything is configured in the browser: API keys, model, research and image
toggles, editorial settings. No .env file and no disk writes are required, so
this file is also the deployment entry point (Streamlit Community Cloud, HF
Spaces, Docker — all run `streamlit run app.py`).
"""

from __future__ import annotations

import base64
import json
import time
import traceback
from datetime import date, datetime
from typing import Any, Dict, List

import pandas as pd
import streamlit as st

from bwa import __version__, theme
from bwa.auth import gate
from bwa.usage import all_usage_today, quota_for, record_run
from bwa.config import (
    DEFAULT_IMAGE_MODEL,
    DEFAULT_TEXT_MODEL,
    FREE_TIER_IMAGE_MODELS,
    IMAGE_MODELS,
    TEXT_MODELS,
    RunConfig,
    env_default,
)
from bwa.exporters import (
    bundle_zip,
    images_zip,
    read_time_minutes,
    split_markdown_images,
    to_standalone_html,
    word_count,
)
from bwa.graph import build_graph, initial_state, safe_slug
from bwa.providers import validate_google_key, validate_groq_key, validate_tavily_key

st.set_page_config(
    page_title="Blog Writing Agent",
    page_icon="✍️",
    layout="wide",
    # "auto" keeps the sidebar docked on desktop but collapsed on phones, where
    # an expanded drawer would cover the whole app on first load.
    initial_sidebar_state="auto",
    menu_items={"about": f"LangGraph Blog Writing Agent v{__version__}"},
)
theme.inject()

# Halts here with a sign-in screen on a hosted deployment; a no-op locally.
access = gate()
quota = quota_for(access.email, access.daily_limit)


# ======================================================================
# Session state
# ======================================================================
DEFAULTS: Dict[str, Any] = {
    "groq_key": env_default("GROQ_API_KEY"),
    "tavily_key": env_default("TAVILY_API_KEY"),
    "google_key": env_default("GOOGLE_API_KEY"),
    "own_keys": False,      # hosted users may opt out of the shared credentials
    "key_status": {},
    "history": [],          # newest first: {id, title, topic, md, images_b64, ...}
    "active_id": None,
    "run_log": [],
    "is_running": False,
}
for key, value in DEFAULTS.items():
    st.session_state.setdefault(key, value)


def active_run() -> Dict[str, Any] | None:
    for item in st.session_state["history"]:
        if item["id"] == st.session_state["active_id"]:
            return item
    return st.session_state["history"][0] if st.session_state["history"] else None


def render_key_inputs() -> None:
    """The bring-your-own-key panel. Shown when there are no shared keys, or
    when a signed-in visitor has chosen to use their own."""
    with st.expander("🔑 API keys", expanded=not st.session_state["groq_key"]):
        st.caption(
            "Keys live in this browser session only — never written to disk, "
            "never committed. All three providers have a free tier."
        )
        st.session_state["groq_key"] = st.text_input(
            "Groq API key  ·  required",
            value=st.session_state["groq_key"],
            type="password",
            placeholder="gsk_...",
            help="Free, no card. Create one at console.groq.com/keys",
        )
        st.session_state["tavily_key"] = st.text_input(
            "Tavily API key  ·  optional",
            value=st.session_state["tavily_key"],
            type="password",
            placeholder="tvly-...",
            help="Free 1,000 searches/month at app.tavily.com. Enables web research.",
        )
        st.session_state["google_key"] = st.text_input(
            "Google AI key  ·  optional",
            value=st.session_state["google_key"],
            type="password",
            placeholder="AIza...",
            help="Free tier at aistudio.google.com/apikey. Enables diagram generation.",
        )

        if st.button("Test keys", width="stretch"):
            status: Dict[str, Any] = {}
            with st.spinner("Checking…"):
                status["groq"] = validate_groq_key(st.session_state["groq_key"])
                if st.session_state["tavily_key"].strip():
                    status["tavily"] = validate_tavily_key(st.session_state["tavily_key"])
                if st.session_state["google_key"].strip():
                    status["google"] = validate_google_key(st.session_state["google_key"])
            st.session_state["key_status"] = status

        for provider, (ok, message) in (st.session_state["key_status"] or {}).items():
            (st.success if ok else st.error)(
                f"**{provider}** — {message}", icon="✅" if ok else "⚠️"
            )


# ======================================================================
# Sidebar
# ======================================================================
with st.sidebar:
    st.markdown("### ✍️ Blog Writing Agent")
    st.caption("LangGraph · Groq · Tavily · Gemini")

    # ---------------- account (hosted deployments only) ----------------
    if access.mode == "hosted":
        st.markdown(f"**{access.label}**")
        st.caption(access.email + ("  ·  admin" if access.is_admin else ""))
        st.caption("📊 " + quota.describe())
        if not quota.unlimited:
            st.progress(min(1.0, quota.used / max(1, quota.limit)))
        if st.button("Sign out", width="stretch"):
            st.logout()

        if access.is_admin:
            with st.expander("👑 Usage today"):
                usage = all_usage_today()
                if not usage:
                    st.caption("No runs yet today.")
                else:
                    st.dataframe(
                        pd.DataFrame(
                            sorted(usage.items(), key=lambda kv: -kv[1]),
                            columns=["User", "Runs"],
                        ),
                        width="stretch",
                        hide_index=True,
                    )
                    st.caption(
                        f"{sum(usage.values())} run(s) across {len(usage)} user(s). "
                        "Counters are in memory and reset on restart or at UTC midnight."
                    )
        st.divider()

        st.session_state["own_keys"] = st.toggle(
            "Use my own API keys",
            value=st.session_state["own_keys"],
            help="Bypasses the shared credentials and the daily limit. "
            "Your keys stay in this browser session.",
        )

    # ---------------- credentials ----------------
    # On a hosted deployment the owner's keys come from Secrets, so the inputs
    # only appear when the visitor opts out of them.
    show_key_inputs = access.mode == "open" or st.session_state["own_keys"]

    if show_key_inputs:
        render_key_inputs()
    else:
        # Restore the deployment's keys in case the visitor edited them and then
        # toggled back to the shared credentials.
        st.session_state["groq_key"] = env_default("GROQ_API_KEY")
        st.session_state["tavily_key"] = env_default("TAVILY_API_KEY")
        st.session_state["google_key"] = env_default("GOOGLE_API_KEY")
        st.caption("🔑 Running on the deployment's shared keys.")

    has_groq = bool(st.session_state["groq_key"].strip())
    has_tavily = bool(st.session_state["tavily_key"].strip())
    has_google = bool(st.session_state["google_key"].strip())

    st.divider()

    # ---------------- topic ----------------
    topic = st.text_area(
        "**Topic**",
        height=110,
        placeholder="e.g. How KV caching actually works in transformer inference",
        key="topic_input",
    )
    as_of = st.date_input("As-of date", value=date.today())

    # ---------------- model ----------------
    with st.expander("🧠 Model", expanded=False):
        model = st.selectbox(
            "Text model (Groq)",
            TEXT_MODELS,
            index=TEXT_MODELS.index(DEFAULT_TEXT_MODEL),
            help="Groq retired llama3-70b-8192 and llama-3.3-70b-versatile. "
            "These are the current production models.",
        )
        temperature = st.slider("Temperature", 0.0, 1.0, 0.4, 0.05)
        max_tokens_on = st.checkbox("Cap output tokens per section", value=False)
        max_tokens = (
            st.number_input("Max tokens", 256, 8192, 2048, 256) if max_tokens_on else None
        )

    # ---------------- research ----------------
    with st.expander("🔎 Research", expanded=False):
        if not has_tavily:
            st.info("Add a Tavily key to enable web research.", icon="ℹ️")
        enable_research = st.toggle("Enable web research", value=has_tavily, disabled=not has_tavily)
        force_mode = st.selectbox(
            "Mode",
            ["auto", "closed_book", "hybrid", "open_book"],
            help="auto lets the router decide. closed_book = evergreen, "
            "hybrid = evergreen + fresh examples, open_book = last-7-days news.",
        )
        max_queries = st.slider("Max search queries", 1, 10, 6, disabled=not has_tavily)
        results_per_query = st.slider("Results per query", 1, 10, 5, disabled=not has_tavily)
        search_depth = st.radio(
            "Search depth",
            ["basic", "advanced"],
            horizontal=True,
            disabled=not has_tavily,
            help="advanced costs more Tavily credits per search.",
        )

    # ---------------- images ----------------
    with st.expander("🖼️ Images", expanded=False):
        if not has_google:
            st.info("Add a Google AI key to enable diagram generation.", icon="ℹ️")
        enable_images = st.toggle("Generate diagrams", value=has_google, disabled=not has_google)
        image_model = st.selectbox(
            "Image model",
            IMAGE_MODELS,
            index=IMAGE_MODELS.index(DEFAULT_IMAGE_MODEL),
            disabled=not has_google,
        )
        if image_model not in FREE_TIER_IMAGE_MODELS:
            st.warning("This model has no free tier — it bills per image.", icon="💳")
        max_images = st.slider("Max images", 1, 6, 3, disabled=not has_google)

    # ---------------- editorial ----------------
    with st.expander("📐 Editorial", expanded=False):
        blog_kind = st.selectbox(
            "Blog kind",
            ["auto", "explainer", "tutorial", "news_roundup", "comparison", "system_design"],
        )
        audience = st.text_input("Audience override", placeholder="e.g. backend engineers new to LLMs")
        tone = st.text_input("Tone override", placeholder="e.g. direct, no hype, code-first")
        min_sections, max_sections = st.slider("Sections", 3, 12, (5, 9))
        constraints_raw = st.text_area(
            "Extra constraints (one per line)",
            placeholder="No marketing language\nUse Python 3.12 examples",
            height=80,
        )

    st.divider()

    # The daily cap only applies to the shared keys — a visitor spending their
    # own credentials is not costing the deployment anything.
    on_shared_keys = access.mode == "hosted" and not st.session_state["own_keys"]
    quota_blocked = on_shared_keys and quota.exhausted

    run_btn = st.button(
        "🚀 Generate blog",
        type="primary",
        width="stretch",
        disabled=not has_groq or quota_blocked or st.session_state["is_running"],
    )
    if not has_groq:
        st.caption("⬆️ Add a Groq API key to enable generation.")
    elif quota_blocked:
        st.caption(
            f"⛔ Daily limit of {quota.limit} runs reached. It resets at UTC "
            "midnight — or switch on **Use my own API keys** above."
        )

    # ---------------- history ----------------
    if st.session_state["history"]:
        st.divider()
        st.markdown("**Session history**")
        labels = {
            f"{item['title'][:42]}{'…' if len(item['title']) > 42 else ''}  ·  {item['when']}": item["id"]
            for item in st.session_state["history"]
        }
        chosen = st.radio(
            "Previously generated",
            list(labels.keys()),
            index=0,
            label_visibility="collapsed",
        )
        if labels[chosen] != st.session_state["active_id"]:
            st.session_state["active_id"] = labels[chosen]
        if st.button("🗑️ Clear history", width="stretch"):
            st.session_state["history"] = []
            st.session_state["active_id"] = None
            st.rerun()


cfg = RunConfig(
    groq_api_key=st.session_state["groq_key"],
    tavily_api_key=st.session_state["tavily_key"],
    google_api_key=st.session_state["google_key"],
    model=model,
    temperature=temperature,
    max_tokens=int(max_tokens) if max_tokens else None,
    enable_research=enable_research,
    force_mode=force_mode,
    max_queries=max_queries,
    results_per_query=results_per_query,
    search_depth=search_depth,
    enable_images=enable_images,
    image_model=image_model,
    max_images=max_images,
    as_of=as_of.isoformat(),
    blog_kind=blog_kind,
    audience=audience,
    tone=tone,
    min_sections=min_sections,
    max_sections=max_sections,
    constraints=[c.strip() for c in constraints_raw.splitlines() if c.strip()],
)


# ======================================================================
# Header
# ======================================================================
theme.hero(
    "Blog Writing Agent",
    "Turn a one-line topic into a researched, cited, illustrated technical post. "
    "A LangGraph pipeline routes, researches, plans, writes every section in "
    "parallel, and draws the diagrams.",
    eyebrow="LangGraph · multi-agent writer",
)
theme.pills(
    [
        (f"Groq · {cfg.model.split('/')[-1]}", "ok" if has_groq else "warn"),
        ("Research on" if cfg.research_available else "Research off", "ok" if cfg.research_available else "off"),
        ("Images on" if cfg.images_available else "Images off", "ok" if cfg.images_available else "off"),
        (f"Mode: {cfg.force_mode}", "ok"),
    ]
)


# ======================================================================
# Run
# ======================================================================
NODE_LABELS = {
    "router": "Deciding whether research is needed",
    "research": "Searching the web and building the evidence pack",
    "orchestrator": "Planning the outline",
    "worker": "Writing sections in parallel",
    "merge": "Merging sections",
    "plan_images": "Deciding on diagrams",
    "render": "Generating images and rendering",
}


def do_run(topic_text: str) -> None:
    problems = cfg.validate()
    if problems:
        for problem in problems:
            st.error(problem, icon="⚠️")
        return

    # Count the run before any API call, so a crash mid-generation cannot be
    # used to retry past the cap.
    if on_shared_keys:
        record_run(access.email)

    st.session_state["is_running"] = True
    st.session_state["run_log"] = []
    log = st.session_state["run_log"]

    started = time.time()
    status = st.status("Starting the graph…", expanded=True)
    progress = st.progress(0.0)
    detail = st.empty()

    final_state: Dict[str, Any] = {}
    seen_nodes: List[str] = []
    sections_done = 0
    expected_sections = 0

    try:
        graph = build_graph(cfg)
        inputs = initial_state(topic_text, cfg)

        for stream_mode, chunk in graph.stream(inputs, stream_mode=["updates", "values"]):
            if stream_mode == "values":
                final_state = chunk
                continue

            for node_name, payload in (chunk or {}).items():
                payload = payload or {}
                if node_name not in seen_nodes:
                    seen_nodes.append(node_name)
                    status.write(f"**{node_name}** — {NODE_LABELS.get(node_name, '…')}")

                if node_name == "orchestrator" and payload.get("plan"):
                    expected_sections = len(payload["plan"].get("tasks", []))
                    status.write(f"↳ outline has {expected_sections} sections")
                if node_name == "research":
                    status.write(f"↳ {len(payload.get('evidence') or [])} sources kept")
                if node_name == "worker":
                    sections_done += len(payload.get("sections") or [])
                    if expected_sections:
                        detail.caption(f"Sections written: {sections_done}/{expected_sections}")
                if node_name == "plan_images":
                    status.write(f"↳ {len(payload.get('image_specs') or [])} diagrams planned")

                done = len(set(seen_nodes) & set(NODE_LABELS))
                progress.progress(min(0.95, done / len(NODE_LABELS)))

                log.append(
                    f"[{node_name}] " + json.dumps(payload, default=str)[:1500]
                )

        progress.progress(1.0)
        elapsed = time.time() - started

        final_md = final_state.get("final") or final_state.get("merged_md") or ""
        if not final_md:
            status.update(label="Finished, but no markdown was produced", state="error")
            st.error("The graph completed without producing any article text.")
            return

        plan = final_state.get("plan") or {}
        title = plan.get("blog_title") or topic_text[:80]

        st.session_state["history"].insert(
            0,
            {
                "id": f"{int(time.time() * 1000)}",
                "title": title,
                "topic": topic_text,
                "when": datetime.now().strftime("%H:%M"),
                "md": final_md,
                "plan": plan,
                "evidence": final_state.get("evidence") or [],
                "image_specs": final_state.get("image_specs") or [],
                "images_b64": final_state.get("images_b64") or {},
                "image_errors": final_state.get("image_errors") or [],
                "warnings": final_state.get("warnings") or [],
                "mode": final_state.get("mode") or "",
                "router_reason": final_state.get("router_reason") or "",
                "queries": final_state.get("queries") or [],
                "elapsed": elapsed,
                "model": cfg.model,
                "log": list(log),
            },
        )
        st.session_state["history"] = st.session_state["history"][:20]
        st.session_state["active_id"] = st.session_state["history"][0]["id"]

        status.update(label=f"✅ Done in {elapsed:.0f}s", state="complete", expanded=False)

    except Exception as exc:  # surface the real reason instead of a blank page
        status.update(label="❌ Run failed", state="error", expanded=True)
        message = str(exc)
        if "invalid_api_key" in message or "401" in message:
            st.error("Groq rejected the API key. Re-check it under **API keys**.", icon="🔑")
        elif "model_not_found" in message or "decommissioned" in message.lower():
            st.error(
                f"Groq no longer serves `{cfg.model}`. Pick a different model under **Model**.",
                icon="🧠",
            )
        elif "rate_limit" in message.lower() or "429" in message:
            st.error("Groq rate limit hit. Wait a moment, or lower the section count.", icon="⏳")
        else:
            st.error(f"Run failed: {message}", icon="❌")
        with st.expander("Traceback"):
            st.code(traceback.format_exc(), language="text")
    finally:
        st.session_state["is_running"] = False


if run_btn:
    if not topic.strip():
        st.warning("Enter a topic first.", icon="✏️")
    else:
        do_run(topic.strip())


# ======================================================================
# Results
# ======================================================================
run = active_run()

if not run:
    st.info(
        "Add your **Groq API key** in the sidebar, type a topic, and hit "
        "**Generate blog**. Tavily and Google keys are optional — they turn on "
        "web research and diagram generation.",
        icon="👋",
    )
    if st.button("👀 Explore the UI with a sample article (no key needed)"):
        from bwa.sample import sample_run

        demo = sample_run()
        st.session_state["history"].insert(0, demo)
        st.session_state["active_id"] = demo["id"]
        st.rerun()

    theme.heading("How it works")
    theme.steps(
        [
            ("🧭", "Route", "Decides whether the topic needs fresh web research."),
            ("🔎", "Research", "Tavily search, deduped and recency-filtered into an evidence pack."),
            ("🧩", "Plan", "Title, audience, tone and a 5–9 section outline."),
            ("✍️", "Write", "One worker per section, all running concurrently."),
            ("🖼️", "Illustrate", "Plans diagrams and renders them with Gemini."),
        ]
    )

    theme.heading("Free API keys")
    theme.key_cards(
        [
            {"name": "Groq", "tag": "Required", "required": "1",
             "desc": "Powers all the writing — router, planner, section writers.",
             "free": "Free · no credit card", "url": "console.groq.com/keys"},
            {"name": "Tavily", "tag": "Optional",
             "desc": "Web research and source citations.",
             "free": "1,000 searches / month", "url": "app.tavily.com"},
            {"name": "Google AI", "tag": "Optional",
             "desc": "Diagram and illustration generation.",
             "free": "~500 images / day on Nano Banana", "url": "aistudio.google.com/apikey"},
        ],
        note="Nothing is stored server-side. Keys stay in your browser session and "
        "vanish when you close the tab.",
    )
    st.stop()


md = run["md"]
plan = run["plan"] or {}
title = run["title"]
slug = safe_slug(title)

theme.stats(
    [
        ("Words", f"{word_count(md):,}"),
        ("Read time", f"{read_time_minutes(md)} min"),
        ("Sections", str(len(plan.get("tasks", [])) or md.count("\n## "))),
        ("Sources", str(len(run["evidence"]))),
        ("Images", str(len(run["images_b64"]))),
        ("Runtime", f"{run['elapsed']:.0f}s"),
    ]
)

for warning in run["warnings"]:
    st.warning(warning, icon="⚠️")

tab_article, tab_plan, tab_sources, tab_images, tab_export, tab_log = st.tabs(
    ["📝 Article", "🧩 Plan", "🔎 Sources", "🖼️ Images", "⬇️ Export", "🧾 Run log"]
)

# ---------------- Article ----------------
with tab_article:
    view = st.radio(
        "View", ["Rendered", "Raw markdown"], horizontal=True, label_visibility="collapsed"
    )
    if view == "Raw markdown":
        st.code(md, language="markdown")
    else:
        st.markdown('<div class="bwa-article">', unsafe_allow_html=True)
        for kind, payload in split_markdown_images(md):
            if kind == "md":
                st.markdown(payload)
                continue
            alt, src, caption = payload.split("|||", 2)
            filename = src.split("/")[-1]
            if src.startswith("http"):
                st.image(src, caption=caption or alt or None, width="stretch")
            elif filename in run["images_b64"]:
                st.image(
                    base64.b64decode(run["images_b64"][filename]),
                    caption=caption or alt or None,
                    width="stretch",
                )
            else:
                st.caption(f"🖼️ _{alt or filename}_ (image unavailable)")
        st.markdown("</div>", unsafe_allow_html=True)

# ---------------- Plan ----------------
with tab_plan:
    if not plan:
        st.info("No plan captured for this article.")
    else:
        st.markdown(f"#### {plan.get('blog_title', title)}")
        theme.stats(
            [
                ("Audience", str(plan.get("audience", "—"))),
                ("Tone", str(plan.get("tone", "—"))),
                ("Kind", str(plan.get("blog_kind", "—"))),
                ("Mode", run["mode"] or "—"),
            ]
        )
        if run["router_reason"]:
            st.caption(f"**Router:** {run['router_reason']}")
        if plan.get("constraints"):
            st.markdown("**Constraints:** " + " · ".join(plan["constraints"]))

        tasks = plan.get("tasks", [])
        if tasks:
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "#": t.get("id"),
                            "Section": t.get("title"),
                            "Words": t.get("target_words"),
                            "Research": "✓" if t.get("requires_research") else "",
                            "Cites": "✓" if t.get("requires_citations") else "",
                            "Code": "✓" if t.get("requires_code") else "",
                        }
                        for t in tasks
                    ]
                ),
                width="stretch",
                hide_index=True,
            )
            with st.expander("Full task detail (JSON)"):
                st.json(tasks)

# ---------------- Sources ----------------
with tab_sources:
    if run["queries"]:
        st.markdown("**Search queries**")
        st.markdown("\n".join(f"- `{q}`" for q in run["queries"]))
    evidence = run["evidence"]
    if not evidence:
        st.info(
            "No sources for this run — either closed-book mode, or no Tavily key was set.",
            icon="ℹ️",
        )
    else:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Title": e.get("title"),
                        "Published": e.get("published_at") or "—",
                        "URL": e.get("url"),
                    }
                    for e in evidence
                ]
            ),
            width="stretch",
            hide_index=True,
            column_config={"URL": st.column_config.LinkColumn("URL", display_text="open")},
        )

# ---------------- Images ----------------
with tab_images:
    images = run["images_b64"]
    if run["image_errors"]:
        for err in run["image_errors"]:
            st.warning(err, icon="🖼️")
    if not images:
        st.info(
            "No images in this article. Add a Google AI key and enable diagrams in the sidebar.",
            icon="ℹ️",
        )
    else:
        specs_by_file = {s["filename"]: s for s in run["image_specs"]}
        for filename, b64 in images.items():
            spec = specs_by_file.get(filename, {})
            st.image(
                base64.b64decode(b64),
                caption=spec.get("caption") or filename,
                width="stretch",
            )
            with st.expander(f"Prompt · {filename}"):
                st.write(spec.get("prompt", "—"))
            st.download_button(
                f"⬇️ {filename}",
                data=base64.b64decode(b64),
                file_name=filename,
                mime="image/png",
                key=f"dl-{run['id']}-{filename}",
            )

# ---------------- Export ----------------
with tab_export:
    st.markdown("Everything is built in memory — nothing was written to the server.")
    left, right = st.columns(2)
    with left:
        st.download_button(
            "⬇️ Markdown (.md)",
            data=md.encode("utf-8"),
            file_name=f"{slug}.md",
            mime="text/markdown",
            width="stretch",
        )
        st.download_button(
            "🌐 Standalone HTML",
            data=to_standalone_html(md, title, run["images_b64"]),
            file_name=f"{slug}.html",
            mime="text/html",
            width="stretch",
            help="Images inlined as data URIs — one file, opens anywhere.",
        )
    with right:
        st.download_button(
            "📦 Bundle (.md + images/)",
            data=bundle_zip(md, f"{slug}.md", run["images_b64"]),
            file_name=f"{slug}_bundle.zip",
            mime="application/zip",
            width="stretch",
        )
        st.download_button(
            "🖼️ Images only (.zip)",
            data=images_zip(run["images_b64"]),
            file_name=f"{slug}_images.zip",
            mime="application/zip",
            width="stretch",
            disabled=not run["images_b64"],
        )

    st.divider()
    st.download_button(
        "🧷 Full run record (.json)",
        data=json.dumps(
            {k: v for k, v in run.items() if k not in ("images_b64", "log")},
            indent=2,
            default=str,
        ).encode("utf-8"),
        file_name=f"{slug}_run.json",
        mime="application/json",
        width="stretch",
    )

# ---------------- Run log ----------------
with tab_log:
    entries = run.get("log") or []
    if not entries:
        st.info("No log captured for this run.")
    else:
        st.caption(f"{len(entries)} node updates · model `{run['model']}`")
        st.code("\n\n".join(entries[-120:]), language="json")

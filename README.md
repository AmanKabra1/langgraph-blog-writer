# Blog Writing Agent

A LangGraph pipeline that turns a one-line topic into a finished technical blog post —
routing, researching, planning, writing sections in parallel, and generating diagrams —
wrapped in a Streamlit UI that runs on a phone, a tablet or a desktop.

**Everything is configured in the browser.** No `.env`, no config file, no environment
variables. Paste your API keys into the sidebar and hit Generate.

```
topic
  │
  ▼
router ──────────► needs research?
  │                     │
  │  no                 │ yes
  │                     ▼
  │                 research  (Tavily → evidence pack, deduped, recency-filtered)
  │                     │
  ▼                     ▼
orchestrator  (plan: title, audience, tone, 5–9 sections)
  │
  ├── Send ──► worker 1 ─┐
  ├── Send ──► worker 2 ─┤  written concurrently
  └── Send ──► worker N ─┘
                         │
                         ▼
                       merge  →  plan_images  →  render  →  markdown + images
```

---

## Quick start

```bash
git clone https://github.com/AmanKabra1/langgraph-blog-writer.git
cd langgraph-blog-writer

python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux

pip install -r requirements.txt
streamlit run app.py
```

Open http://localhost:8501. You can click **"Explore the UI with a sample article"**
to see the whole interface before entering any credentials.

---

## The three keys (all have a free tier)

| Provider | Powers | Required? | Free tier | Get a key |
| --- | --- | --- | --- | --- |
| **Groq** | Router, planner, section writers, image planner | **Yes** | Free, no credit card | [console.groq.com/keys](https://console.groq.com/keys) |
| **Tavily** | Web research and source citations | No | 1,000 searches/month | [app.tavily.com](https://app.tavily.com) |
| **Google AI** | Diagram generation | No | ~500 images/day on Nano Banana | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) |

With Groq alone the app writes closed-book posts. Adding Tavily turns on research and
citations; adding Google AI turns on diagrams. Missing keys disable those nodes cleanly
and say so in the UI rather than failing the run.

Keys are held in Streamlit's per-session state. They are never written to disk, never
logged, and disappear when the tab closes. The **Test keys** button validates each one
against its provider before you spend a run on a bad credential.

### Models

Groq retires models aggressively. `llama3-70b-8192` (the original default in this
project) was shut down in **August 2025**, and `llama-3.3-70b-versatile` /
`llama-3.1-8b-instant` shut down on **2026-08-16**. The current default is
`openai/gpt-oss-120b`; the model picker only offers models that are live.

---

## Deploying to Streamlit Community Cloud (free)

1. Push this repo to GitHub (already done if you cloned it from there).
2. Go to [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub.
3. **New app** → pick this repo → branch `main` → main file `app.py` → **Deploy**.
4. Done. Users of the deployed app enter their own keys in the sidebar.

Optional: to bake in your own keys so the app starts ready to use, open
**App settings → Secrets** and paste:

```toml
GROQ_API_KEY   = "gsk_..."
TAVILY_API_KEY = "tvly-..."
GOOGLE_API_KEY = "AIza..."
```

The sidebar pre-fills from those but users can still override them.

> The app writes nothing to disk — generated markdown, images and zips are built in
> memory — so it behaves identically on an ephemeral cloud host and on your laptop.

---

## Layout

```
app.py                      Streamlit UI and the only entry point
bwa/
  config.py                 RunConfig — all runtime settings, model catalogues
  schemas.py                Pydantic models and the LangGraph state
  providers.py              Groq (langchain), Tavily (REST), Gemini (REST), key validation
  graph.py                  build_graph(cfg) — the pipeline
  exporters.py              in-memory markdown / HTML / zip export
  theme.py                  responsive CSS and layout helpers
  sample.py                 built-in demo article (no API calls)
tests/
  test_pipeline.py          offline graph tests with a fake LLM — no keys, no network
  test_responsive.mjs       Playwright layout checks across 7 viewports
legacy/                     the original single-file backend/frontend, kept for reference
.streamlit/config.toml      theme + server settings
```

Tavily and Gemini are called over plain REST rather than through their SDKs. That keeps
the dependency list to seven packages and avoids breaking when an SDK changes shape.

---

## Tests

**Pipeline** — runs the whole graph against a fake LLM. No keys, no network:

```bash
python tests/test_pipeline.py
```

Covers the happy path plus the failure modes that matter: a worker that 429s mid-run,
image generation failing, the image planner truncating the article, closed-book skipping
research, and a Groq-only run degrading cleanly.

**Responsive layout** — drives a real browser at 7 viewports from 320px to 1920px:

```bash
npm install && npx playwright install chromium
streamlit run app.py --server.port 8501 --server.headless true   # in another shell
node tests/test_responsive.mjs http://localhost:8501
```

Asserts no horizontal page scroll, no element escaping the viewport, images that scale,
a tab strip that stays reachable, 32px+ tap targets on touch, 11px+ text, no console
errors, and that the page title is never hidden behind Streamlit's fixed header.
Screenshots are written to `screenshots/`.

---

## Design notes

**Per-run graph construction.** `build_graph(cfg)` closes over the config, so the keys
and model come from the UI rather than module-level globals. Nothing is read at import
time, which is what lets the app boot with zero credentials.

**Images live in state.** Generated PNGs are base64 in the graph state and in session
state, never files. Downloads (markdown, standalone HTML with inlined data URIs, zip
bundle) are all assembled in memory.

**Single execution.** Progress is streamed with `stream_mode=["updates", "values"]`, so
the UI gets node-by-node updates and the final state from one pass.

**Failures are contained.** A section that fails leaves a marked placeholder and a
warning instead of killing the post. Image failures leave a blockquote with the prompt
and the reason. The image planner is checked for truncation before its output replaces
the merged article.

# Blog Writing Agent

A LangGraph pipeline that turns a one-line topic into a finished technical blog post —
routing, researching, planning, writing sections in parallel, and generating diagrams —
wrapped in a Streamlit UI that runs on a phone, a tablet or a desktop.

It runs in one of two modes, chosen automatically by what's in Secrets:

| | **Open** (default) | **Hosted** |
| --- | --- | --- |
| Trigger | no `[auth]` block | `[auth]` block present |
| Login | none | Google sign-in |
| Keys | each visitor brings their own | the owner's, from Secrets |
| Limits | none | N runs per user per day |

Open mode is what you get from `git clone && streamlit run app.py` — nothing to
configure. Hosted mode is for putting the app on the internet on your own credentials
without strangers draining your free tier.

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

1. [share.streamlit.io](https://share.streamlit.io) → sign in with GitHub.
2. **New app** → this repo → branch `main` → main file `app.py` → **Deploy**.
3. **⋮ → Settings → Sharing → Who can view this app → Anyone with the link.**
   Skipping this leaves the app invisible to everyone but you.

That gives you open mode: every visitor supplies their own keys. Stop here if that's
what you want — it costs you nothing and needs no further setup.

### Hosted mode: your keys, Google sign-in, daily limits

Turning this on means visitors spend **your** free tier, so the login gate and the
per-user cap are what keep that bounded.

**Step 1 — create a Google OAuth client.** At
[console.cloud.google.com](https://console.cloud.google.com):

- **APIs & Services → OAuth consent screen** → External → fill in the app name and
  your email → Save. Leave it in *Testing* to restrict to accounts you list, or
  **Publish** it to let any Google account in.
- **APIs & Services → Credentials → Create credentials → OAuth client ID →
  Web application.**
- Under **Authorised redirect URIs**, add both:
  ```
  http://localhost:8501/oauth2callback
  https://<your-app>.streamlit.app/oauth2callback
  ```
  The path must be exactly `/oauth2callback`. A mismatch here is the single most
  common cause of `redirect_uri_mismatch` at sign-in.
- Copy the **client ID** and **client secret**.

**Step 2 — generate a cookie secret:**

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

**Step 3 — paste into App settings → Secrets** (see
[`.streamlit/secrets.toml.example`](.streamlit/secrets.toml.example) for the annotated
version):

```toml
GROQ_API_KEY   = "gsk_..."
TAVILY_API_KEY = "tvly-..."
GOOGLE_API_KEY = "AIza..."

[auth]
redirect_uri  = "https://<your-app>.streamlit.app/oauth2callback"
cookie_secret = "<the 64-char hex string from step 2>"

[auth.google]
client_id           = "....apps.googleusercontent.com"
client_secret       = "GOCSPX-..."
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"

[access]
daily_run_limit = 5
admins          = ["you@example.com"]
# allowed_emails  = ["friend@example.com"]   # omit both to allow any Google account
# allowed_domains = ["yourcompany.com"]
```

Saving Secrets restarts the app. Visitors now hit a sign-in screen; admins bypass the
cap and get a usage panel in the sidebar.

A signed-in visitor can flip **"Use my own API keys"** to spend their own credentials
instead — that also lifts their daily cap, since they are no longer costing you
anything.

> **Never commit secrets.** `.streamlit/secrets.toml` is gitignored. On Community Cloud
> the Secrets panel is the only correct place for them — not the repo, not a chat
> window. If a key is ever exposed, revoke and reissue it; all three providers do this
> instantly and for free.

> The app writes nothing to disk — generated markdown, images and zips are built in
> memory — so it behaves identically on an ephemeral cloud host and on your laptop.

---

## Layout

```
app.py                      Streamlit UI and the only entry point
bwa/
  auth.py                   Google sign-in gate + email/domain allowlist
  usage.py                  per-user daily run cap (in-memory, resets at UTC midnight)
  config.py                 RunConfig — all runtime settings, model catalogues
  schemas.py                Pydantic models and the LangGraph state
  providers.py              Groq (langchain), Tavily (REST), Gemini (REST), key validation
  graph.py                  build_graph(cfg) — the pipeline
  exporters.py              in-memory markdown / HTML / zip export
  theme.py                  responsive CSS and layout helpers
  sample.py                 built-in demo article (no API calls)
tests/
  test_pipeline.py          offline graph tests with a fake LLM — no keys, no network
  test_access.py            allowlist and quota logic — no OAuth, no network
  test_responsive.mjs       Playwright layout checks across 7 viewports
legacy/                     the original single-file backend/frontend, kept for reference
.streamlit/config.toml      theme + server settings
```

Tavily and Gemini are called over plain REST rather than through their SDKs. That keeps
the dependency list to eight packages and avoids breaking when an SDK changes shape.

---

## Tests

**Pipeline and access control** — no keys, no network, no OAuth:

```bash
python tests/test_pipeline.py    # 9 tests: the graph, against a fake LLM
python tests/test_access.py      # 8 tests: allowlist, quota, counter thread-safety
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
Screenshots are written to `screenshots/`. Current status: **110/110**.

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

**The gate is fail-closed.** `gate()` runs before any widget is drawn and calls
`st.stop()` on an unauthenticated or disallowed visitor, so the sidebar — and the
owner's keys with it — never reaches the browser. The daily counter increments *before*
the first API call, so a run that crashes halfway cannot be replayed to beat the cap.

**Failures are contained.** A section that fails leaves a marked placeholder and a
warning instead of killing the post. Image failures leave a blockquote with the prompt
and the reason. The image planner is checked for truncation before its output replaces
the merged article.

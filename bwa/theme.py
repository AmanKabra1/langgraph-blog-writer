"""Responsive styling.

Streamlit is only partly responsive out of the box: tab strips overflow, the
wide layout leaves unreadably long lines on desktop, and control padding is far
too generous on a phone. The CSS below fixes those across three breakpoints —
phone (<=640px), tablet (641-1024px) and desktop (>1024px) — and is written to
work in both the light and dark Streamlit themes.
"""

from __future__ import annotations

import streamlit as st

CSS = """
<style>
/* ------------------------------------------------------------------
   Base / desktop
   ------------------------------------------------------------------ */
:root {
  --bwa-accent: #6c8cff;
  --bwa-accent-soft: rgba(108, 140, 255, 0.14);
  --bwa-border: rgba(128, 138, 165, 0.28);
  --bwa-surface: rgba(128, 138, 165, 0.07);
  --bwa-radius: 14px;
  /* Streamlit's header is absolutely positioned and opaque, so the first
     element on the page must be pushed clear of it or it gets covered. */
  --bwa-header: 60px;
}

.block-container {
  max-width: 1180px;
  padding-top: calc(var(--bwa-header) + 0.9rem);
  padding-bottom: 4rem;
}

/* Long-form prose should stay readable even in the wide layout. */
.bwa-article p,
.bwa-article li {
  max-width: 74ch;
  line-height: 1.75;
}
.bwa-article img { border-radius: 12px; }

/* ---- page backdrop: a faint glow behind the hero, nothing that competes with text ---- */
div[data-testid="stAppViewContainer"] {
  background:
    radial-gradient(900px 420px at 18% -8%, rgba(108, 140, 255, 0.16), transparent 70%),
    radial-gradient(700px 360px at 92% -12%, rgba(176, 108, 255, 0.10), transparent 70%);
}

/* ---- header: translucent so the backdrop glow reads through ---- */
header[data-testid="stHeader"] {
  background: rgba(14, 17, 23, 0.72);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
}

/* ---- sidebar ---- */
section[data-testid="stSidebar"] > div:first-child {
  background: linear-gradient(180deg, rgba(108, 140, 255, 0.07), transparent 38%);
  border-right: 1px solid var(--bwa-border);
}
section[data-testid="stSidebar"] div[data-testid="stExpander"] details {
  border-radius: 12px;
  border-color: var(--bwa-border);
  background: var(--bwa-surface);
}

/* ---- hero ---- */
.bwa-hero {
  position: relative;
  overflow: hidden;
  border: 1px solid var(--bwa-border);
  border-radius: 18px;
  padding: 1.5rem 1.6rem 1.35rem;
  margin-bottom: 1.1rem;
  background:
    linear-gradient(135deg, rgba(108, 140, 255, 0.20), rgba(176, 108, 255, 0.08) 45%, transparent 80%),
    var(--bwa-surface);
  box-shadow: 0 10px 40px -18px rgba(108, 140, 255, 0.45);
}
.bwa-hero::after {  /* soft orb, top right */
  content: "";
  position: absolute;
  width: 260px; height: 260px;
  right: -80px; top: -120px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(176, 108, 255, 0.28), transparent 70%);
  pointer-events: none;
}
.bwa-eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
  font-size: 0.72rem;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--bwa-accent);
  margin-bottom: 0.55rem;
}
.bwa-eyebrow::before {
  content: "";
  width: 7px; height: 7px; border-radius: 50%;
  background: var(--bwa-accent);
  box-shadow: 0 0 0 4px var(--bwa-accent-soft);
}
.bwa-hero h1 {
  margin: 0;
  padding: 0;
  font-size: clamp(1.45rem, 2.8vw, 2.25rem);
  font-weight: 750;
  line-height: 1.15;
  letter-spacing: -0.025em;
  background: linear-gradient(90deg, #ffffff, #b9c7ff 55%, #d4b8ff);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
}
.bwa-hero p {
  margin: 0.5rem 0 0;
  max-width: 62ch;
  opacity: 0.78;
  font-size: 0.95rem;
  line-height: 1.55;
}

/* ---- pills ---- */
.bwa-pills { display: flex; flex-wrap: wrap; gap: 0.4rem; margin: 0.7rem 0 0.9rem; }
.bwa-pill {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.24rem 0.7rem;
  border: 1px solid var(--bwa-border);
  border-radius: 999px;
  background: var(--bwa-surface);
  font-size: 0.76rem;
  white-space: nowrap;
}
.bwa-pill::before {
  content: "";
  width: 6px; height: 6px; border-radius: 50%;
  background: rgba(160, 168, 190, 0.7);
}
.bwa-pill.ok    { border-color: rgba(46, 160, 96, 0.45); background: rgba(46, 160, 96, 0.08); }
.bwa-pill.ok::before   { background: #3ecf7a; box-shadow: 0 0 6px #3ecf7a; }
.bwa-pill.warn  { border-color: rgba(214, 154, 42, 0.55); background: rgba(214, 154, 42, 0.08); }
.bwa-pill.warn::before { background: #f0b43c; }
.bwa-pill.off   { opacity: 0.6; }

/* ---- stat strip: wraps instead of squashing ---- */
.bwa-stats { display: flex; flex-wrap: wrap; gap: 0.6rem; margin: 0.4rem 0 1rem; }
.bwa-stat {
  position: relative;
  flex: 1 1 130px;
  min-width: 118px;
  border: 1px solid var(--bwa-border);
  border-radius: var(--bwa-radius);
  padding: 0.7rem 0.85rem;
  background: linear-gradient(180deg, rgba(108, 140, 255, 0.07), transparent), var(--bwa-surface);
  overflow: hidden;
  transition: border-color 0.15s ease, transform 0.15s ease;
}
.bwa-stat::before {
  content: "";
  position: absolute; left: 0; top: 0; right: 0; height: 2px;
  background: linear-gradient(90deg, var(--bwa-accent), #b06cff);
  opacity: 0.8;
}
.bwa-stat:hover { border-color: rgba(108, 140, 255, 0.5); transform: translateY(-1px); }
.bwa-stat .k { font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.07em; opacity: 0.62; }
.bwa-stat .v {
  font-size: 1.35rem; font-weight: 700; line-height: 1.25; margin-top: 0.15rem;
  font-variant-numeric: tabular-nums;
}

/* ---- section label ---- */
.bwa-h {
  margin: 1.4rem 0 0.7rem;
  font-size: 0.78rem;
  font-weight: 650;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  opacity: 0.7;
}

/* ---- "how it works" steps ---- */
.bwa-steps {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 0.6rem;
  counter-reset: bwa-step;
}
.bwa-step {
  border: 1px solid var(--bwa-border);
  border-radius: var(--bwa-radius);
  padding: 0.85rem 0.9rem;
  background: var(--bwa-surface);
  counter-increment: bwa-step;
}
.bwa-step .ic {
  display: inline-flex; align-items: center; justify-content: center;
  width: 32px; height: 32px; border-radius: 9px;
  background: var(--bwa-accent-soft);
  font-size: 1rem;
  margin-bottom: 0.5rem;
}
.bwa-step .t { font-weight: 650; font-size: 0.92rem; }
.bwa-step .t::before { content: counter(bwa-step) ". "; color: var(--bwa-accent); }
.bwa-step .d { font-size: 0.8rem; opacity: 0.72; line-height: 1.45; margin-top: 0.2rem; }

/* ---- provider key cards (replaces a table that overflowed on phones) ---- */
.bwa-keys {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 0.6rem;
}
.bwa-key {
  border: 1px solid var(--bwa-border);
  border-radius: var(--bwa-radius);
  padding: 0.9rem 1rem;
  background: var(--bwa-surface);
  display: flex; flex-direction: column; gap: 0.35rem;
}
.bwa-key .top { display: flex; align-items: center; justify-content: space-between; gap: 0.5rem; }
.bwa-key .n { font-weight: 700; font-size: 1rem; }
.bwa-key .tag {
  font-size: 0.68rem; font-weight: 650; letter-spacing: 0.06em; text-transform: uppercase;
  padding: 0.14rem 0.5rem; border-radius: 999px;
  border: 1px solid var(--bwa-border); opacity: 0.8;
}
.bwa-key .tag.req { border-color: rgba(108, 140, 255, 0.6); color: var(--bwa-accent); opacity: 1; }
.bwa-key .d { font-size: 0.84rem; opacity: 0.78; line-height: 1.45; }
.bwa-key .f { font-size: 0.76rem; opacity: 0.6; }
.bwa-key a {
  margin-top: 0.2rem;
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--bwa-accent) !important;
  text-decoration: none;
  word-break: break-all;
}
.bwa-key a:hover { text-decoration: underline; }
.bwa-note { font-size: 0.8rem; opacity: 0.6; margin: 0.7rem 0 0; }

/* ---- buttons ---- */
.stButton > button, .stDownloadButton > button {
  border-radius: 10px;
  font-weight: 600;
  transition: transform 0.12s ease, box-shadow 0.12s ease, border-color 0.12s ease;
}
.stButton > button:hover, .stDownloadButton > button:hover {
  transform: translateY(-1px);
  border-color: var(--bwa-accent);
}
button[data-testid="stBaseButton-primary"] {
  background: linear-gradient(135deg, #6c8cff, #9a6cff);
  border: 0;
  box-shadow: 0 6px 22px -8px rgba(108, 140, 255, 0.75);
}
button[data-testid="stBaseButton-primary"]:hover {
  box-shadow: 0 8px 28px -8px rgba(154, 108, 255, 0.85);
}

/* ---- inputs ---- */
.stTextArea textarea:focus, .stTextInput input:focus {
  box-shadow: 0 0 0 3px var(--bwa-accent-soft) !important;
}

/* ---- tabs: pill style ---- */
div[data-testid="stTabs"] [role="tablist"] { gap: 0.3rem; }
div[data-testid="stTabs"] [role="tab"] {
  border-radius: 999px;
  padding: 0.3rem 0.9rem;
  border: 1px solid transparent;
}
div[data-testid="stTabs"] [role="tab"][aria-selected="true"] {
  background: var(--bwa-accent-soft);
  border-color: rgba(108, 140, 255, 0.45);
}
div[data-testid="stTabs"] [data-baseweb="tab-highlight"] { display: none; }

/* ---- article ---- */
.bwa-article h1 { letter-spacing: -0.02em; }
.bwa-article h2 { margin-top: 2rem; letter-spacing: -0.01em; }
.bwa-article blockquote {
  border-left: 3px solid var(--bwa-accent);
  background: var(--bwa-accent-soft);
  padding: 0.6rem 1rem;
  border-radius: 0 10px 10px 0;
}

/* ---- tabs: scroll horizontally rather than wrapping into a tall mess ---- */
div[data-testid="stTabs"] [role="tablist"] {
  overflow-x: auto;
  overflow-y: hidden;
  flex-wrap: nowrap;
  scrollbar-width: thin;
  -webkit-overflow-scrolling: touch;
}
div[data-testid="stTabs"] [role="tablist"]::-webkit-scrollbar { height: 4px; }
div[data-testid="stTabs"] [role="tab"] { white-space: nowrap; flex: 0 0 auto; }

/* ---- anything wide gets its own scroll container, never the page ---- */
div[data-testid="stDataFrame"], div[data-testid="stTable"] { overflow-x: auto; }
.stCode, pre { overflow-x: auto; max-width: 100%; }
.bwa-article table { display: block; overflow-x: auto; max-width: 100%; }

/* ------------------------------------------------------------------
   Tablet  (641px - 1024px)
   ------------------------------------------------------------------ */
@media (min-width: 641px) and (max-width: 1024px) {
  .block-container {
    padding-left: 1.6rem;
    padding-right: 1.6rem;
    padding-top: calc(var(--bwa-header) + 0.6rem);
  }
  .bwa-hero h1 { font-size: 1.45rem; }
  .bwa-stat { flex: 1 1 44%; }
  .bwa-article p, .bwa-article li { max-width: none; }
}

/* ------------------------------------------------------------------
   Phone  (<= 640px)
   ------------------------------------------------------------------ */
@media (max-width: 640px) {
  .block-container {
    padding-left: 0.85rem;
    padding-right: 0.85rem;
    padding-top: calc(var(--bwa-header) + 0.35rem);
    padding-bottom: 3rem;
  }

  .bwa-hero { padding: 0.9rem 1rem; border-radius: 12px; }
  .bwa-hero h1 { font-size: 1.2rem; }
  .bwa-hero p  { font-size: 0.85rem; }

  /* Streamlit keeps columns side-by-side on some phone widths — force stacking. */
  div[data-testid="stHorizontalBlock"] { flex-direction: column !important; gap: 0.5rem; }
  div[data-testid="stColumn"] { width: 100% !important; flex: 1 1 100% !important; min-width: 100% !important; }

  /* Two-up, not one-up: six full-width cards would push the article itself
     below the fold on a phone. */
  .bwa-stats { gap: 0.45rem; }
  .bwa-stat {
    flex: 1 1 calc(50% - 0.45rem);
    min-width: 0;
    padding: 0.5rem 0.65rem;
  }
  .bwa-stat .k { font-size: 0.7rem; }
  .bwa-stat .v {
    font-size: 1.05rem;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  /* Full-width tap targets, comfortably above the 44px minimum. */
  .stButton > button,
  .stDownloadButton > button,
  div[data-testid="stFormSubmitButton"] > button {
    width: 100%;
    min-height: 44px;
  }

  div[data-testid="stTabs"] [role="tab"] {
    padding-left: 0.6rem;
    padding-right: 0.6rem;
    font-size: 0.85rem;
    min-height: 40px;
  }

  .bwa-article p, .bwa-article li { max-width: none; font-size: 0.97rem; line-height: 1.7; }
  .bwa-article h1 { font-size: 1.45rem; }
  .bwa-article h2 { font-size: 1.2rem; }
  .bwa-article h3 { font-size: 1.05rem; }
  .bwa-article pre, .stCode { font-size: 0.8rem; }

  /* A near-full-width drawer is easier to use than the default narrow one —
     but ONLY while expanded. Streamlit hides the sidebar with a fixed
     translateX(-300px), so widening it in the collapsed state leaves a sliver
     of the drawer sitting on top of the page. */
  section[data-testid="stSidebar"][aria-expanded="true"] {
    width: 88vw !important;
    min-width: 88vw !important;
    max-width: 88vw !important;
  }

  div[data-testid="stMetricValue"] { font-size: 1.2rem; }
  .stTextArea textarea { font-size: 16px; }  /* stops iOS zooming on focus */
}

/* ------------------------------------------------------------------
   Touch devices of any size
   Streamlit's own chrome (the toolbar "Stop"/menu buttons and the sidebar
   collapse arrow) ships at 28px, under the 44px touch guideline. Enlarge it
   wherever the primary input is a finger rather than a mouse.
   ------------------------------------------------------------------ */
@media (pointer: coarse), (hover: none), (max-width: 1024px) {
  div[data-testid="stToolbar"] button,
  div[data-testid="stToolbarActions"] button,
  button[data-testid="stBaseButton-headerNoPadding"],
  button[data-testid="stBaseButton-header"],
  div[data-testid="stSidebarCollapseButton"] button,
  div[data-testid="stSidebarCollapsedControl"] button,
  button[kind="header"],
  button[kind="headerNoPadding"] {
    min-height: 44px;
    min-width: 44px;
  }

  div[data-testid="stTabs"] [role="tab"] { min-height: 44px; }

  /* The "?" help icons, the password reveal toggle and the image toolbar all
     ship at 16-22px, which is unhittable with a thumb. Grow the hit area
     without moving the glyph. */
  [data-testid="stTooltipHoverTarget"] > button,
  [data-testid="stTooltipIcon"] button,
  [data-testid="stTextInputRootElement"] > button,
  [data-testid="stNumberInputContainer"] > button,
  button[data-testid="stBaseButton-elementToolbar"] {
    min-height: 40px;
    min-width: 40px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }

  /* Radio and checkbox rows: the label is the hit area, so give it real height. */
  div[data-testid="stRadio"] label,
  div[data-testid="stCheckbox"] label,
  div[data-baseweb="radio"] label,
  div[data-baseweb="checkbox"] label {
    min-height: 36px;
    align-items: center;
  }

  /* Streamlit's per-heading anchor links only appear on hover. On a touch
     device they are unreachable and act as a 16px tap trap — drop them. */
  [data-testid="stHeaderActionElements"] { display: none !important; }
}

/* Respect reduced-motion preferences. */
@media (prefers-reduced-motion: reduce) {
  * { animation-duration: 0.01ms !important; transition-duration: 0.01ms !important; }
}
</style>
"""


def inject() -> None:
    """Inject the stylesheet. Safe to call once per rerun."""
    st.markdown(CSS, unsafe_allow_html=True)


def hero(title: str, subtitle: str, eyebrow: str = "") -> None:
    eyebrow_html = f'<div class="bwa-eyebrow">{eyebrow}</div>' if eyebrow else ""
    st.markdown(
        f'<div class="bwa-hero">{eyebrow_html}<h1>{title}</h1><p>{subtitle}</p></div>',
        unsafe_allow_html=True,
    )


def heading(text: str) -> None:
    """A small uppercase section label."""
    st.markdown(f'<div class="bwa-h">{text}</div>', unsafe_allow_html=True)


def steps(items: list[tuple[str, str, str]]) -> None:
    """A numbered "how it works" grid. `items` is (icon, title, description)."""
    html = "".join(
        f'<div class="bwa-step"><div class="ic">{icon}</div>'
        f'<div class="t">{title}</div><div class="d">{desc}</div></div>'
        for icon, title, desc in items
    )
    st.markdown(f'<div class="bwa-steps">{html}</div>', unsafe_allow_html=True)


def key_cards(items: list[dict[str, str]], note: str = "") -> None:
    """Provider cards — name, tag, required, desc, free, url. Replaces a
    markdown table that overflowed sideways on phones."""
    cards = []
    for it in items:
        tag_cls = "tag req" if it.get("required") else "tag"
        cards.append(
            f'<div class="bwa-key"><div class="top"><span class="n">{it["name"]}</span>'
            f'<span class="{tag_cls}">{it["tag"]}</span></div>'
            f'<div class="d">{it["desc"]}</div><div class="f">{it["free"]}</div>'
            f'<a href="https://{it["url"]}" target="_blank" rel="noopener">{it["url"]} ↗</a></div>'
        )
    note_html = f'<p class="bwa-note">{note}</p>' if note else ""
    st.markdown(
        f'<div class="bwa-keys">{"".join(cards)}</div>{note_html}', unsafe_allow_html=True
    )


def pills(items: list[tuple[str, str]]) -> None:
    """Render status chips. `items` is a list of (label, state) where state is
    one of "ok", "warn", "off"."""
    html = "".join(
        f'<span class="bwa-pill {state}">{label}</span>' for label, state in items
    )
    st.markdown(f'<div class="bwa-pills">{html}</div>', unsafe_allow_html=True)


def stats(items: list[tuple[str, str]]) -> None:
    """A wrap-friendly stat strip — replaces st.columns+st.metric, which squashes
    badly on narrow screens."""
    html = "".join(
        f'<div class="bwa-stat"><div class="k">{k}</div><div class="v">{v}</div></div>'
        for k, v in items
    )
    st.markdown(f'<div class="bwa-stats">{html}</div>', unsafe_allow_html=True)

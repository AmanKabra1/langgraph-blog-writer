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

/* ---- hero ---- */
.bwa-hero {
  border: 1px solid var(--bwa-border);
  border-radius: var(--bwa-radius);
  padding: 1.15rem 1.35rem;
  margin-bottom: 1.1rem;
  background: linear-gradient(135deg, var(--bwa-accent-soft), transparent 72%);
}
.bwa-hero h1 {
  margin: 0;
  font-size: clamp(1.35rem, 2.4vw, 2rem);
  line-height: 1.2;
  letter-spacing: -0.015em;
}
.bwa-hero p {
  margin: 0.4rem 0 0;
  opacity: 0.75;
  font-size: 0.92rem;
  line-height: 1.5;
}

/* ---- pills ---- */
.bwa-pills { display: flex; flex-wrap: wrap; gap: 0.4rem; margin: 0.7rem 0 0.2rem; }
.bwa-pill {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.2rem 0.62rem;
  border: 1px solid var(--bwa-border);
  border-radius: 999px;
  background: var(--bwa-surface);
  font-size: 0.76rem;
  white-space: nowrap;
}
.bwa-pill.ok    { border-color: rgba(46, 160, 96, 0.55); }
.bwa-pill.warn  { border-color: rgba(214, 154, 42, 0.55); }
.bwa-pill.off   { opacity: 0.55; }

/* ---- stat strip: wraps instead of squashing ---- */
.bwa-stats { display: flex; flex-wrap: wrap; gap: 0.6rem; margin: 0.4rem 0 1rem; }
.bwa-stat {
  flex: 1 1 130px;
  min-width: 118px;
  border: 1px solid var(--bwa-border);
  border-radius: var(--bwa-radius);
  padding: 0.65rem 0.8rem;
  background: var(--bwa-surface);
}
.bwa-stat .k { font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.06em; opacity: 0.62; }
.bwa-stat .v { font-size: 1.3rem; font-weight: 650; line-height: 1.25; margin-top: 0.15rem; }

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


def hero(title: str, subtitle: str) -> None:
    st.markdown(
        f'<div class="bwa-hero"><h1>{title}</h1><p>{subtitle}</p></div>',
        unsafe_allow_html=True,
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

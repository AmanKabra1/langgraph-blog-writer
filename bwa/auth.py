"""Google sign-in gate.

Two modes, chosen automatically:

* **hosted** — an ``[auth]`` block exists in secrets, so the app is a shared
  deployment running on the owner's API keys. Visitors must sign in with Google
  and pass the allowlist before they can spend those keys.
* **open** — no ``[auth]`` block (local development, or a fork someone runs
  themselves). No login; every visitor brings their own keys, exactly as the
  app behaved before auth existed.

Falling back to open mode rather than erroring means ``streamlit run app.py``
still works on a laptop with nothing configured.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

import streamlit as st


@dataclass
class Access:
    """Who the current visitor is and what they are allowed to do."""

    mode: str                      # "hosted" | "open"
    email: str = ""
    name: str = ""
    picture: str = ""
    is_admin: bool = False
    daily_limit: Optional[int] = None   # None = unlimited
    shared_keys: bool = False           # running on the owner's credentials

    @property
    def signed_in(self) -> bool:
        return self.mode == "open" or bool(self.email)

    @property
    def label(self) -> str:
        return self.name or self.email or "guest"


def _secret_section(name: str) -> dict:
    try:
        if name in st.secrets:
            return dict(st.secrets[name])
    except Exception:
        pass
    return {}


def auth_configured() -> bool:
    """True when the deployment has an [auth] block, i.e. login is expected."""
    try:
        return "auth" in st.secrets
    except Exception:
        return False


def _as_list(value) -> List[str]:
    if not value:
        return []
    if isinstance(value, str):
        return [v.strip().lower() for v in value.split(",") if v.strip()]
    return [str(v).strip().lower() for v in value]


def _is_allowed(email: str, access_cfg: dict) -> bool:
    """An empty allowlist means any Google account may sign in."""
    emails = _as_list(access_cfg.get("allowed_emails"))
    domains = _as_list(access_cfg.get("allowed_domains"))
    if not emails and not domains:
        return True

    email = email.lower()
    if email in emails:
        return True
    domain = email.rsplit("@", 1)[-1] if "@" in email else ""
    return domain in domains


# ======================================================================
# Screens
# ======================================================================
def _login_screen() -> None:
    st.markdown(
        '<div class="bwa-hero"><h1>Blog Writing Agent</h1>'
        "<p>A LangGraph pipeline that routes, researches, plans, writes in "
        "parallel, and illustrates a full technical post.</p></div>",
        unsafe_allow_html=True,
    )
    st.info(
        "This is a shared deployment running on the owner's API keys. "
        "Sign in with Google to use it.",
        icon="🔐",
    )

    left, _ = st.columns([1, 1])
    with left:
        if st.button("Sign in with Google", type="primary", width="stretch"):
            st.login("google")

    st.caption(
        "Only your email address and display name are read, and only to apply "
        "the daily usage limit. Nothing you generate is stored on the server."
    )

    with st.expander("Want to see the interface first?"):
        st.write(
            "You can run this app yourself with your own free API keys — no login "
            "involved. The source is at "
            "[github.com/AmanKabra1/langgraph-blog-writer]"
            "(https://github.com/AmanKabra1/langgraph-blog-writer)."
        )


def _denied_screen(email: str) -> None:
    st.markdown(
        '<div class="bwa-hero"><h1>Blog Writing Agent</h1></div>',
        unsafe_allow_html=True,
    )
    st.error(
        f"**{email}** is not on the access list for this deployment.",
        icon="🚫",
    )
    st.caption(
        "Ask the owner to add your address, or run your own copy with your own "
        "free API keys — see the "
        "[repository](https://github.com/AmanKabra1/langgraph-blog-writer)."
    )
    if st.button("Sign out"):
        st.logout()


# ======================================================================
# Entry point
# ======================================================================
def gate() -> Access:
    """Resolve the visitor's access. Halts the script if they may not proceed."""
    if not auth_configured():
        return Access(mode="open", daily_limit=None, shared_keys=False)

    access_cfg = _secret_section("access")
    limit_raw = access_cfg.get("daily_run_limit", 5)
    try:
        daily_limit = int(limit_raw) if limit_raw not in (None, "", 0) else None
    except (TypeError, ValueError):
        daily_limit = 5

    try:
        logged_in = bool(st.user.is_logged_in)
    except Exception as exc:
        # Misconfigured [auth] block, or Authlib missing. Say so plainly rather
        # than showing a blank page.
        st.error(f"Sign-in is misconfigured on this deployment: {exc}", icon="⚠️")
        st.caption(
            "The owner needs a valid `[auth]` block in Secrets and `Authlib` in "
            "requirements.txt."
        )
        st.stop()

    if not logged_in:
        _login_screen()
        st.stop()

    email = str(getattr(st.user, "email", "") or "")
    if not _is_allowed(email, access_cfg):
        _denied_screen(email)
        st.stop()

    admins = _as_list(access_cfg.get("admins"))
    is_admin = email.lower() in admins

    return Access(
        mode="hosted",
        email=email,
        name=str(getattr(st.user, "name", "") or ""),
        picture=str(getattr(st.user, "picture", "") or ""),
        is_admin=is_admin,
        daily_limit=None if is_admin else daily_limit,
        shared_keys=True,
    )

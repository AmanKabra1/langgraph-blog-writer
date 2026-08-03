"""Offline tests for the login allowlist and the daily run cap.

No OAuth, no network. Run with:
    python tests/test_access.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bwa.auth import Access, _as_list, _is_allowed
from bwa.usage import Quota, _Counter


def test_allowlist_empty_allows_everyone():
    assert _is_allowed("anyone@gmail.com", {})
    assert _is_allowed("anyone@gmail.com", {"daily_run_limit": 5})
    print("  empty allowlist admits anyone ..... ok")


def test_allowlist_by_email():
    cfg = {"allowed_emails": ["A@Example.com", "b@example.com"]}
    assert _is_allowed("a@example.com", cfg), "match must be case-insensitive"
    assert _is_allowed("B@EXAMPLE.COM", cfg)
    assert not _is_allowed("c@example.com", cfg)
    print("  email allowlist ................... ok")


def test_allowlist_by_domain():
    cfg = {"allowed_domains": ["Corp.com"]}
    assert _is_allowed("anyone@corp.com", cfg)
    assert not _is_allowed("anyone@notcorp.com", cfg)
    # A lookalike suffix must not slip through.
    assert not _is_allowed("anyone@evilcorp.com", cfg)
    print("  domain allowlist .................. ok")


def test_allowlist_accepts_comma_string():
    # TOML users sometimes write a string instead of a list.
    cfg = {"allowed_emails": "a@x.com, b@x.com"}
    assert _as_list(cfg["allowed_emails"]) == ["a@x.com", "b@x.com"]
    assert _is_allowed("b@x.com", cfg)
    assert not _is_allowed("c@x.com", cfg)
    print("  comma-separated string config ..... ok")


def test_access_dataclass():
    open_mode = Access(mode="open")
    assert open_mode.signed_in, "open mode needs no sign-in"
    assert not open_mode.shared_keys

    hosted = Access(mode="hosted", email="a@b.com", name="Aman", daily_limit=5)
    assert hosted.signed_in and hosted.label == "Aman"
    assert Access(mode="hosted", email="a@b.com").label == "a@b.com"
    assert not Access(mode="hosted").signed_in, "hosted with no email is not signed in"
    print("  access dataclass .................. ok")


def test_quota_arithmetic():
    q = Quota(used=0, limit=5)
    assert q.remaining == 5 and not q.exhausted
    q = Quota(used=5, limit=5)
    assert q.remaining == 0 and q.exhausted
    q = Quota(used=99, limit=5)
    assert q.remaining == 0 and q.exhausted, "must not go negative"
    q = Quota(used=100, limit=None)
    assert q.unlimited and not q.exhausted
    assert "no limit" in q.describe()
    assert "3 of 5" in Quota(used=2, limit=5).describe()
    print("  quota arithmetic .................. ok")


def test_counter_is_per_user_and_daily():
    c = _Counter()
    assert c.get("a@x.com") == 0
    c.increment("a@x.com")
    c.increment("a@x.com")
    c.increment("b@x.com")
    assert c.get("a@x.com") == 2
    assert c.get("b@x.com") == 1, "users must not share a counter"
    assert c.snapshot() == {"a@x.com": 2, "b@x.com": 1}

    # Yesterday's rows are dropped on the next access.
    stale_key = ("a@x.com", "2020-01-01")
    c._counts[stale_key] = 99
    assert c.get("a@x.com") == 2
    assert stale_key not in c._counts, "stale day must be pruned"
    print("  counter is per-user and daily ..... ok")


def test_counter_is_thread_safe():
    import threading

    c = _Counter()
    errors = []

    def hammer():
        try:
            for _ in range(200):
                c.increment("shared@x.com")
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=hammer) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, errors
    assert c.get("shared@x.com") == 1600, f"lost updates: {c.get('shared@x.com')}"
    print("  counter is thread-safe ............ ok")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"\nRunning {len(tests)} access tests\n" + "-" * 46)
    failed = 0
    for fn in tests:
        try:
            fn()
        except Exception as exc:
            failed += 1
            print(f"  FAILED {fn.__name__}: {exc}")
            import traceback

            traceback.print_exc()
    print("-" * 46)
    print("all passed" if not failed else f"{failed} failed")
    sys.exit(1 if failed else 0)

"""Offline tests — no API keys, no network.

Run with:  python -m pytest tests -q      (or)   python tests/test_pipeline.py
"""

from __future__ import annotations

import base64
import io
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bwa import graph as graph_mod
from bwa.config import RunConfig
from bwa.exporters import (
    bundle_zip,
    images_zip,
    read_time_minutes,
    split_markdown_images,
    to_standalone_html,
    word_count,
)
from bwa.graph import build_graph, initial_state, safe_slug
from bwa.schemas import EvidencePack, GlobalImagePlan, ImageSpec, Plan, RouterDecision, Task

# A 1x1 transparent PNG.
TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk"
    "YPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


# ======================================================================
# Fakes
# ======================================================================
class FakeMessage:
    def __init__(self, content: str):
        self.content = content


class FakeLLM:
    """Stands in for ChatGroq. Records calls so tests can assert on flow."""

    def __init__(self, mode="hybrid", n_tasks=5, n_images=2):
        self.mode = mode
        self.n_tasks = n_tasks
        self.n_images = n_images
        self.calls: list[str] = []
        self._schema = None

    def with_structured_output(self, schema, method="function_calling", **kwargs):
        self._schema = schema
        return _FakeStructured(self, schema)

    def invoke(self, messages):
        self.calls.append("worker")
        return FakeMessage("## Generated Section\n\nBody text for the section. " * 12)


class _FakeStructured:
    def __init__(self, parent: FakeLLM, schema):
        self.parent = parent
        self.schema = schema

    def invoke(self, messages):
        self.parent.calls.append(self.schema.__name__)

        if self.schema is RouterDecision:
            return RouterDecision(
                needs_research=self.parent.mode != "closed_book",
                mode=self.parent.mode,
                reason="test",
                queries=["q1", "q2", "q3"],
            )

        if self.schema is EvidencePack:
            return EvidencePack(
                evidence=[
                    {
                        "title": "Source A",
                        "url": "https://a.example/1",
                        "published_at": "2026-08-01",
                        "snippet": "s",
                    },
                    {
                        "title": "Source A dup",
                        "url": "https://a.example/1",
                        "published_at": "2026-08-01",
                    },
                    {"title": "Source B", "url": "https://b.example/2"},
                ]
            )

        if self.schema is Plan:
            return Plan(
                blog_title="Test Blog: How Things Work",
                audience="engineers",
                tone="direct",
                blog_kind="explainer",
                tasks=[
                    Task(
                        id=99,  # deliberately wrong — orchestrator must renumber
                        title=f"Section {i}",
                        goal="g",
                        bullets=["a", "b", "c"],
                        target_words=9999,  # deliberately out of range — must clamp
                    )
                    for i in range(1, self.parent.n_tasks + 1)
                ],
            )

        if self.schema is GlobalImagePlan:
            # Echo back the merged article exactly as a well-behaved model would,
            # with placeholders appended.
            prompt = messages[-1].content
            body = prompt[prompt.index("\n# ") + 1 :]
            placeholders = "\n\n".join(
                f"[[IMAGE_{i}]]" for i in range(1, self.parent.n_images + 1)
            )
            return GlobalImagePlan(
                md_with_placeholders=body + "\n\n" + placeholders,
                images=[
                    ImageSpec(
                        placeholder=f"[[IMAGE_{i}]]",
                        filename="Bad Name.PNG",  # must be sanitized + deduped
                        alt=f"alt {i}",
                        caption=f"cap {i}",
                        prompt=f"diagram {i}",
                    )
                    for i in range(1, self.parent.n_images + 1)
                ],
            )

        raise AssertionError(f"unexpected schema {self.schema}")


def base_cfg(**over) -> RunConfig:
    defaults = dict(
        groq_api_key="gsk_test",
        tavily_api_key="tvly_test",
        google_api_key="AIza_test",
        enable_research=True,
        enable_images=True,
    )
    defaults.update(over)
    return RunConfig(**defaults)


def patch(monkey: dict, fake_llm: FakeLLM, images=True, search_hits=3):
    """Patch provider entry points on the graph module."""
    monkey["make_llm"] = graph_mod.make_llm
    monkey["tavily_search"] = graph_mod.tavily_search
    monkey["gemini_generate_image"] = graph_mod.gemini_generate_image

    graph_mod.make_llm = lambda cfg: fake_llm
    graph_mod.tavily_search = lambda *a, **k: [
        {
            "title": f"Hit {i}",
            "url": f"https://x.example/{i}",
            "snippet": "s",
            "published_at": "2026-08-01",
            "source": "x",
        }
        for i in range(search_hits)
    ]

    def _img(api_key, prompt, model="m", timeout=120):
        if not images:
            raise RuntimeError("simulated image failure")
        return TINY_PNG

    graph_mod.gemini_generate_image = _img


def unpatch(monkey: dict):
    for name, original in monkey.items():
        setattr(graph_mod, name, original)


# ======================================================================
# Tests
# ======================================================================
def test_exporters():
    md = "# T\n\nHello world.\n\n![a](images/f.png)\n*A caption*\n\nAfter."
    parts = split_markdown_images(md)
    kinds = [k for k, _ in parts]
    assert "img" in kinds, kinds
    img_part = next(p for k, p in parts if k == "img")
    alt, src, caption = img_part.split("|||", 2)
    assert (alt, src, caption) == ("a", "images/f.png", "A caption")
    # The caption line must be consumed, not re-rendered as body text.
    assert "*A caption*" not in "".join(p for k, p in parts if k == "md")

    images = {"f.png": base64.b64encode(TINY_PNG).decode()}

    zbytes = bundle_zip(md, "t.md", images)
    with zipfile.ZipFile(io.BytesIO(zbytes)) as z:
        assert set(z.namelist()) == {"t.md", "images/f.png"}
        assert z.read("images/f.png") == TINY_PNG

    with zipfile.ZipFile(io.BytesIO(images_zip(images))) as z:
        assert z.namelist() == ["f.png"]

    html = to_standalone_html(md, "T", images).decode()
    assert "data:image/png;base64," in html
    assert "images/f.png" not in html
    assert "<h1>T</h1>" in html
    assert 'name="viewport"' in html  # responsive export

    assert word_count("one two three") == 3
    assert read_time_minutes("word " * 450) == 2
    assert safe_slug("Hello, World! 2026") == "hello_world_2026"
    print("  exporters ..................... ok")


def test_html_escaping():
    html = to_standalone_html("<script>alert(1)</script>", "T", {}).decode()
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
    print("  html export escapes markup .... ok")


def test_full_run_hybrid():
    monkey: dict = {}
    llm = FakeLLM(mode="hybrid", n_tasks=5, n_images=2)
    patch(monkey, llm)
    try:
        cfg = base_cfg()
        out = build_graph(cfg).invoke(initial_state("test topic", cfg))
    finally:
        unpatch(monkey)

    assert out["mode"] == "hybrid"
    assert out["needs_research"] is True
    # 3 raw hits deduped by URL through the evidence synthesizer
    assert len(out["evidence"]) == 2, out["evidence"]

    tasks = out["plan"]["tasks"]
    assert [t["id"] for t in tasks] == [1, 2, 3, 4, 5], "ids must be renumbered"
    assert all(120 <= t["target_words"] <= 550 for t in tasks), "words must be clamped"

    assert len(out["sections"]) == 5, "every worker must contribute exactly once"
    assert [i for i, _ in sorted(out["sections"])] == [1, 2, 3, 4, 5]

    assert out["final"].startswith("# Test Blog: How Things Work")
    assert "[[IMAGE_" not in out["final"], "no placeholder may survive"
    assert len(out["images_b64"]) == 2
    # Filenames must be sanitized and made unique.
    names = list(out["images_b64"])
    assert all(n.endswith(".png") and n == n.lower() and " " not in n for n in names), names
    assert len(set(names)) == 2, names
    for name in names:
        assert f"images/{name}" in out["final"]
    print("  full run · hybrid ............. ok")


def test_closed_book_skips_research():
    monkey: dict = {}
    llm = FakeLLM(mode="closed_book", n_tasks=4, n_images=0)
    patch(monkey, llm)
    try:
        cfg = base_cfg(min_sections=3)
        out = build_graph(cfg).invoke(initial_state("evergreen topic", cfg))
    finally:
        unpatch(monkey)

    assert out["needs_research"] is False
    assert out["evidence"] == []
    assert "EvidencePack" not in llm.calls, "research node must not run"
    assert len(out["sections"]) == 4
    print("  closed_book skips research .... ok")


def test_no_keys_disables_optional_nodes():
    monkey: dict = {}
    llm = FakeLLM(mode="open_book", n_tasks=5, n_images=3)
    patch(monkey, llm)
    try:
        # Groq only — no Tavily, no Google.
        cfg = RunConfig(groq_api_key="gsk_test")
        out = build_graph(cfg).invoke(initial_state("latest ai news", cfg))
    finally:
        unpatch(monkey)

    assert out["needs_research"] is False, "must not attempt research without a key"
    assert out["images_b64"] == {}
    assert out["image_specs"] == []
    assert "GlobalImagePlan" not in llm.calls, "image planner must not run"
    assert out["final"] and "[[IMAGE_" not in out["final"]
    assert any("Tavily" in w for w in out["warnings"]), out["warnings"]
    print("  groq-only run degrades cleanly  ok")


def test_image_failure_is_survivable():
    monkey: dict = {}
    llm = FakeLLM(mode="closed_book", n_tasks=3, n_images=2)
    patch(monkey, llm, images=False)
    try:
        cfg = base_cfg(min_sections=3)
        out = build_graph(cfg).invoke(initial_state("topic", cfg))
    finally:
        unpatch(monkey)

    assert out["images_b64"] == {}
    assert len(out["image_errors"]) == 2
    assert out["final"], "the article must still be produced"
    assert "[[IMAGE_" not in out["final"]
    assert "[Image not generated]" in out["final"]
    print("  image failure is survivable ... ok")


def test_worker_failure_is_survivable():
    monkey: dict = {}
    llm = FakeLLM(mode="closed_book", n_tasks=4, n_images=0)

    def boom(messages):
        llm.calls.append("worker")
        if len([c for c in llm.calls if c == "worker"]) == 2:
            raise RuntimeError("simulated 429")
        return FakeMessage("## S\n\ntext " * 30)

    llm.invoke = boom
    patch(monkey, llm)
    try:
        cfg = base_cfg(min_sections=3)
        out = build_graph(cfg).invoke(initial_state("topic", cfg))
    finally:
        unpatch(monkey)

    assert len(out["sections"]) == 4, "a failed section must still be emitted"
    assert any("simulated 429" in w for w in out["warnings"])
    assert out["final"]
    print("  worker failure is survivable .. ok")


def test_image_planner_truncation_guard():
    monkey: dict = {}
    llm = FakeLLM(mode="closed_book", n_tasks=6, n_images=1)

    class Truncating(_FakeStructured):
        def invoke(self, messages):
            if self.schema is GlobalImagePlan:
                self.parent.calls.append("GlobalImagePlan")
                return GlobalImagePlan(md_with_placeholders="# Tiny\n", images=[])
            return super().invoke(messages)

    llm.with_structured_output = lambda schema, method="function_calling", **k: Truncating(
        llm, schema
    )
    patch(monkey, llm)
    try:
        cfg = base_cfg(min_sections=3)
        out = build_graph(cfg).invoke(initial_state("topic", cfg))
    finally:
        unpatch(monkey)

    assert out["final"] == out["merged_md"], "must fall back to the un-mangled markdown"
    assert any("rewrote the article" in w for w in out["warnings"]), out["warnings"]
    print("  planner truncation guarded .... ok")


def test_config_validation():
    assert RunConfig().validate(), "empty config must be rejected"
    assert not RunConfig(groq_api_key="k").validate()
    assert RunConfig(groq_api_key="k", as_of="not-a-date").validate()
    assert RunConfig(groq_api_key="k", min_sections=9, max_sections=4).validate()
    assert RunConfig(groq_api_key="k", model="llama3-70b-8192").validate(), (
        "the decommissioned model must not be accepted"
    )
    cfg = RunConfig(groq_api_key="k")
    assert not cfg.research_available and not cfg.images_available
    print("  config validation ............. ok")


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    print(f"\nRunning {len(tests)} tests\n" + "-" * 46)
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

"""A built-in sample article.

Lets anyone open the app and see the full result UI — article, plan, sources,
images, exports — without supplying a single API key. It is also what the
responsive UI tests drive.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Dict

from ._sample_asset import DIAGRAM_PNG_B64

SAMPLE_MD = """# How KV Caching Actually Works in Transformer Inference

## Why generation gets slower without a cache

Every token a decoder-only model emits attends over every token before it. Without
caching, generating token *n* means recomputing the key and value projections for all
*n-1* previous tokens — work you already did on the previous step. The cost of a
sequence grows quadratically, and almost all of it is redundant.

The KV cache removes the redundancy. Keys and values are computed once per token and
retained, so each new step projects exactly one token and reads the rest from memory.
Generation goes from quadratic to linear in sequence length.

![Graph topology of the blog writing agent](images/kv_cache_flow.png)
*The same fan-out / fan-in shape this app uses to write sections in parallel.*

## What actually lives in the cache

For each layer you store two tensors shaped `[batch, heads, seq_len, head_dim]` — one
for keys, one for values. Queries are never cached: a query is only meaningful for the
token currently being generated.

- **Per layer, not per model.** A 32-layer model keeps 32 key tensors and 32 value tensors.
- **Grows every step.** `seq_len` increases by one per generated token.
- **Dtype matters.** At fp16, cache size is `2 x layers x heads x head_dim x seq_len x 2 bytes`.

A 7B model with 32 layers, 32 heads and a head dimension of 128 costs roughly 0.5 MB per
token of context. At 8k context that is about 4 GB — frequently more than the weights
you are trying to serve.

## The techniques that make it affordable

Grouped-query attention shares one set of KV heads across several query heads, cutting
cache size by the grouping factor with little quality loss. Multi-query attention is the
extreme case: a single KV head for all query heads.

```python
# The whole idea, stripped down.
cache = []  # per layer: (k, v)

def step(token, layer_idx):
    q, k, v = project(token)
    if layer_idx < len(cache):
        k = torch.cat([cache[layer_idx][0], k], dim=2)
        v = torch.cat([cache[layer_idx][1], v], dim=2)
    cache[layer_idx] = (k, v)
    return attention(q, k, v)   # q is one token; k and v are the full history
```

Paged attention goes further, allocating the cache in fixed-size blocks the way an OS
pages memory. That removes the fragmentation you get from pre-allocating a contiguous
buffer per sequence, and it is why vLLM can hold far more concurrent sequences than a
naive server on the same hardware.

## Where it bites you in production

Cache memory, not compute, is usually the ceiling on concurrency. Each in-flight request
holds its own cache for its full lifetime, so your maximum batch size is set by
`total_vram - weights` divided by per-sequence cache. Long-context requests are
disproportionately expensive; one 32k conversation can cost as much as a dozen short ones.

Two consequences worth designing around: evicting a cache mid-stream means recomputing
the prefill from scratch, and prefix sharing across requests with a common system prompt
can reclaim a surprising amount of memory for very little engineering.
"""

SAMPLE_PLAN: Dict[str, Any] = {
    "blog_title": "How KV Caching Actually Works in Transformer Inference",
    "audience": "backend engineers deploying LLMs",
    "tone": "direct, no hype, code-first",
    "blog_kind": "explainer",
    "constraints": ["No marketing language", "At least one runnable snippet"],
    "tasks": [
        {
            "id": 1,
            "title": "Why generation gets slower without a cache",
            "goal": "Show the redundant work a cache removes.",
            "bullets": ["quadratic recompute", "attention over history", "linear after caching"],
            "target_words": 220,
            "tags": ["fundamentals"],
            "requires_research": False,
            "requires_citations": False,
            "requires_code": False,
        },
        {
            "id": 2,
            "title": "What actually lives in the cache",
            "goal": "Make the memory cost concrete.",
            "bullets": ["tensor shapes", "per-layer storage", "dtype and size math"],
            "target_words": 260,
            "tags": ["memory"],
            "requires_research": False,
            "requires_citations": False,
            "requires_code": False,
        },
        {
            "id": 3,
            "title": "The techniques that make it affordable",
            "goal": "Explain GQA, MQA and paged attention.",
            "bullets": ["grouped-query attention", "multi-query attention", "paged attention"],
            "target_words": 300,
            "tags": ["optimization"],
            "requires_research": True,
            "requires_citations": True,
            "requires_code": True,
        },
        {
            "id": 4,
            "title": "Where it bites you in production",
            "goal": "Connect cache size to concurrency limits.",
            "bullets": ["batch size ceiling", "eviction cost", "prefix sharing"],
            "target_words": 240,
            "tags": ["operations"],
            "requires_research": True,
            "requires_citations": True,
            "requires_code": False,
        },
    ],
}

SAMPLE_EVIDENCE = [
    {
        "title": "Efficient Memory Management for LLM Serving with PagedAttention",
        "url": "https://arxiv.org/abs/2309.06180",
        "published_at": "2023-09-12",
        "snippet": "Introduces PagedAttention and the vLLM serving system.",
        "source": "arxiv.org",
    },
    {
        "title": "GQA: Training Generalized Multi-Query Transformer Models",
        "url": "https://arxiv.org/abs/2305.13245",
        "published_at": "2023-05-22",
        "snippet": "Grouped-query attention as an interpolation between MHA and MQA.",
        "source": "arxiv.org",
    },
    {
        "title": "Fast Transformer Decoding: One Write-Head is All You Need",
        "url": "https://arxiv.org/abs/1911.02150",
        "published_at": "2019-11-06",
        "snippet": "The original multi-query attention paper.",
        "source": "arxiv.org",
    },
]


def sample_run() -> Dict[str, Any]:
    """A history entry shaped exactly like a real run."""
    return {
        "id": f"sample-{int(time.time() * 1000)}",
        "title": SAMPLE_PLAN["blog_title"],
        "topic": "How KV caching actually works in transformer inference",
        "when": datetime.now().strftime("%H:%M"),
        "md": SAMPLE_MD,
        "plan": SAMPLE_PLAN,
        "evidence": SAMPLE_EVIDENCE,
        "image_specs": [
            {
                "placeholder": "[[IMAGE_1]]",
                "filename": "kv_cache_flow.png",
                "alt": "Graph topology of the blog writing agent",
                "caption": "The same fan-out / fan-in shape this app uses to write sections in parallel.",
                "prompt": "Clean labelled technical diagram of a five-stage pipeline on a dark background.",
            }
        ],
        "images_b64": {"kv_cache_flow.png": DIAGRAM_PNG_B64},
        "image_errors": [],
        "warnings": [
            "This is the built-in sample article — no API calls were made. "
            "Add a Groq key in the sidebar to generate your own."
        ],
        "mode": "hybrid",
        "router_reason": "Evergreen mechanics, but the optimization landscape moves quickly.",
        "queries": [
            "KV cache memory formula transformer inference",
            "grouped query attention vs multi query attention",
            "paged attention vLLM block allocation",
        ],
        "elapsed": 0.0,
        "model": "sample (no model called)",
        "log": ["[sample] loaded the built-in demo article — no graph execution"],
    }

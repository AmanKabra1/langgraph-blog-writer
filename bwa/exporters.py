"""Export helpers — everything is produced in memory.

No file is ever written to disk, so the app behaves identically on a laptop and
on an ephemeral cloud host.
"""

from __future__ import annotations

import base64
import re
import zipfile
from io import BytesIO
from typing import Dict, List, Tuple

MD_IMAGE_RE = re.compile(r"!\[(?P<alt>[^\]]*)\]\((?P<src>[^)\s]+)(?:\s+\"[^\"]*\")?\)")
CAPTION_RE = re.compile(r"^\*(?P<cap>[^*].*)\*$")


def markdown_to_html_fragment(md: str) -> str:
    """Very small markdown -> HTML shim used only for the standalone HTML export."""
    html_lines: List[str] = []
    in_code = False
    in_list = False

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            html_lines.append("</ul>")
            in_list = False

    def inline(text: str) -> str:
        text = (
            text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        )
        text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
        text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
        text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", text)
        text = re.sub(
            r"!\[([^\]]*)\]\(([^)]+)\)", r'<img alt="\1" src="\2" />', text
        )
        text = re.sub(
            r"\[([^\]]+)\]\(([^)]+)\)",
            r'<a href="\2" target="_blank" rel="noopener">\1</a>',
            text,
        )
        return text

    for raw in md.splitlines():
        line = raw.rstrip()

        if line.strip().startswith("```"):
            close_list()
            html_lines.append("</pre>" if in_code else "<pre>")
            in_code = not in_code
            continue
        if in_code:
            html_lines.append(
                line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            )
            continue

        if not line.strip():
            close_list()
            continue

        heading = re.match(r"^(#{1,6})\s+(.*)$", line)
        if heading:
            close_list()
            level = len(heading.group(1))
            html_lines.append(f"<h{level}>{inline(heading.group(2))}</h{level}>")
            continue

        if line.startswith("> "):
            close_list()
            html_lines.append(f"<blockquote>{inline(line[2:])}</blockquote>")
            continue

        bullet = re.match(r"^[-*]\s+(.*)$", line)
        if bullet:
            if not in_list:
                html_lines.append("<ul>")
                in_list = True
            html_lines.append(f"<li>{inline(bullet.group(1))}</li>")
            continue

        close_list()
        html_lines.append(f"<p>{inline(line)}</p>")

    close_list()
    if in_code:
        html_lines.append("</pre>")
    return "\n".join(html_lines)


HTML_SHELL = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{title}</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{ margin:0 auto; padding:2rem 1.25rem 5rem; max-width:52rem; line-height:1.7;
         font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
         font-size:1.02rem; }}
  h1 {{ font-size:clamp(1.7rem,4.5vw,2.5rem); line-height:1.2; }}
  h2 {{ font-size:clamp(1.3rem,3.2vw,1.75rem); margin-top:2.4rem; }}
  h3 {{ font-size:clamp(1.1rem,2.6vw,1.3rem); }}
  img {{ max-width:100%; height:auto; border-radius:10px; display:block; margin:1.25rem auto; }}
  pre {{ overflow-x:auto; padding:1rem; border-radius:10px; background:rgba(127,127,127,.12); }}
  code {{ font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:.92em; }}
  blockquote {{ margin:1rem 0; padding:.6rem 1rem; border-left:3px solid rgba(127,127,127,.5);
                background:rgba(127,127,127,.08); border-radius:0 8px 8px 0; }}
  a {{ color:#5b8def; }}
  @media (max-width:640px) {{ body {{ padding:1.25rem .9rem 4rem; font-size:1rem; }} }}
</style>
</head><body>
{body}
</body></html>
"""


def to_standalone_html(md: str, title: str, images_b64: Dict[str, str]) -> bytes:
    """Self-contained HTML with images inlined as data URIs."""
    for filename, b64 in (images_b64 or {}).items():
        md = md.replace(f"images/{filename}", f"data:image/png;base64,{b64}")
    return HTML_SHELL.format(
        title=title, body=markdown_to_html_fragment(md)
    ).encode("utf-8")


def bundle_zip(md: str, md_filename: str, images_b64: Dict[str, str]) -> bytes:
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(md_filename, md.encode("utf-8"))
        for filename, b64 in (images_b64 or {}).items():
            archive.writestr(f"images/{filename}", base64.b64decode(b64))
    return buf.getvalue()


def images_zip(images_b64: Dict[str, str]) -> bytes:
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for filename, b64 in (images_b64 or {}).items():
            archive.writestr(filename, base64.b64decode(b64))
    return buf.getvalue()


def split_markdown_images(md: str) -> List[Tuple[str, str]]:
    """Split markdown into ("md", text) and ("img", "alt|||src|||caption") parts.

    Captions written as a lone `*italic line*` right after an image are absorbed
    into the image part so the renderer can attach them properly.
    """
    parts: List[Tuple[str, str]] = []
    cursor = 0

    for match in MD_IMAGE_RE.finditer(md):
        before = md[cursor : match.start()]
        if before:
            parts.append(("md", before))

        alt = (match.group("alt") or "").strip()
        src = (match.group("src") or "").strip()
        cursor = match.end()

        caption = ""
        tail = md[cursor:]
        stripped = tail.lstrip("\n")
        if stripped:
            first_line = stripped.splitlines()[0].strip()
            cap_match = CAPTION_RE.match(first_line)
            if cap_match:
                caption = cap_match.group("cap").strip()
                consumed = len(tail) - len(stripped) + len(stripped.splitlines()[0])
                cursor += consumed

        parts.append(("img", f"{alt}|||{src}|||{caption}"))

    tail = md[cursor:]
    if tail:
        parts.append(("md", tail))

    return parts or [("md", md)]


def word_count(md: str) -> int:
    text = re.sub(r"```.*?```", " ", md, flags=re.S)
    text = re.sub(r"[#>*`_\[\]()!-]", " ", text)
    return len([w for w in text.split() if any(c.isalnum() for c in w)])


def read_time_minutes(md: str) -> int:
    return max(1, round(word_count(md) / 225))

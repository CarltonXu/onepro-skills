#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import re
import ssl
import unicodedata
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _collapse_ws(s: str) -> str:
    s = s.replace("\u00a0", " ")
    s = re.sub(r"[ \t\r\f\v]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def _has_cjk(s: str) -> bool:
    for ch in s:
        if "\u4e00" <= ch <= "\u9fff":
            return True
    return False


def _slugify(s: str, max_len: int = 64) -> str:
    s = unicodedata.normalize("NFKD", s).lower().strip()
    out = []
    for ch in s:
        if ch.isalnum():
            out.append(ch)
        elif ch in {" ", "_", "-", ".", "/", ":"}:
            out.append("-")
    slug = re.sub(r"-{2,}", "-", "".join(out)).strip("-")
    return (slug[:max_len] or "section").strip("-")


def _sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _guess_category_from_url_path(path_url: str) -> str:
    path = path_url.strip("/")
    if not path:
        return "Docs"
    parts = [p for p in path.split("/") if p and not p.endswith(".html")]
    if parts and parts[0] in {"zh", "en"}:
        parts = parts[1:]
    if not parts:
        return "Docs"
    parts = parts[:3]
    return " / ".join(p.replace("-", " ").title() for p in parts)


def _guess_tags_from_url_path(path_url: str) -> list[str]:
    path = path_url.strip("/")
    parts = [p for p in path.split("/") if p]
    if parts and parts[0] in {"zh", "en"}:
        parts = parts[1:]
    parts = [p for p in parts if not p.endswith(".html")]
    tags = []
    for p in parts[:8]:
        t = p.replace("-", " ").lower()
        if t and t not in tags:
            tags.append(t)
    return tags


@dataclass
class ExtractedSection:
    section_id: str
    heading: str
    level: int
    text: str
    text_hash: str


@dataclass
class ExtractedPage:
    page_id: str
    url: str
    path_url: str
    lang: str
    title: str | None
    category: str
    tags: list[str]
    sections: list[ExtractedSection]
    full_text: str
    full_text_hash: str


class _ContentExtractor(HTMLParser):
    """
    Heuristic extractor for VuePress/VitePress-like docs pages.
    Captures within known content roots when present, otherwise within <body>.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._stack: list[str] = []
        self._skip_depth = 0
        self._capture_depth = 0
        self._saw_content_root = False

        self._in_heading: int | None = None
        self._heading_buf: list[str] = []
        self._text_buf: list[str] = []

        self.title: str | None = None
        self.sections: list[tuple[int, str, str]] = []  # (level, heading, text)
        self._current_heading: tuple[int, str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._stack.append(tag)
        if tag in {"script", "style", "nav", "footer", "header", "aside"}:
            self._skip_depth += 1
            return

        attr = {k: (v or "") for k, v in attrs}
        cls = attr.get("class", "")
        el_id = attr.get("id", "")

        is_content_root = False
        if tag in {"main", "article", "div", "section"}:
            if any(x in cls for x in ["theme-default-content", "content__default", "vp-doc", "markdown-body", "doc-content"]):
                is_content_root = True
            if el_id in {"main-content", "content", "doc-content"}:
                is_content_root = True
        if is_content_root and not self._saw_content_root:
            self._saw_content_root = True
            self._capture_depth = len(self._stack)

        if self._in_capture() and tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._in_heading = int(tag[1])
            self._heading_buf = []

    def handle_endtag(self, tag: str) -> None:
        if self._in_heading and tag == f"h{self._in_heading}":
            heading = _collapse_ws("".join(self._heading_buf))
            self._in_heading = None
            self._heading_buf = []
            if heading:
                if not self.title and tag == "h1":
                    self.title = heading
                # Close previous section text.
                if self._current_heading:
                    lvl, h = self._current_heading
                    txt = _collapse_ws("".join(self._text_buf))
                    if txt:
                        self.sections.append((lvl, h, txt))
                self._current_heading = (int(tag[1]), heading)
                self._text_buf = []

        if self._skip_depth and self._stack and self._stack[-1] == tag:
            self._skip_depth -= 1

        if self._stack:
            self._stack.pop()

        if self._capture_depth and len(self._stack) < self._capture_depth:
            self._capture_depth = 0

    def handle_data(self, data: str) -> None:
        if not self._in_capture():
            return
        if self._in_heading:
            self._heading_buf.append(data)
            return
        txt = data.replace("\u00a0", " ")
        if not txt.strip():
            return
        self._text_buf.append(txt)
        # Add paragraph-ish breaks on block boundaries via newline heuristics.
        if self._stack and self._stack[-1] in {"p", "li"}:
            self._text_buf.append("\n\n")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._in_capture() and tag == "br":
            self._text_buf.append("\n")

    def _in_capture(self) -> bool:
        if self._skip_depth:
            return False
        if self._saw_content_root:
            return self._capture_depth > 0 and len(self._stack) >= self._capture_depth
        return "body" in self._stack

    def finalize(self) -> None:
        # Flush the last open section.
        if self._current_heading:
            lvl, h = self._current_heading
            txt = _collapse_ws("".join(self._text_buf))
            if txt:
                self.sections.append((lvl, h, txt))
        else:
            txt = _collapse_ws("".join(self._text_buf))
            if txt:
                self.sections.append((1, self.title or "Overview", txt))


def _extract_from_html_bytes(html_bytes: bytes) -> tuple[str | None, list[tuple[int, str, str]], str]:
    try:
        html = html_bytes.decode("utf-8", errors="replace")
    except Exception:
        html = html_bytes.decode(errors="replace")
    p = _ContentExtractor()
    p.feed(html)
    p.close()
    p.finalize()
    full_text = _collapse_ws("\n\n".join([s[2] for s in p.sections if s[2]]))
    return p.title, p.sections, full_text


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract per-page/per-section text from a crawled docs snapshot.")
    parser.add_argument("--snapshot", required=True, help="Snapshot dir created by crawl_docs_sitemap.py (contains manifest.json)")
    parser.add_argument("--out", default="outputs/docs_extracted.json", help="Output JSON path")
    parser.add_argument("--max-pages", type=int, default=0, help="Process at most N pages (0 = no limit)")
    parser.add_argument("--min-section-len", type=int, default=200, help="Minimum section text length")
    args = parser.parse_args()

    snapshot_dir = os.path.abspath(args.snapshot)
    manifest_path = os.path.join(snapshot_dir, "manifest.json")
    if not os.path.exists(manifest_path):
        print(f"[ERROR] manifest.json not found: {manifest_path}")
        return 2

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    pages_manifest = manifest.get("items") or []
    if not isinstance(pages_manifest, list):
        print("[ERROR] manifest.items must be a list")
        return 2

    extracted_pages: list[ExtractedPage] = []
    processed = 0
    for m in pages_manifest:
        if args.max_pages and processed >= args.max_pages:
            break
        if not isinstance(m, dict):
            continue
        url = (m.get("url") or "").strip()
        rel_path = (m.get("path") or "").strip()
        path_url = (m.get("path_url") or "").strip()
        if not url or not rel_path:
            continue

        html_path = os.path.join(snapshot_dir, rel_path)
        if not os.path.exists(html_path):
            continue

        with open(html_path, "rb") as f:
            html_bytes = f.read()

        title, raw_sections, full_text = _extract_from_html_bytes(html_bytes)
        if not full_text:
            continue

        # Prefer URL path prefix for deterministic language.
        if "/zh/" in url or path_url.strip("/").startswith("zh/"):
            lang = "zh"
        else:
            # Docs convention: no '/zh' prefix is English.
            lang = "en"

        sections: list[ExtractedSection] = []
        for level, heading, text in raw_sections:
            text2 = _collapse_ws(text)
            if len(text2) < args.min_section_len:
                continue
            sec_id = _slugify(heading, max_len=80)
            th = _sha256_text(text2)
            sections.append(
                ExtractedSection(section_id=sec_id, heading=heading, level=level, text=text2, text_hash=th)
            )

        if not sections:
            continue

        page_id = f"docs_page:{path_url}"
        page = ExtractedPage(
            page_id=page_id,
            url=url,
            path_url=path_url,
            lang=lang,
            title=title,
            category=_guess_category_from_url_path(path_url),
            tags=_guess_tags_from_url_path(path_url),
            sections=sections,
            full_text=full_text,
            full_text_hash=_sha256_text(full_text),
        )
        extracted_pages.append(page)
        processed += 1

    out_obj: dict[str, Any] = {
        "version": 1,
        "generated_at": _now_iso(),
        "source": {"kind": "docs_snapshot", "snapshot_dir": snapshot_dir, "manifest": "manifest.json"},
        "pages": [asdict(p) for p in extracted_pages],
    }

    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out_obj, f, ensure_ascii=False, indent=2)

    print(f"Wrote: {args.out} (pages={len(extracted_pages)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

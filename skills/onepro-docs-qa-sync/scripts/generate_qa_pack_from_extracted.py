#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _collapse_ws(s: str) -> str:
    s = s.replace("\u00a0", " ")
    s = re.sub(r"[ \t\r\f\v]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def _content_hash(item: dict) -> str:
    data = {
        "title": item.get("title") or "",
        "category": item.get("category") or "",
        "tags": item.get("tags") or [],
        "question_md": item.get("question_md") or "",
        "answer_md": item.get("answer_md") or "",
        "source_urls": item.get("source_urls") or [],
    }
    blob = json.dumps(data, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _split_paragraphs(text: str) -> list[str]:
    text = _collapse_ws(text)
    if not text:
        return []
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    return paras


def _pick_key_points(paras: list[str], lang: str, limit: int = 8) -> list[str]:
    if not paras:
        return []

    if lang == "zh":
        keys = ["步骤", "配置", "注意", "必须", "建议", "错误", "失败", "原因", "解决", "排查", "端口", "防火墙", "权限", "限制", "支持", "不支持"]
    else:
        keys = [
            "step",
            "steps",
            "configure",
            "configuration",
            "note",
            "must",
            "should",
            "recommend",
            "error",
            "fail",
            "cause",
            "fix",
            "troubleshoot",
            "port",
            "firewall",
            "permission",
            "limit",
            "supported",
            "not supported",
            "prerequisite",
            "require",
        ]

    scored: list[tuple[int, str]] = []
    for p in paras[:40]:
        pl = p.lower()
        score = 0
        for k in keys:
            if k in pl:
                score += 2
        # Prefer shorter, actionable paragraphs.
        if 40 <= len(p) <= 400:
            score += 1
        if score:
            scored.append((score, p))

    scored.sort(key=lambda x: (-x[0], len(x[1])))
    out: list[str] = []
    for _, p in scored:
        if p in out:
            continue
        out.append(p)
        if len(out) >= limit:
            break

    # Fallback: first 2 paragraphs if nothing matched.
    if not out:
        out = paras[:2]
    return out


def _build_answer(paras: list[str], lang: str) -> dict[str, str]:
    """
    Build three answer variants for 3 Q&As: overview/how-to/troubleshooting-ish.
    These are content-driven (extractive) with light structure.
    """
    key_points = _pick_key_points(paras, lang=lang, limit=8)
    overview = paras[:2] if paras else []
    rest = paras[2:]

    if lang == "zh":
        a1_title = "要点概览"
        a2_title = "操作/配置要点"
        a3_title = "常见问题与限制"
        verify_title = "验证方法"
    else:
        a1_title = "Key overview"
        a2_title = "How to use/configure"
        a3_title = "Common issues & limits"
        verify_title = "How to verify"

    def bulletize(ps: list[str], max_each: int = 500) -> str:
        lines = []
        for p in ps:
            p2 = p.strip()
            if len(p2) > max_each:
                p2 = p2[:max_each].rstrip() + "…"
            lines.append(f"- {p2}")
        return "\n".join(lines).strip()

    # Overview answer: overview + key points.
    a1_parts = []
    if overview:
        a1_parts.append(_collapse_ws("\n\n".join(overview)))
    if key_points:
        a1_parts.append(f"**{a1_title}:**\n{bulletize(key_points[:6])}")
    a1 = "\n\n".join([p for p in a1_parts if p]).strip()

    # How-to answer: focus on imperative / procedural paragraphs if present.
    how_ps = []
    if lang == "zh":
        how_re = re.compile(r"(步骤|配置|如何|操作|使用|设置|安装|部署|示例)")
    else:
        how_re = re.compile(r"(step|steps|configure|how to|usage|use|install|deploy|example)", re.IGNORECASE)
    for p in (key_points + rest)[:60]:
        if how_re.search(p):
            how_ps.append(p)
        if len(how_ps) >= 8:
            break
    if not how_ps:
        how_ps = key_points[:6] or overview

    a2 = f"**{a2_title}:**\n{bulletize(how_ps)}".strip()

    # Troubleshooting/limits: pick paragraphs with error/limit words.
    ts_ps = []
    if lang == "zh":
        ts_re = re.compile(r"(错误|失败|原因|解决|排查|限制|不支持|注意|权限|端口|防火墙)")
    else:
        ts_re = re.compile(
            r"(error|fail|cause|fix|troubleshoot|limit|not supported|note|permission|port|firewall)",
            re.IGNORECASE,
        )
    for p in paras[:80]:
        if ts_re.search(p):
            ts_ps.append(p)
        if len(ts_ps) >= 8:
            break
    if not ts_ps:
        ts_ps = key_points[:6]

    verify_ps = []
    if lang == "zh":
        v_re = re.compile(r"(验证|确认|检查|查看|日志|状态)")
    else:
        v_re = re.compile(r"(verify|check|log|status|confirm)", re.IGNORECASE)
    for p in paras[:80]:
        if v_re.search(p):
            verify_ps.append(p)
        if len(verify_ps) >= 4:
            break

    a3_parts = [f"**{a3_title}:**\n{bulletize(ts_ps)}" if ts_ps else ""]
    if verify_ps:
        a3_parts.append(f"**{verify_title}:**\n{bulletize(verify_ps, max_each=400)}")
    a3 = "\n\n".join([p for p in a3_parts if p]).strip()

    return {"a1": a1, "a2": a2, "a3": a3}


def _build_questions(heading: str, lang: str) -> list[str]:
    h = heading.strip() or ("该功能" if lang == "zh" else "this feature")
    if lang == "zh":
        return [
            f"{h} 是什么？适用场景有哪些？",
            f"如何配置或使用 {h}？",
            f"{h} 有哪些常见问题、限制或注意事项？",
        ]
    return [
        f"What is {h} and when should I use it?",
        f"How do I configure or use {h}?",
        f"What are common issues, limits, or notes for {h}?",
    ]


def _wrap_for_en_site_from_zh(answer_md_zh: str, heading: str) -> str:
    """
    English-site fallback when source docs are Chinese-only.
    Keep content faithful by embedding Chinese extracts, but provide an English framing.
    """
    h = heading.strip() or "this section"
    return (
        f"**English note:** The source documentation for “{h}” is currently Chinese-only. "
        f"The key points below are extracted from the Chinese docs.\n\n"
        f"---\n\n{answer_md_zh}"
    ).strip()


def _build_tags(page_tags: list[str], heading: str, lang: str) -> list[str]:
    tags = [t.strip() for t in (page_tags or []) if str(t).strip()]
    if heading:
        tags.append(heading if lang == "zh" else heading.lower())
    # Dedup while preserving order.
    seen = set()
    out = []
    for t in tags:
        t2 = str(t).strip()
        if not t2 or t2 in seen:
            continue
        seen.add(t2)
        out.append(t2[:50])
    return out[:20]


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate EN/ZH Q&A pack JSON from outputs/docs_extracted.json.")
    parser.add_argument("--in", dest="in_path", required=True, help="Input extracted docs JSON (from extract_docs_snapshot.py)")
    parser.add_argument("--out-en", default="outputs/qa_pack_en.json", help="Output EN pack path")
    parser.add_argument("--out-zh", default="outputs/qa_pack_zh.json", help="Output ZH pack path")
    parser.add_argument("--max-pages", type=int, default=0, help="Process at most N pages (0 = no limit)")
    parser.add_argument("--max-sections-per-page", type=int, default=6, help="Process at most N sections per page")
    parser.add_argument("--qas-per-section", type=int, default=3, choices=[1, 2, 3], help="Generate 1-3 QAs per section")
    parser.add_argument("--min-section-len", type=int, default=250, help="Skip sections whose extracted text is shorter")
    parser.add_argument(
        "--en-from-zh",
        action="store_true",
        help="If docs are Chinese-only, also generate an English pack that embeds Chinese extracts with English framing.",
    )
    args = parser.parse_args()

    with open(args.in_path, "r", encoding="utf-8") as f:
        extracted = json.load(f)

    pages = extracted.get("pages") or []
    if not isinstance(pages, list):
        print("[ERROR] extracted.pages must be a list")
        return 2

    src = extracted.get("source") or {}
    src_dir = src.get("snapshot_dir") if isinstance(src, dict) else None

    pack_en: dict[str, Any] = {
        "version": 1,
        "generated_at": _now_iso(),
        "lang": "en",
        "source": {"kind": "docs_extracted", "extracted_file": os.path.abspath(args.in_path), "snapshot_dir": src_dir},
        "items": [],
    }
    pack_zh: dict[str, Any] = {
        "version": 1,
        "generated_at": _now_iso(),
        "lang": "zh",
        "source": {"kind": "docs_extracted", "extracted_file": os.path.abspath(args.in_path), "snapshot_dir": src_dir},
        "items": [],
    }

    processed_pages = 0
    used_source_ids_en: set[str] = set()
    used_source_ids_zh: set[str] = set()
    for page in pages:
        if args.max_pages and processed_pages >= args.max_pages:
            break
        if not isinstance(page, dict):
            continue
        url = page.get("url") or ""
        path_url = page.get("path_url") or ""
        lang = page.get("lang") or "en"
        category = page.get("category") or "Docs"
        page_tags = page.get("tags") or []
        sections = page.get("sections") or []
        if not isinstance(sections, list) or not url:
            continue

        # Pick up to N sections, preferring longer ones.
        usable = []
        for s in sections:
            if not isinstance(s, dict):
                continue
            txt = _collapse_ws(s.get("text") or "")
            if len(txt) < args.min_section_len:
                continue
            usable.append((len(txt), s))
        usable.sort(key=lambda x: -x[0])
        usable = usable[: args.max_sections_per_page]

        seen_section_keys: set[tuple[str, str]] = set()
        for _, sec in usable:
            heading = (sec.get("heading") or "").strip() or (page.get("title") or "").strip()
            section_id = (sec.get("section_id") or "").strip()
            if not section_id:
                section_id = "sec"
            text_hash = (sec.get("text_hash") or "").strip()
            if not text_hash:
                # Fallback: derive from content if missing.
                text_hash = hashlib.sha256(_collapse_ws(sec.get("text") or "").encode("utf-8")).hexdigest()
            th8 = text_hash[:8]
            k = (section_id, text_hash)
            if k in seen_section_keys:
                continue
            seen_section_keys.add(k)
            text = _collapse_ws(sec.get("text") or "")
            paras = _split_paragraphs(text)
            if not paras:
                continue

            eff_lang = lang if lang in {"en", "zh"} else "en"
            q_list = _build_questions(heading, lang=eff_lang)
            answers = _build_answer(paras, lang=eff_lang)
            tags = _build_tags(page_tags=page_tags, heading=heading, lang=lang)

            # Use deterministic source_id pattern for dedupe.
            # docs:<path_url>#qa-<section_id>-<text_hash8>-<i>
            # (text_hash8 disambiguates repeated headings/section ids within the same page)
            base = f"docs:{path_url}#qa-{section_id}-{th8}"
            items_out = []
            if args.qas_per_section >= 1:
                items_out.append((1, q_list[0], answers["a1"]))
            if args.qas_per_section >= 2:
                items_out.append((2, q_list[1], answers["a2"]))
            if args.qas_per_section >= 3:
                items_out.append((3, q_list[2], answers["a3"]))

            for i, title, answer_md in items_out:
                source_id = f"{base}-{i}"
                item = {
                    "source_id": source_id,
                    "title": title,
                    "category": category,
                    "question_md": title,
                    "answer_md": answer_md,
                    "tags": tags,
                    "source_urls": [url],
                }
                item["content_hash"] = _content_hash(item)
                if lang == "zh":
                    if source_id in used_source_ids_zh:
                        # Deterministic collision breaker (rare, but possible for duplicated sections).
                        n = 2
                        while f"{source_id}-x{n}" in used_source_ids_zh:
                            n += 1
                        item["source_id"] = f"{source_id}-x{n}"
                        item["content_hash"] = _content_hash(item)
                        source_id = item["source_id"]
                    used_source_ids_zh.add(source_id)
                    pack_zh["items"].append(item)
                    if args.en_from_zh:
                        item_en = dict(item)
                        item_en["answer_md"] = _wrap_for_en_site_from_zh(item["answer_md"], heading=heading)
                        item_en["content_hash"] = _content_hash(item_en)
                        sid_en = item_en["source_id"]
                        if sid_en in used_source_ids_en:
                            n = 2
                            while f"{sid_en}-x{n}" in used_source_ids_en:
                                n += 1
                            item_en["source_id"] = f"{sid_en}-x{n}"
                            item_en["content_hash"] = _content_hash(item_en)
                            sid_en = item_en["source_id"]
                        used_source_ids_en.add(sid_en)
                        pack_en["items"].append(item_en)
                else:
                    if source_id in used_source_ids_en:
                        n = 2
                        while f"{source_id}-x{n}" in used_source_ids_en:
                            n += 1
                        item["source_id"] = f"{source_id}-x{n}"
                        item["content_hash"] = _content_hash(item)
                        source_id = item["source_id"]
                    used_source_ids_en.add(source_id)
                    pack_en["items"].append(item)

        processed_pages += 1

    os.makedirs(os.path.dirname(os.path.abspath(args.out_en)) or ".", exist_ok=True)
    os.makedirs(os.path.dirname(os.path.abspath(args.out_zh)) or ".", exist_ok=True)
    with open(args.out_en, "w", encoding="utf-8") as f:
        json.dump(pack_en, f, ensure_ascii=False, indent=2)
    with open(args.out_zh, "w", encoding="utf-8") as f:
        json.dump(pack_zh, f, ensure_ascii=False, indent=2)

    print(f"Wrote EN pack: {args.out_en} (items={len(pack_en['items'])})")
    print(f"Wrote ZH pack: {args.out_zh} (items={len(pack_zh['items'])})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

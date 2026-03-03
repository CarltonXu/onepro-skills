#!/usr/bin/env python3
import argparse
import hashlib
import json
import sys


REQUIRED_ITEM_FIELDS = ["source_id", "title", "category", "question_md", "answer_md", "tags", "source_urls"]


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


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Q&A pack JSON and optionally fill content_hash.")
    parser.add_argument("--in", dest="in_path", required=True, help="Input Q&A pack JSON")
    parser.add_argument("--out", dest="out_path", help="Write updated pack JSON (fills content_hash when missing)")
    args = parser.parse_args()

    with open(args.in_path, "r", encoding="utf-8") as f:
        pack = json.load(f)

    if pack.get("version") != 1:
        print(f"[WARN] pack.version={pack.get('version')!r} (expected 1)")

    items = pack.get("items")
    if not isinstance(items, list):
        print("[ERROR] pack.items must be a list")
        return 2

    ok = True
    seen: set[str] = set()
    for idx, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            print(f"[ERROR] item {idx} is not an object")
            ok = False
            continue
        for f in REQUIRED_ITEM_FIELDS:
            if f not in item:
                print(f"[ERROR] item {idx} missing field: {f}")
                ok = False
        sid = item.get("source_id")
        if isinstance(sid, str) and sid:
            if sid in seen:
                print(f"[ERROR] duplicate source_id: {sid}")
                ok = False
            seen.add(sid)
        if not item.get("content_hash"):
            item["content_hash"] = _content_hash(item)

    if args.out_path:
        with open(args.out_path, "w", encoding="utf-8") as f:
            json.dump(pack, f, ensure_ascii=False, indent=2)
        print(f"Wrote: {args.out_path}")

    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
import argparse
import json
import os
from datetime import datetime, timezone


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def main() -> int:
    parser = argparse.ArgumentParser(description="Render Q&A pack JSON to a Markdown archive.")
    parser.add_argument("--in", dest="in_path", required=True, help="Input Q&A pack JSON")
    parser.add_argument("--out", dest="out_path", required=True, help="Output Markdown file")
    args = parser.parse_args()

    with open(args.in_path, "r", encoding="utf-8") as f:
        pack = json.load(f)

    items = pack.get("items") or []
    lang = pack.get("lang") or "unknown"
    generated_at = pack.get("generated_at") or _now_iso()

    os.makedirs(os.path.dirname(os.path.abspath(args.out_path)) or ".", exist_ok=True)
    with open(args.out_path, "w", encoding="utf-8") as out:
        out.write(f"# Q&A Archive ({lang})\n\n")
        out.write(f"- Generated at: {generated_at}\n")
        src = pack.get("source") or {}
        if isinstance(src, dict) and src:
            out.write(f"- Source: `{src.get('kind', 'unknown')}`\n")
            if src.get("snapshot_dir"):
                out.write(f"- Snapshot: `{src.get('snapshot_dir')}`\n")
        out.write("\n---\n\n")

        for i, it in enumerate(items, start=1):
            title = (it.get("title") or "").strip()
            category = (it.get("category") or "").strip()
            tags = it.get("tags") or []
            source_urls = it.get("source_urls") or []

            out.write(f"## {i}. {title}\n\n")
            if category:
                out.write(f"**Category:** {category}\n\n")
            if tags:
                out.write("**Tags:** " + ", ".join(tags) + "\n\n")
            if source_urls:
                out.write("**Sources:**\n")
                for u in source_urls:
                    out.write(f"- {u}\n")
                out.write("\n")

            q = (it.get("question_md") or "").rstrip()
            a = (it.get("answer_md") or "").rstrip()

            out.write("### Question\n\n")
            out.write(q + "\n\n")
            out.write("### Answer\n\n")
            out.write(a + "\n\n")
            out.write("---\n\n")

    print(f"Wrote: {args.out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

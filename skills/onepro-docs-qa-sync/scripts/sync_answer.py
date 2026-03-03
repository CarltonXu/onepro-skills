#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import sys
import ssl
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

def _load_env_file(path: str) -> None:
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.lower().startswith("export "):
                line = line[7:].lstrip()
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip("'").strip('"')
            if k and k not in os.environ:
                os.environ[k] = v


def _env(name: str, default: str | None = None) -> str | None:
    v = os.environ.get(name)
    return v if v is not None and v != "" else default


def _json_request(method: str, url: str, headers: dict, payload: dict | None) -> dict:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, method=method.upper())
    for k, v in headers.items():
        if v is not None:
            req.add_header(k, v)
    if payload is not None:
        req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=60, context=ssl._create_unverified_context()) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else ""
        raise RuntimeError(f"HTTP {e.code} for {method} {url}: {raw[:2000]}")


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


def _source_key(source_id: str) -> str:
    """
    Short, stable key derived from source_id for server-side search dedupe.
    Answer /search enforces q length <= 60, so we cannot search the full source_id.
    """
    h = hashlib.sha256(source_id.encode("utf-8")).hexdigest()
    return h[:16]  # 64-bit hex, short and collision-resistant enough for practical use


def _search_token(source_id: str) -> str:
    """
    A short token that is safe for Answer search `q` (<=60 chars) and is likely to be indexed as a word.
    Avoid punctuation-heavy strings like "key=..." which may be tokenized away.
    """
    return f"opqa{_source_key(source_id)}"


def _marker(source_id: str) -> str:
    # Hidden marker to help search/debug without showing in rendered HTML.
    token = _search_token(source_id)
    # Keep a short searchable token and also include full source_id for debugging.
    return f"\n\n<!-- onepro-docs-qa-sync:{token} source_id={source_id} -->\n"


def _load_state(path: str) -> dict:
    if not os.path.exists(path):
        return {"version": 1, "updated_at": _now_iso(), "items": {}}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_state(path: str, state: dict) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    state["updated_at"] = _now_iso()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def _auth_headers() -> dict:
    api_key = _env("ANSWER_API_KEY")
    if not api_key:
        raise RuntimeError("Missing env ANSWER_API_KEY")
    header = _env("ANSWER_API_KEY_HEADER", "Authorization")
    # Swagger declares ApiKeyAuth in header, but does not define a prefix.
    # Default to sending the raw key value; set ANSWER_API_KEY_PREFIX if your deployment needs it.
    prefix = _env("ANSWER_API_KEY_PREFIX", "")
    value = f"{prefix} {api_key}".strip() if prefix else api_key
    return {header: value}


def _build_url(path: str) -> str:
    base = _env("ANSWER_BASE_URL")
    if not base:
        raise RuntimeError("Missing env ANSWER_BASE_URL")
    if path.startswith("http://") or path.startswith("https://"):
        return path
    return base.rstrip("/") + "/" + path.lstrip("/")


def _create_question(item: dict, apply: bool) -> dict:
    create_path = _env("ANSWER_CREATE_QUESTION_PATH")
    if not create_path:
        raise RuntimeError("Missing env ANSWER_CREATE_QUESTION_PATH")

    title = (item["title"] or "").strip()
    question_md = (item.get("question_md") or "").rstrip() + _marker(item["source_id"])
    tags = item.get("tags") or []

    payload = {
        "title": title,
        "content": question_md,
        "tags": [_to_tag_item(t) for t in tags],
    }

    if not apply:
        return {"dry_run": True, "request": {"method": "POST", "path": create_path, "payload": payload}}

    return _json_request("POST", _build_url(create_path), {**_auth_headers()}, payload)


def _slugify_tag(tag: str) -> str:
    out = []
    for ch in tag.strip().lower():
        if ch.isalnum():
            out.append(ch)
        elif ch in {" ", "_", "-", ".", "/"}:
            out.append("-")
    slug = "".join(out).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug[:35] if slug else "tag"


def _to_tag_item(tag: str) -> dict:
    tag = (tag or "").strip()
    return {"display_name": tag[:35], "slug_name": _slugify_tag(tag), "original_text": ""}


def _create_answer(question_id: str, item: dict, apply: bool) -> dict:
    create_path = _env("ANSWER_CREATE_ANSWER_PATH")
    if not create_path:
        return {"skipped": True, "reason": "ANSWER_CREATE_ANSWER_PATH not set"}

    answer_md = (item.get("answer_md") or "").rstrip() + _marker(item["source_id"])
    payload = {"content": answer_md, "question_id": str(question_id)}

    if not apply:
        return {"dry_run": True, "request": {"method": "POST", "path": create_path, "payload": payload}}

    return _json_request("POST", _build_url(create_path), {**_auth_headers()}, payload)


def _create_question_and_answer(item: dict, apply: bool) -> dict:
    create_path = _env("ANSWER_CREATE_QA_PATH")
    if not create_path:
        return {"skipped": True, "reason": "ANSWER_CREATE_QA_PATH not set"}

    title = (item["title"] or "").strip()
    question_md = (item.get("question_md") or "").rstrip() + _marker(item["source_id"])
    answer_md = (item.get("answer_md") or "").rstrip() + _marker(item["source_id"])
    tags = item.get("tags") or []

    payload = {
        "title": title,
        "content": question_md,
        "answer_content": answer_md,
        "tags": [_to_tag_item(t) for t in tags],
    }

    if not apply:
        return {"dry_run": True, "request": {"method": "POST", "path": create_path, "payload": payload}}

    return _json_request("POST", _build_url(create_path), {**_auth_headers()}, payload)


def _extract_question_id(resp: dict) -> str | None:
    # Try common response shapes.
    for key in ("id", "question_id", "questionId"):
        if key in resp and isinstance(resp[key], (str, int)):
            return str(resp[key])
    data = resp.get("data")
    if isinstance(data, dict):
        for key in ("id", "question_id", "questionId"):
            if key in data and isinstance(data[key], (str, int)):
                return str(data[key])
        # Sometimes payload is nested again (e.g. {data: {info: {id: ...}}})
        info = data.get("info")
        if isinstance(info, dict):
            for key in ("id", "question_id", "questionId"):
                if key in info and isinstance(info[key], (str, int)):
                    return str(info[key])
    return None


def _search_existing_question(source_id: str) -> str | None:
    search_path = _env("ANSWER_SEARCH_PATH")
    if not search_path:
        return None
    # Answer API restricts q to max 60 characters; search by short token only.
    q = _search_token(source_id)
    order = _env("ANSWER_SEARCH_ORDER", "relevance")
    url = _build_url(search_path) + f"?q={urllib.parse.quote(q)}&order={urllib.parse.quote(order)}"
    resp = _json_request("GET", url, {**_auth_headers()}, None)
    data = resp.get("data")
    if not isinstance(data, dict):
        return None
    lst = data.get("list")
    if not isinstance(lst, list):
        return None
    for r in lst:
        if not isinstance(r, dict):
            continue
        obj = r.get("object")
        if not isinstance(obj, dict):
            continue
        # Ensure the returned object actually contains our token (avoid false positives).
        excerpt = obj.get("excerpt")
        if isinstance(excerpt, str) and q not in excerpt:
            continue
        # Search objects may contain id or question_id.
        for key in ("id", "question_id"):
            if key in obj and isinstance(obj[key], (str, int)):
                return str(obj[key])
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync Q&A pack to Apache Answer with dedupe (dry-run by default).")
    parser.add_argument("--in", dest="in_path", required=True, help="Input Q&A pack JSON")
    parser.add_argument("--state", required=True, help="State file path (JSON)")
    parser.add_argument("--site", choices=["en", "zh"], help="Just a label for logging")
    parser.add_argument("--env-file", help="Optional .env file (KEY=VALUE or 'export KEY=VALUE'); does not override existing env")
    parser.add_argument("--apply", action="store_true", help="Actually create content (otherwise dry-run)")
    parser.add_argument(
        "--search-dedupe",
        action="store_true",
        help="Use server-side /search to avoid duplicates if state.json is missing (apply-mode only).",
    )
    parser.add_argument(
        "--write-state-on-dry-run",
        action="store_true",
        help="Write planned items into state.json during dry-run (default: do not modify state on dry-run).",
    )
    parser.add_argument("--limit", type=int, default=0, help="Process at most N items (0 = no limit)")
    args = parser.parse_args()

    if args.env_file:
        _load_env_file(args.env_file)

    with open(args.in_path, "r", encoding="utf-8") as f:
        pack = json.load(f)

    items = pack.get("items") or []
    state = _load_state(args.state)
    state_items = state.setdefault("items", {})

    created = 0
    skipped = 0
    changed = 0

    for idx, item in enumerate(items, start=1):
        if args.limit and idx > args.limit:
            break

        source_id = item.get("source_id")
        if not source_id:
            print(f"[WARN] item {idx} missing source_id; skipping")
            skipped += 1
            continue

        item_hash = item.get("content_hash") or _content_hash(item)
        item["content_hash"] = item_hash

        prev = state_items.get(source_id)
        if isinstance(prev, dict):
            prev_hash = prev.get("content_hash")
            if prev_hash == item_hash:
                skipped += 1
                continue
            changed += 1
            # Default safe behavior: do not auto-update (endpoint may differ).
            print(f"[CHANGED] {source_id} content changed; skipping update (configure update endpoints if needed)")
            continue

        # Optional server-side dedupe if local state is missing.
        existing_id = None
        if args.apply and args.search_dedupe:
            try:
                existing_id = _search_existing_question(source_id)
            except Exception as e:
                print(f"[WARN] search failed for {source_id}: {e}")
        if existing_id:
            skipped += 1
            if args.apply or args.write_state_on_dry_run:
                state_items[source_id] = {
                    "content_hash": item_hash,
                    "created_at": _now_iso(),
                    "site": args.site or "",
                    "question_id": existing_id,
                    "note": "found_by_search",
                }
            continue

        # Create question + answer
        qa_resp = None
        q_resp = None
        a_resp = None
        q_id = None
        # Prefer one-call create if configured (Swagger provides /answer/api/v1/question/answer).
        if _env("ANSWER_CREATE_QA_PATH"):
            qa_resp = _create_question_and_answer(item, apply=args.apply)
            if args.apply:
                q_id = _extract_question_id(qa_resp)
        else:
            q_resp = _create_question(item, apply=args.apply)
            q_id = None if not args.apply else _extract_question_id(q_resp)
            if args.apply and q_id:
                a_resp = _create_answer(q_id, item, apply=args.apply)

        created += 1
        if args.apply or args.write_state_on_dry_run:
            state_items[source_id] = {
                "content_hash": item_hash,
                "created_at": _now_iso(),
                "site": args.site or "",
                "question_id": q_id,
                "last_qa_response": qa_resp if args.apply else None,
                "last_question_response": q_resp if args.apply else None,
                "last_answer_response": a_resp if args.apply else None,
            }

        if not args.apply:
            print(f"[DRY-RUN] would create: {source_id}  title={item.get('title')!r}")

    if args.apply or args.write_state_on_dry_run:
        _save_state(args.state, state)
    print(f"Done. created={created} skipped={skipped} changed_skipped={changed} apply={args.apply}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

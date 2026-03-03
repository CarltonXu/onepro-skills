#!/usr/bin/env python3
import argparse
import json
import sys
import textwrap
import urllib.request


def _load_json_from_url(url: str) -> dict:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = resp.read().decode("utf-8", errors="replace")
    return json.loads(body)


def _load_json_from_file(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _iter_paths(spec: dict):
    paths = spec.get("paths", {})
    for path, methods in paths.items():
        if not isinstance(methods, dict):
            continue
        for method, op in methods.items():
            if method.lower() not in {"get", "post", "put", "patch", "delete"}:
                continue
            if not isinstance(op, dict):
                continue
            yield path, method.lower(), op


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect Apache Answer OpenAPI/Swagger doc for paths/security.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--swagger-url", help="OpenAPI/Swagger JSON URL (e.g. https://host/swagger/doc.json)")
    src.add_argument("--swagger-file", help="OpenAPI/Swagger JSON file path")
    parser.add_argument(
        "--grep",
        default="question,answer,tag,search,post,article,comment",
        help="Comma-separated keywords to filter interesting endpoints.",
    )
    args = parser.parse_args()

    spec = _load_json_from_url(args.swagger_url) if args.swagger_url else _load_json_from_file(args.swagger_file)

    print("== OpenAPI summary ==")
    if "openapi" in spec:
        print(f"openapi: {spec.get('openapi')}")
    if "swagger" in spec:
        print(f"swagger: {spec.get('swagger')}")
    print(f"title: {((spec.get('info') or {}).get('title'))!r}")
    print(f"version: {((spec.get('info') or {}).get('version'))!r}")

    servers = spec.get("servers")
    if isinstance(servers, list) and servers:
        print("servers:")
        for s in servers[:5]:
            url = (s or {}).get("url")
            if url:
                print(f"  - {url}")
    else:
        base_path = spec.get("basePath")
        if base_path:
            print(f"basePath: {base_path}")

    print("\n== Security schemes ==")
    components = spec.get("components") or {}
    security_schemes = (components.get("securitySchemes") or {}) if isinstance(components, dict) else {}
    if not security_schemes:
        security_schemes = spec.get("securityDefinitions") or {}
    if not security_schemes:
        print("(none found)")
    else:
        for name, scheme in security_schemes.items():
            if not isinstance(scheme, dict):
                continue
            print(f"- {name}: type={scheme.get('type')!r} in={scheme.get('in')!r} name={scheme.get('name')!r}")

    print("\n== Interesting endpoints ==")
    keywords = [k.strip().lower() for k in args.grep.split(",") if k.strip()]
    hits = []
    for path, method, op in _iter_paths(spec):
        blob = " ".join(
            str(x)
            for x in [
                path,
                method,
                op.get("operationId"),
                op.get("summary"),
                op.get("description"),
                ",".join(op.get("tags", []) or []),
            ]
        ).lower()
        if any(k in blob for k in keywords):
            hits.append((path, method, op))

    if not hits:
        print("(no matches; try --grep with different keywords)")
        return 0

    for path, method, op in hits[:200]:
        op_id = op.get("operationId") or "-"
        summary = op.get("summary") or ""
        tags = ",".join(op.get("tags", []) or [])
        print(f"- {method.upper():6s} {path}  opId={op_id}  tags={tags}")
        if summary:
            print(textwrap.indent(textwrap.fill(summary, width=100), prefix="  "))

    if len(hits) > 200:
        print(f"... truncated ({len(hits)} total matches)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

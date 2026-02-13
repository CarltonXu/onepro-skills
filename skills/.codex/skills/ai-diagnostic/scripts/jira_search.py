#!/usr/bin/env python3
import argparse
import base64
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

DEFAULT_FIELDS = [
    "summary",
    "description",
    "resolution",
    "fixVersions",
    "status",
    "priority",
    "components",
    "labels",
    "updated",
    "comment",
    "issuetype",
]

STOP_WORDS = set(
    [
        "the",
        "and",
        "or",
        "a",
        "an",
        "to",
        "in",
        "of",
        "for",
        "on",
        "with",
        "is",
        "are",
        "was",
        "were",
        "be",
        "this",
        "that",
        "it",
        "as",
        "at",
        "by",
        "from",
        "error",
        "failed",
        "failure",
        "exception",
        "timeout",
    ]
)


def _tokenize(text):
    if not text:
        return []
    tokens = re.findall(r"[A-Za-z0-9_.-]+", text.lower())
    return [t for t in tokens if t not in STOP_WORDS and len(t) > 1]


def _safe_text(value):
    if value is None:
        return ""
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return " ".join(_safe_text(v) for v in value)
    return str(value)


def _extract_solution_summary(comments_dict):
    if not isinstance(comments_dict, dict):
        return ""
    comments = comments_dict.get("comments", []) or []
    if not comments:
        return ""
    # Prefer the latest comment body as solution summary
    last = comments[-1]
    return _safe_text(last.get("body", "")).strip()


def _latest_fix_version(fix_versions):
    if not fix_versions:
        return ""
    # Jira returns list of dicts with name/releaseDate
    def sort_key(v):
        date_str = v.get("releaseDate") or ""
        try:
            return datetime.strptime(date_str, "%Y-%m-%d")
        except Exception:
            return datetime.min

    try:
        sorted_versions = sorted(fix_versions, key=sort_key, reverse=True)
        return sorted_versions[0].get("name") or ""
    except Exception:
        return fix_versions[0].get("name") if isinstance(fix_versions[0], dict) else ""


def _compute_similarity(query_tokens, issue_text):
    if not query_tokens:
        return 0.0
    text_tokens = set(_tokenize(issue_text))
    if not text_tokens:
        return 0.0
    hit = sum(1 for t in query_tokens if t in text_tokens)
    return round(hit / max(len(query_tokens), 1), 3)


def build_jql(keywords, stage=None, module=None, version=None, project_keys=None):
    keywords = [k for k in keywords if k]
    if not keywords:
        keywords = ["error"]
    keyword_expr = " OR ".join(
        [
            f'summary ~ "{k}" OR description ~ "{k}" OR text ~ "{k}"'
            for k in keywords
        ]
    )
    clauses = [f"({keyword_expr})"]

    if stage:
        clauses.append(f'(summary ~ "{stage}" OR description ~ "{stage}" OR text ~ "{stage}")')
    if module:
        clauses.append(f'(summary ~ "{module}" OR description ~ "{module}" OR text ~ "{module}")')
    if version:
        clauses.append(f'(summary ~ "{version}" OR description ~ "{version}" OR text ~ "{version}")')

    if project_keys:
        keys = ", ".join(project_keys)
        clauses.insert(0, f"project in ({keys})")

    return " AND ".join(clauses) + " ORDER BY updated DESC"


def request_jira(base_url, user, password, jql, max_results, fields):
    auth_raw = f"{user}:{password}".encode("utf-8")
    token = base64.b64encode(auth_raw).decode("utf-8")
    payload = {
        "jql": jql,
        "maxResults": max_results,
        "fields": fields,
    }
    data = json.dumps(payload).encode("utf-8")
    url = urllib.parse.urljoin(base_url, "/rest/api/2/search")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Authorization", f"Basic {token}")
    req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read()
        return json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"Jira HTTPError {e.code}: {body}")
    except Exception as e:
        raise RuntimeError(f"Jira request failed: {e}")


def main():
    parser = argparse.ArgumentParser(description="Jira issue search for OnePro diagnostic")
    parser.add_argument("--base-url", default=os.environ.get("JIRA_BASE_URL", ""))
    parser.add_argument("--query", default="", help="free text query keywords")
    parser.add_argument("--stage", default="")
    parser.add_argument("--module", default="")
    parser.add_argument("--version", default="")
    parser.add_argument("--project-keys", default=os.environ.get("JIRA_PROJECT_KEYS", "REQ,PRJ"))
    parser.add_argument("--max", type=int, default=5)
    parser.add_argument("--fields", default="")
    parser.add_argument("--print-jql", action="store_true")
    parser.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()

    base_url = args.base_url or ""
    if not base_url:
        print(json.dumps({"error": "missing base url"}, ensure_ascii=False))
        sys.exit(1)

    user = os.environ.get("JIRA_USER", "")
    password = os.environ.get("JIRA_PASS", "")
    if not user or not password:
        print(json.dumps({"error": "missing JIRA_USER/JIRA_PASS"}, ensure_ascii=False))
        sys.exit(1)

    keywords = _tokenize(args.query)
    if args.query and not keywords:
        keywords = [args.query]

    project_keys = [k.strip() for k in args.project_keys.split(",") if k.strip()]

    jql = build_jql(
        keywords=keywords,
        stage=args.stage,
        module=args.module,
        version=args.version,
        project_keys=project_keys,
    )

    fields = DEFAULT_FIELDS
    if args.fields:
        fields = [f.strip() for f in args.fields.split(",") if f.strip()]

    if args.print_jql:
        print(jql)
        if args.dry_run:
            return

    if args.dry_run:
        print(json.dumps({"jql": jql, "dry_run": True}, ensure_ascii=False, indent=2))
        return

    result = request_jira(base_url, user, password, jql, args.max, fields)

    issues = []
    for item in result.get("issues", []):
        fields_obj = item.get("fields", {})
        summary = fields_obj.get("summary") or ""
        description = fields_obj.get("description") or ""
        comments = ""
        solution_summary = ""
        if isinstance(fields_obj.get("comment"), dict):
            bodies = []
            for c in fields_obj.get("comment", {}).get("comments", []):
                bodies.append(c.get("body") or "")
            comments = "\n".join(bodies)
            solution_summary = _extract_solution_summary(fields_obj.get("comment", {}))

        issue_text = "\n".join([summary, _safe_text(description), comments])
        similarity = _compute_similarity(keywords, issue_text)

        issuetype = fields_obj.get("issuetype", {}) or {}
        labels = fields_obj.get("labels", []) or []
        bug_flag = False
        if isinstance(issuetype, dict) and "bug" in (issuetype.get("name", "").lower()):
            bug_flag = True
        if any("bug" in str(l).lower() for l in labels):
            bug_flag = True

        fix_version = _latest_fix_version(fields_obj.get("fixVersions", []))
        resolution = fields_obj.get("resolution", {}) or {}
        resolution_summary = resolution.get("name") if isinstance(resolution, dict) else _safe_text(resolution)

        issues.append(
            {
                "key": item.get("key", ""),
                "summary": summary,
                "similarity": similarity,
                "bug": "Yes" if bug_flag else "No",
                "fix_version": fix_version,
                "resolution": resolution_summary or "",
                "solution_summary": solution_summary,
                "status": (fields_obj.get("status") or {}).get("name", ""),
                "updated": fields_obj.get("updated", ""),
            }
        )

    output = {
        "jql": jql,
        "count": len(issues),
        "issues": sorted(issues, key=lambda x: x["similarity"], reverse=True),
    }

    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

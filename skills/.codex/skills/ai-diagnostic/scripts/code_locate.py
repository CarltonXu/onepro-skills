#!/usr/bin/env python3
import argparse
import json
import os
import re
import subprocess
import sys
import urllib.parse
from pathlib import Path

REPO_MAP = {
    "newmuse": "hypermotion/newmuse",
    "owl": "hypermotion/owl",
    "crab": "hypermotion/crab",
    "ant": "hypermotion/ant",
    "porter": "hypermotion/porter",
    "mistral": "atomy/mistral",
    "atomy-unicloud": "atomy/atomy-unicloud",
    "unicloud": "hypermotion/unicloud",
    "atomy-obstor": "atomy/atomy-obstor",
    "storplus": "hypermotion/storplus",
    "oneway": "hypermotion/oneway",
    "proxy": "hypermotion/proxy",
    "minitgt": "hypermotion/minitgt",
    "s3block": "hypermotion/SwiftS3Block",
    "hamal": "atomy/hamalv3",
    "windows agent": "hypermotion/windows-agent",
    "linux agent": "hypermotion/egisplus-agent",
    "egisplus-agent": "hypermotion/egisplus-agent",
}

DEFAULT_BASE = "http://192.168.10.254:20080"


def _normalize_module(name: str) -> str:
    return name.strip().lower()


def _auth_url(base_url: str, repo_path: str, user: str, password: str) -> str:
    if not user or not password:
        return f"{base_url}/{repo_path}.git"
    safe_user = urllib.parse.quote(user, safe="")
    safe_pass = urllib.parse.quote(password, safe="")
    return f"{base_url.replace('http://', f'http://{safe_user}:{safe_pass}@')}/{repo_path}.git"


def _branch_candidates(product: str, version: str):
    candidates = []
    if product and version:
        prefix = "HyperBDR" if product.lower() == "hyperbdr" else "HyperMotion"
        candidates.append(f"{prefix}_release_v{version}")
    candidates.extend(["master", "main"])
    return candidates


def _ls_remote_branches(repo_url: str):
    try:
        out = subprocess.check_output(
            ["git", "ls-remote", "--heads", repo_url],
            stderr=subprocess.STDOUT,
            text=True,
            timeout=20,
        )
    except Exception:
        return []
    branches = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) == 2 and parts[1].startswith("refs/heads/"):
            branches.append(parts[1].replace("refs/heads/", ""))
    return branches


def _select_branch(candidates, remote_branches):
    for c in candidates:
        if c in remote_branches:
            return c
    return candidates[0] if candidates else "master"


def _run(cmd, cwd=None):
    return subprocess.check_output(cmd, cwd=cwd, stderr=subprocess.STDOUT, text=True)


def _ensure_repo(clone_dir: Path, repo_url: str, branch: str):
    if clone_dir.exists() and (clone_dir / ".git").exists():
        try:
            _run(["git", "fetch", "--all", "--prune"], cwd=str(clone_dir))
            _run(["git", "checkout", branch], cwd=str(clone_dir))
            _run(["git", "pull", "--ff-only"], cwd=str(clone_dir))
            return
        except Exception:
            pass
    if clone_dir.exists():
        # best-effort cleanup if previous clone failed
        for _ in range(1):
            try:
                subprocess.check_call(["rm", "-rf", str(clone_dir)])
            except Exception:
                break
    _run(["git", "clone", "--depth", "1", "--branch", branch, repo_url, str(clone_dir)])


def _rg_hits(repo_dir: Path, term: str, max_count: int = 5):
    if not term:
        return []
    cmd = ["rg", "-n", "--max-count", str(max_count), term, str(repo_dir)]
    try:
        out = _run(cmd)
    except Exception:
        return []
    hits = []
    for line in out.splitlines():
        # format: path:line:text
        parts = line.split(":", 2)
        if len(parts) == 3:
            hits.append({"file": parts[0], "line": int(parts[1]), "text": parts[2]})
    return hits


def _extract_terms(query, class_name, method_name):
    terms = []
    if class_name:
        terms.append(class_name)
    if method_name:
        terms.append(method_name)
    if query:
        terms.extend(re.findall(r"[A-Za-z0-9_.-]+", query))
    seen = set()
    filtered = []
    for t in terms:
        if t and t not in seen and len(t) > 1:
            filtered.append(t)
            seen.add(t)
    return filtered[:10]


def main():
    parser = argparse.ArgumentParser(description="Locate code by module and error keywords")
    parser.add_argument("--module", required=True)
    parser.add_argument("--product", default="")
    parser.add_argument("--version", default="")
    parser.add_argument("--query", default="", help="error text or keywords")
    parser.add_argument("--class", dest="class_name", default="")
    parser.add_argument("--method", dest="method_name", default="")
    parser.add_argument("--base-url", default=os.environ.get("GIT_BASE_URL", DEFAULT_BASE))
    parser.add_argument("--workdir", default=os.environ.get("CODE_WORKDIR", "/tmp/onepro-code"))
    parser.add_argument("--list-branches", action="store_true")
    parser.add_argument("--max-hits", type=int, default=5)
    args = parser.parse_args()

    module_key = _normalize_module(args.module)
    if module_key not in REPO_MAP:
        print(json.dumps({"error": "unknown module", "module": args.module}, ensure_ascii=False))
        sys.exit(1)

    repo_path = REPO_MAP[module_key]
    user = os.environ.get("GIT_USER", "")
    password = os.environ.get("GIT_PASS", "")

    repo_url_auth = _auth_url(args.base_url, repo_path, user, password)
    repo_url_display = f"{args.base_url}/{repo_path}.git"

    candidates = _branch_candidates(args.product, args.version)
    remote_branches = []
    selected = candidates[0] if candidates else "master"
    if args.list_branches:
        remote_branches = _ls_remote_branches(repo_url_auth)
        if remote_branches:
            selected = _select_branch(candidates, remote_branches)

    workdir = Path(args.workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    clone_dir = workdir / repo_path.replace("/", "_")

    try:
        _ensure_repo(clone_dir, repo_url_auth, selected)
    except Exception as e:
        print(
            json.dumps(
                {
                    "error": "clone_failed",
                    "repo_url": repo_url_display,
                    "branch": selected,
                    "detail": str(e),
                },
                ensure_ascii=False,
            )
        )
        sys.exit(1)

    terms = _extract_terms(args.query, args.class_name, args.method_name)
    hits = []
    for t in terms:
        hits.extend(_rg_hits(clone_dir, t, max_count=args.max_hits))

    # upstream/downstream candidates are heuristic: list files containing method name
    call_chain_candidates = []
    if args.method_name:
        call_chain_candidates = _rg_hits(clone_dir, args.method_name, max_count=10)

    output = {
        "module": args.module,
        "repo_path": repo_path,
        "repo_url": repo_url_display,
        "branch_candidates": candidates,
        "selected_branch": selected,
        "clone_path": str(clone_dir),
        "search_terms": terms,
        "hits": hits[: args.max_hits * max(1, len(terms))],
        "call_chain_candidates": call_chain_candidates,
    }

    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

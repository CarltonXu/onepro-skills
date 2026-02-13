#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import sys
import urllib.parse

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
            timeout=15,
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


def main():
    parser = argparse.ArgumentParser(description="Locate repo and branch for OnePro modules")
    parser.add_argument("--module", required=True)
    parser.add_argument("--product", default="")
    parser.add_argument("--version", default="")
    parser.add_argument("--base-url", default=os.environ.get("GIT_BASE_URL", DEFAULT_BASE))
    parser.add_argument("--list-branches", action="store_true")
    args = parser.parse_args()

    module_key = _normalize_module(args.module)
    if module_key not in REPO_MAP:
        print(json.dumps({"error": "unknown module", "module": args.module}, ensure_ascii=False))
        sys.exit(1)

    repo_path = REPO_MAP[module_key]
    user = os.environ.get("GIT_USER", "")
    password = os.environ.get("GIT_PASS", "")

    repo_url = _auth_url(args.base_url, repo_path, user, password)
    candidates = _branch_candidates(args.product, args.version)

    remote_branches = []
    selected = candidates[0] if candidates else "master"
    if args.list_branches:
        remote_branches = _ls_remote_branches(repo_url)
        if remote_branches:
            selected = _select_branch(candidates, remote_branches)

    output = {
        "module": args.module,
        "repo_path": repo_path,
        "repo_url": args.base_url + "/" + repo_path + ".git",
        "branch_candidates": candidates,
        "selected_branch": selected,
        "remote_branches": remote_branches,
    }

    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

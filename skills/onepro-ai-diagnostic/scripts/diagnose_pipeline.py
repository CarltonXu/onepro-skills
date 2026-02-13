#!/usr/bin/env python3
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile


def _run(cmd, env=None):
    return subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True, env=env)


def _read_lines(path, max_lines=20000):
    try:
        with open(path, "r", errors="ignore") as f:
            lines = f.readlines()
        if len(lines) > max_lines:
            return lines[-max_lines:]
        return lines
    except Exception:
        return []


def _extract_timestamp(line):
    # Match common patterns: 2025-01-01 12:34:56 or 2025-01-01T12:34:56
    m = re.search(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}", line)
    return m.group(0) if m else ""


def _classify_error(text):
    t = text.lower()
    network = any(k in t for k in ["timeout", "timed out", "connection refused", "unreachable", "reset", "connect failed"])
    permission = any(k in t for k in ["permission denied", "unauthorized", "forbidden", "auth failed", "authentication failed"])
    cloud_api = any(k in t for k in ["api", "rate limit", "quota", "throttl"])
    internal = any(k in t for k in ["exception", "traceback", "panic", "nullpointer", "stacktrace", "segfault"])
    error_type = "Unknown"
    if network:
        error_type = "Network"
    elif permission:
        error_type = "Permission"
    elif cloud_api:
        error_type = "CloudAPI"
    elif internal:
        error_type = "InternalException"
    return error_type, network, permission, cloud_api, internal


def _collect_log_files(root):
    paths = []
    for dirpath, _, filenames in os.walk(root):
        for fn in filenames:
            lower = fn.lower()
            if lower.endswith((".log", ".txt", ".out", ".err")):
                paths.append(os.path.join(dirpath, fn))
    return paths


def _analyze_logs(root):
    keywords = ["error", "exception", "failed", "timeout"]
    paths = _collect_log_files(root)
    best_file = ""
    best_hits = []
    total_hits = 0
    first_time = ""
    error_blob = ""

    for p in paths:
        lines = _read_lines(p)
        hits = []
        for idx, line in enumerate(lines):
            if any(k in line.lower() for k in keywords):
                hits.append((idx, line))
        if hits:
            total_hits += len(hits)
            if not first_time:
                ts = _extract_timestamp(hits[0][1])
                if ts:
                    first_time = ts
        if len(hits) > len(best_hits):
            best_hits = hits
            best_file = p
            error_blob = "".join(lines[max(hits[-1][0] - 300, 0) : hits[-1][0] + 1]) if hits else ""

    error_type, network, permission, cloud_api, internal = _classify_error(error_blob)

    module = ""
    if best_file:
        module = os.path.basename(os.path.dirname(best_file))

    return {
        "module": module,
        "error_type": error_type,
        "first_occurrence_time": first_time,
        "repetition_count": total_hits,
        "network_related": "Yes" if network else "No",
        "permission_related": "Yes" if permission else "No",
        "cloud_api_related": "Yes" if cloud_api else "No",
        "internal_exception": "Yes" if internal else "No",
        "core_log_excerpt": error_blob.strip(),
        "stack_trace_present": "Yes" if "traceback" in error_blob.lower() or "exception" in error_blob.lower() else "No",
    }


def _extract_archive(path):
    tmpdir = tempfile.mkdtemp(prefix="onepro-logs-")
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path, "r") as zf:
            zf.extractall(tmpdir)
        return tmpdir
    try:
        with tarfile.open(path, "r:*") as tf:
            tf.extractall(tmpdir)
        return tmpdir
    except Exception:
        shutil.rmtree(tmpdir, ignore_errors=True)
        return ""


def _ocr_image(path):
    try:
        from PIL import Image  # type: ignore
        import pytesseract  # type: ignore

        img = Image.open(path)
        return pytesseract.image_to_string(img)
    except Exception:
        return ""


def main():
    parser = argparse.ArgumentParser(description="OnePro diagnostic pipeline: Jira + Code")
    parser.add_argument("--query", required=True)
    parser.add_argument("--product", default="")
    parser.add_argument("--stage", default="")
    parser.add_argument("--module", default="")
    parser.add_argument("--version", default="")
    parser.add_argument("--class", dest="class_name", default="")
    parser.add_argument("--method", dest="method_name", default="")
    parser.add_argument("--max", type=int, default=5)
    parser.add_argument("--skip-code", action="store_true")
    parser.add_argument("--log-archive", default="")
    parser.add_argument("--log-path", default="")
    parser.add_argument("--screenshot", default="")
    parser.add_argument("--output-md", action="store_true")
    parser.add_argument("--output-file", default="")
    args = parser.parse_args()

    env = os.environ.copy()

    attachment_types = []
    screenshot_text = ""
    if args.screenshot:
        attachment_types.append("screenshot")
        screenshot_text = _ocr_image(args.screenshot)

    log_root = ""
    if args.log_path:
        attachment_types.append("log_dir")
        log_root = args.log_path
    elif args.log_archive:
        attachment_types.append("log_archive")
        log_root = _extract_archive(args.log_archive)

    log_result = {
        "module": args.module,
        "error_type": "Unknown",
        "first_occurrence_time": "",
        "repetition_count": 0,
        "network_related": "Unknown",
        "permission_related": "Unknown",
        "cloud_api_related": "Unknown",
        "internal_exception": "Unknown",
        "core_log_excerpt": "",
        "stack_trace_present": "Unknown",
    }

    if log_root:
        log_result = _analyze_logs(log_root)

    # Jira search
    jira_cmd = [
        "python3",
        os.path.join(os.path.dirname(__file__), "jira_search.py"),
        "--query",
        args.query,
        "--stage",
        args.stage,
        "--module",
        args.module,
        "--version",
        args.version,
        "--max",
        str(args.max),
    ]
    jira_raw = ""
    jira_json = {}
    try:
        jira_raw = _run(jira_cmd, env=env)
        jira_json = json.loads(jira_raw)
    except Exception as e:
        jira_json = {"error": "jira_failed", "detail": str(e), "raw": jira_raw}

    # Code locate (optional)
    code_json = {}
    if args.skip_code:
        code_json = {"skipped": True}
    else:
        code_cmd = [
            "python3",
            os.path.join(os.path.dirname(__file__), "code_locate.py"),
            "--module",
            args.module,
            "--product",
            args.product,
            "--version",
            args.version,
            "--query",
            args.query,
            "--class",
            args.class_name,
            "--method",
            args.method_name,
            "--list-branches",
        ]
        try:
            code_raw = _run(code_cmd, env=env)
            code_json = json.loads(code_raw)
        except Exception as e:
            code_json = {"error": "code_failed", "detail": str(e)}

    output = {
        "input": {
            "query": args.query,
            "product": args.product,
            "stage": args.stage,
            "module": args.module,
            "version": args.version,
            "class": args.class_name,
            "method": args.method_name,
        },
        "input_analysis": {
            "product": args.product,
            "stage": args.stage,
            "version": args.version,
            "detected_module": args.module,
            "keywords": args.query,
            "attachment_types": attachment_types,
            "stack_trace_present": log_result.get("stack_trace_present", "Unknown"),
            "screenshot_text": screenshot_text,
        },
        "log_analysis_result": log_result,
        "stage_consistency": {
            "consistent": "Unknown",
            "reason": "",
        },
        "jira_match_result": jira_json,
        "code_analysis": {
            "triggered": "Unknown",
            "reason": "",
        },
        "code_localization": code_json,
        "code_analysis_conclusion": {
            "root_cause": "",
            "logic_defect": "Unknown",
            "boundary_not_handled": "Unknown",
            "external_dependency_failure": "Unknown",
            "fix_commit_exists": "Unknown",
        },
        "root_cause_probability": {
            "environment_issue": "",
            "configuration_issue": "",
            "cloud_platform_issue": "",
            "code_defect": "",
            "primary_root_cause": "",
            "confidence_level": "",
        },
        "mitigation_plan": {
            "temporary": [],
            "permanent": [],
            "upgrade_suggestion": "",
        },
        "rd_escalation": {
            "required": "Unknown",
            "priority": "",
            "reason": "",
            "suggested_summary": "",
        },
    }

    if args.output_md:
        content = _render_markdown(output)
    else:
        content = json.dumps(output, ensure_ascii=False, indent=2)

    if args.output_file:
        with open(args.output_file, "w", encoding="utf-8") as f:
            f.write(content)
    print(content)


def _render_markdown(data):
    basic = data.get("input_analysis", {})
    log_res = data.get("log_analysis_result", {})
    stage = data.get("stage_consistency", {})
    jira = data.get("jira_match_result", {})
    code_loc = data.get("code_localization", {})
    rc = data.get("root_cause_probability", {})
    mit = data.get("mitigation_plan", {})
    esc = data.get("rd_escalation", {})

    jira_rows = []
    for i in jira.get("issues", []):
        jira_rows.append(
            "| {key} | {sim} | {bug} | {fix} | {status} | {res} | {sol} |".format(
                key=i.get("key", ""),
                sim=i.get("similarity", ""),
                bug=i.get("bug", ""),
                fix=i.get("fix_version", ""),
                status=i.get("status", ""),
                res=i.get("resolution", ""),
                sol=i.get("solution_summary", ""),
            )
        )
    if not jira_rows:
        jira_rows = ["| - | - | - | - | - | - | - |"]

    md = [
        "# Hyper Diagnostic Report",
        "",
        "## 1. Basic Information",
        f"- Product: {basic.get('product','')}",
        f"- Stage: {basic.get('stage','')}",
        f"- Version: {basic.get('version','')}",
        f"- Module: {basic.get('detected_module','')}",
        "",
        "## 2. Core Error Summary",
        f"- Error Type: {log_res.get('error_type','')}",
        "- Key Errors:",
        f"  - {log_res.get('core_log_excerpt','')[:200].replace('\n',' ')}",
        f"- First Occurrence Time: {log_res.get('first_occurrence_time','')}",
        f"- Repetition Count: {log_res.get('repetition_count','')}",
        "",
        "## 3. Evidence Chain",
        "### Screenshot Findings",
        f"- {basic.get('screenshot_text','')[:200].replace('\n',' ')}",
        "",
        "### Log Findings",
        f"- Network Related: {log_res.get('network_related','')}",
        f"- Permission Related: {log_res.get('permission_related','')}",
        f"- Cloud API Related: {log_res.get('cloud_api_related','')}",
        f"- Internal Exception: {log_res.get('internal_exception','')}",
        "",
        "## 4. Stage Consistency",
        f"- Consistent: {stage.get('consistent','')}",
        f"- Reason: {stage.get('reason','')}",
        "",
        "## 5. Jira Historical Match (Top 5)",
        "| Key | Similarity | Bug | Fix Version | Status | Resolution | Solution Summary |",
        "| --- | --- | --- | --- | --- | --- | --- |",
        *jira_rows,
        "",
        "## 6. Code Localization (if triggered)",
        f"- Triggered: {data.get('code_analysis',{}).get('triggered','')}",
        f"- Reason: {data.get('code_analysis',{}).get('reason','')}",
        f"- Repository: {code_loc.get('repo_url','')}",
        f"- Branch: {code_loc.get('selected_branch','')}",
        f"- File Path: {'' if not code_loc.get('hits') else code_loc.get('hits')[0].get('file','')}",
        f"- Class: {data.get('input',{}).get('class','')}",
        f"- Method: {data.get('input',{}).get('method','')}",
        f"- Call Chain: {'' if not code_loc.get('call_chain_candidates') else code_loc.get('call_chain_candidates')[0].get('text','')}",
        "",
        "## 7. Root Cause Probability Table (Total = 100%)",
        "| Category | Probability |",
        "| --- | --- |",
        f"| Environment Issue | {rc.get('environment_issue','')} |",
        f"| Configuration Issue | {rc.get('configuration_issue','')} |",
        f"| Cloud Platform Issue | {rc.get('cloud_platform_issue','')} |",
        f"| Code Defect | {rc.get('code_defect','')} |",
        "",
        f"**Primary Root Cause:** {rc.get('primary_root_cause','')}",
        f"**Confidence Level:** {rc.get('confidence_level','')}",
        "",
        "## 8. Mitigation Plan",
        "### Temporary",
        *[f"1. {s}" for s in mit.get("temporary", [])] if mit.get("temporary") else ["1. "],
        "",
        "### Permanent",
        *[f"1. {s}" for s in mit.get("permanent", [])] if mit.get("permanent") else ["1. "],
        "",
        "### Upgrade Suggestion",
        f"- {mit.get('upgrade_suggestion','')}",
        "",
        "## 9. R&D Escalation Decision",
        f"- Required: {esc.get('required','')}",
        f"- Priority: {esc.get('priority','')}",
        f"- Reason: {esc.get('reason','')}",
        f"- Suggested Escalation Content Summary: {esc.get('suggested_summary','')}",
    ]
    return "\n".join(md)


if __name__ == "__main__":
    main()

---
name: onepro-ai-diagnostic
description: AI-driven fault triage for OnePro HyperBDR/HyperMotion delivery issues. Use when users submit logs (zip/tar.gz), screenshots, or text descriptions and need stage identification, error classification, Jira search, optional bounded code localization, and a structured diagnostic report with mitigation and escalation decisions.
---

# OnePro AI 故障处理

## Overview
对 HyperBDR / HyperMotion 交付问题进行闭环诊断：解析截图与日志包、识别阶段与模块、检索 Jira 历史、在满足触发条件时做有限代码定位，输出结构化报告与解决方案。

## References (Load When Needed)
- `references/onepro-troubleshooting.md`：阶段划分、模块→日志路径映射、日志分析要点与归因示例。用于 STEP 0/1/2 的阶段识别与模块定位。
- `references/jira-rest.md`：Jira Data Center REST 检索指引（Basic 认证、JQL 模板、字段映射）。用于 STEP 3。
- `references/repo-map.md`：模块→仓库映射、分支规则、认证方式。用于 STEP 5。

## Global Rules (Mandatory)
- 严格按步骤顺序执行，不允许跳步。
- 每一步输出结构化中间结果。
- 所有判断给出概率/置信度；根因概率总和必须等于 100%。
- 结论必须有证据链：日志 + Jira +（如触发）代码分析。
- 不在明显环境问题时触发代码分析或拉取代码。
- 代码分析范围限制：单文件 + 上下游调用深度 ≤ 2 层。

## Workflow

### STEP 0 — Input Parsing
识别产品、阶段、版本、关键词、截图与日志包类型。

输出：
```
[Input Analysis]
Product:
Stage:
Version:
Detected Module:
Keywords:
Attachment Types: (screenshot/log zip/tar.gz/text)
Stack Trace Present: Yes/No
```

### STEP 1 — Evidence Extraction (Mandatory)
1) 截图解析：OCR/多模态提取关键报错、时间、模块、IP/Endpoint。  
2) 日志包解压：识别子目录与模块日志，提取 ERROR/Exception/Failed/Timeout 的上下文（最后 300 行），统计重复次数。  
3) 归类错误类型：网络/权限/云平台 API/内部异常。

输出：
```
[Log Analysis Result]
Module:
Error Type:
First Occurrence Time:
Repetition Count:
Network Related: Yes/No
Permission Related: Yes/No
Cloud API Related: Yes/No
Internal Exception: Yes/No

Core Log Excerpt:
(log excerpt)
```

### STEP 2 — Stage Consistency Validation
校验模块是否与阶段一致；发现跨阶段异常（如同步阶段却出现安装模块日志）。

输出：
```
[Stage Consistency]
Consistent: Yes/No
Reason:
```

### STEP 3 — Jira Retrieval (Mandatory)
基于关键词/模块/阶段/版本检索 Jira，返回 Top 5 相似问题与修复信息。
优先使用 Jira MCP；若不可用，改用 Jira REST API（参见 `references/jira-rest.md`）。
若无法访问 Jira，明确说明原因并请求用户提供 Jira 导出或关键字段。

Jira REST 自动检索脚本（推荐）：
```
JIRA_BASE_URL=http://192.168.10.254:9005 \
JIRA_USER=your_user \
JIRA_PASS=your_pass \
JIRA_PROJECT_KEYS=REQ,PRJ \
python3 scripts/jira_search.py \
  --query "<自然语言问题关键词>" \
  --stage "<阶段>" \
  --module "<模块>" \
  --version "<版本>" \
  --max 5 \
  --print-jql
```

脚本输出 JSON（供诊断分析解析）：
```
{
  "jql": "...",
  "count": 5,
  "issues": [
    {
      "key": "HB-1234",
      "summary": "...",
      "similarity": 0.72,
      "bug": "Yes",
      "fix_version": "v3.2.1",
      "resolution": "Fixed",
      "solution_summary": "...",
      "status": "Done",
      "updated": "2025-01-01T08:00:00.000+0800"
    }
  ]
}
```

调试用法：
```
python3 scripts/jira_search.py --query "..." --print-jql
python3 scripts/jira_search.py --query "..." --dry-run
```

输出：
```
[Jira Match Result]
Issue List:
Key:
Similarity Score:
Bug: Yes/No
Fix Version:
Resolution Summary:

Existing Fix Version Available: Yes/No
```

### STEP 4 — Code Retrieval Trigger
仅在满足任一条件时触发：
- Internal Exception = Yes
- Jira 显示已确认 Bug
- 栈追踪包含类/方法
- 明确业务逻辑错误

以下场景禁止触发：
- 网络超时/连接拒绝
- 权限/鉴权失败
- 云平台限流
- 明显配置问题

输出：
```
[Code Analysis]
Triggered: Yes/No
Reason:
```

### STEP 5 — Code Retrieval & Localization (If Triggered)
定位仓库与分支（依据版本/模块），抽取文件路径、类、方法、上下游调用链（≤2 层）。
如无法访问内部代码仓库，说明原因并请求用户提供目标仓库/分支/文件路径或代码片段。

仓库定位脚本（可先确定仓库与分支候选）：
```
GIT_BASE_URL=http://192.168.10.254:20080 \
GIT_USER=your_user \
GIT_PASS=your_pass \
python3 scripts/repo_locate.py \
  --module "<模块>" \
  --product "HyperBDR|HyperMotion" \
  --version "<版本>" \
  --list-branches
```

代码定位脚本（拉取仓库 + 关键词定位 + 调用链候选）：
```
GIT_BASE_URL=http://192.168.10.254:20080 \
GIT_USER=your_user \
GIT_PASS=your_pass \
CODE_WORKDIR=/tmp/onepro-code \
python3 scripts/code_locate.py \
  --module "<模块>" \
  --product "HyperBDR|HyperMotion" \
  --version "<版本>" \
  --query "<错误关键词/报错片段>" \
  --class "<类名>" \
  --method "<方法名>" \
  --list-branches
```

诊断总入口脚本（Jira + 代码定位编排，输出统一 JSON）：
```
JIRA_BASE_URL=http://192.168.10.254:9005 \
JIRA_USER=your_user \
JIRA_PASS=your_pass \
JIRA_PROJECT_KEYS=REQ,PRJ \
GIT_BASE_URL=http://192.168.10.254:20080 \
GIT_USER=your_user \
GIT_PASS=your_pass \
CODE_WORKDIR=/tmp/onepro-code \
python3 scripts/diagnose_pipeline.py \
  --query "<自然语言问题>" \
  --product "HyperBDR|HyperMotion" \
  --stage "<阶段>" \
  --module "<模块>" \
  --version "<版本>" \
  --class "<类名>" \
  --method "<方法名>" \
  --log-archive "<日志包路径.zip|tar.gz>" \
  --log-path "<日志目录>" \
  --screenshot "<截图路径.png|jpg>" \
  --output-md \
  --output-file "/path/to/report.md"
```

OCR 依赖安装（仅当需要截图识别）：
```
bash scripts/install_ocr_deps.sh
```

脚本输出 JSON（用于代码定位结构化分析）：
```
{
  "module": "newmuse",
  "repo_path": "hypermotion/newmuse",
  "repo_url": "http://192.168.10.254:20080/hypermotion/newmuse.git",
  "branch_candidates": ["HyperMotion_release_vx.x.x", "master", "main"],
  "selected_branch": "HyperMotion_release_vx.x.x",
  "clone_path": "/tmp/onepro-code/hypermotion_newmuse",
  "search_terms": ["timeout", "Session", "open"],
  "hits": [
    {"file": "src/xxx.py", "line": 123, "text": "..."}
  ],
  "call_chain_candidates": [
    {"file": "src/yyy.py", "line": 45, "text": "..."}
  ]
}
```

输出：
```
[Code Localization]
Repository:
Branch:
File Path:
Class:
Method:
Call Chain:
Exception Trigger Condition:
```

### STEP 6 — Code Context Analysis
评估：空值处理、边界条件、外部依赖失败处理、重试逻辑、是否存在已修复提交。

输出：
```
[Code Analysis Conclusion]
Root Cause:
Logic Defect: Yes/No
Boundary Not Handled: Yes/No
External Dependency Failure: Yes/No
Fix Commit Exists: Yes/No
```

### STEP 7 — Root Cause Probability Model (Mandatory)
四类概率之和=100%：
环境问题 / 配置问题 / 云平台问题 / 代码缺陷。

输出：
```
[Root Cause Probability]
Environment Issue: %
Configuration Issue: %
Cloud Platform Issue: %
Code Defect: %

Primary Root Cause:
Confidence Level:
```

### STEP 8 — Solution Generation
给出：
- 临时缓解方案（可执行步骤）
- 永久解决方案（可执行步骤）
- 升级建议（版本 + 原因）

### STEP 9 — R&D Escalation Decision
判断是否需要升级研发，给出优先级与建议摘要。

输出：
```
[R&D Escalation]
Required: Yes/No
Priority: P1 / P2 / P3
Reason:
Suggested Escalation Content Summary:
```

## Final Output Format (Mandatory)
```
Hyper Diagnostic Report (Standardized)
Time:
Ticket/Scenario:

1️⃣ Basic Information
Product:
Stage:
Version:
Module:

2️⃣ Core Error Summary
Error Type:
Key Errors:
- 
- 
First Occurrence Time:
Repetition Count:

3️⃣ Evidence Chain
Screenshot Findings:
- 
Log Findings:
- Network Related:
- Permission Related:
- Cloud API Related:
- Internal Exception:

4️⃣ Stage Consistency
Consistent: Yes/No
Reason:

5️⃣ Jira Historical Match (Top 5)
Issue List:
- Key:
  Similarity Score:
  Bug:
  Fix Version:
  Status:
  Resolution Summary:
Existing Fix Version Available: Yes/No/Unknown

6️⃣ Code Localization (if triggered)
Triggered: Yes/No
Reason:
Repository:
Branch:
File Path:
Class:
Method:
Call Chain:

7️⃣ Root Cause Probability Table (Total = 100%)
Environment Issue:
Configuration Issue:
Cloud Platform Issue:
Code Defect:
Primary Root Cause:
Confidence Level:

8️⃣ Mitigation Plan
Temporary:
- 
Permanent:
- 
Upgrade Suggestion:
- 

9️⃣ R&D Escalation Decision
Required: Yes/No
Priority: P1 / P2 / P3
Reason:
Suggested Escalation Content Summary:
```

## Standard Markdown Output (Mandatory)
使用以下 Markdown 模板输出最终报告，保持字段与顺序一致：

```
# Hyper Diagnostic Report

## 1. Basic Information
- Product: <HyperBDR|HyperMotion>
- Stage: <stage>
- Version: <version>
- Module: <module>

## 2. Core Error Summary
- Error Type: <type>
- Key Errors:
  - <error 1>
  - <error 2>
- First Occurrence Time: <time>
- Repetition Count: <count>

## 3. Evidence Chain
### Screenshot Findings
- <finding 1>
- <finding 2>

### Log Findings
- Network Related: <Yes/No>
- Permission Related: <Yes/No>
- Cloud API Related: <Yes/No>
- Internal Exception: <Yes/No>

## 4. Stage Consistency
- Consistent: <Yes/No>
- Reason: <reason>

## 5. Jira Historical Match (Top 5)
| Key | Similarity | Bug | Fix Version | Status | Resolution | Solution Summary |
| --- | --- | --- | --- | --- | --- | --- |
| REQ-123 | 0.72 | Yes | v3.2.1 | Done | Fixed | <summary> |

## 6. Code Localization (if triggered)
- Triggered: <Yes/No>
- Reason: <reason>
- Repository: <repo>
- Branch: <branch>
- File Path: <path>
- Class: <class>
- Method: <method>
- Call Chain: <caller -> callee>

## 7. Root Cause Probability Table (Total = 100%)
| Category | Probability |
| --- | --- |
| Environment Issue | 30% |
| Configuration Issue | 20% |
| Cloud Platform Issue | 10% |
| Code Defect | 40% |

**Primary Root Cause:** <text>
**Confidence Level:** <text>

## 8. Mitigation Plan
### Temporary
1. <step>
2. <step>

### Permanent
1. <step>
2. <step>

### Upgrade Suggestion
- <version + reason>

## 9. R&D Escalation Decision
- Required: <Yes/No>
- Priority: <P1|P2|P3>
- Reason: <reason>
- Suggested Escalation Content Summary: <summary>
```

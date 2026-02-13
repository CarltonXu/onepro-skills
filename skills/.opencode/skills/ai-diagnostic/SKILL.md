---
name: onepro-ai-diagnostic
description: AI-driven fault triage for OnePro HyperBDR/HyperMotion delivery issues. Use when users submit logs (zip/tar.gz), screenshots, or text descriptions and need stage identification, error classification, Jira search, optional bounded code localization, and a structured diagnostic report with mitigation and escalation decisions.
---

# OnePro AI 故障诊断

## Overview
对 HyperBDR / HyperMotion 交付问题进行闭环诊断：解析截图与日志包、识别阶段与模块、检索 Jira 历史、在满足触发条件时做有限代码定位，输出结构化报告与解决方案。

## When to Use
- 用户提交日志包（zip/tar.gz）需要分析
- 用户上传截图显示报错信息
- 用户描述故障现象需要诊断
- 需要检索 Jira 历史记录匹配相似问题
- 需要代码级定位分析（仅限内部异常场景）

## References (Load When Needed)
- `references/onepro-troubleshooting.md`：阶段划分、模块→日志路径映射、日志分析要点与归因示例。用于 STEP 0/1/2 的阶段识别与模块定位。
- `references/jira-rest.md`：Jira Data Center REST 检索指引（Basic 认证、JQL 模板、字段映射）。用于 STEP 3。
- `references/repo-map.md`：模块→仓库映射、分支规则、认证方式。用于 STEP 5。

## Global Rules (Mandatory)
1. 严格按步骤顺序执行，不允许跳步
2. 每一步输出结构化中间结果
3. 所有判断给出概率/置信度；根因概率总和必须等于 100%
4. 结论必须有证据链：日志 + Jira +（如触发）代码分析
5. 不在明显环境问题时触发代码分析或拉取代码
6. 代码分析范围限制：单文件 + 上下游调用深度 ≤ 2 层

## Workflow

### STEP 0 — Input Parsing
识别产品、阶段、版本、关键词、截图与日志包类型。

**输出格式：**
```
[Input Analysis]
Product: <HyperBDR|HyperMotion|Unknown>
Stage: <安装/注册/初始同步/增量同步/演练/接管>
Version: <版本号>
Detected Module: <模块名>
Keywords: <提取的关键词>
Attachment Types: <screenshot/log zip/tar.gz/text/none>
Stack Trace Present: <Yes/No/Unknown>
```

### STEP 1 — Evidence Extraction (Mandatory)
1) 截图解析：OCR/多模态提取关键报错、时间、模块、IP/Endpoint
2) 日志包解压：识别子目录与模块日志，提取 ERROR/Exception/Failed/Timeout 的上下文（最后 300 行），统计重复次数
3) 归类错误类型：网络/权限/云平台 API/内部异常

**输出格式：**
```
[Log Analysis Result]
Module: <模块名>
Error Type: <Network/Permission/CloudAPI/InternalException/Unknown>
First Occurrence Time: <时间戳>
Repetition Count: <数字>
Network Related: <Yes/No>
Permission Related: <Yes/No>
Cloud API Related: <Yes/No>
Internal Exception: <Yes/No>
Stack Trace Present: <Yes/No>

Core Log Excerpt:
<日志片段，最多300行>
```

### STEP 2 — Stage Consistency Validation
校验模块是否与阶段一致；发现跨阶段异常（如同步阶段却出现安装模块日志）。

**输出格式：**
```
[Stage Consistency]
Consistent: <Yes/No/Unknown>
Reason: <说明>
```

### STEP 3 — Jira Retrieval (Mandatory)
基于关键词/模块/阶段/版本检索 Jira，返回 Top 5 相似问题与修复信息。

**触发条件：** 始终执行

**工具调用：** `scripts/jira_search.py`

```bash
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

**输出格式：**
```
[Jira Match Result]
Issue List:
- Key: <JIRA-123>
  Similarity Score: <0.00-1.00>
  Bug: <Yes/No>
  Fix Version: <版本号>
  Resolution Summary: <解决摘要>
  Status: <状态>

Existing Fix Version Available: <Yes/No/Unknown>
```

**注意事项：**
- 优先使用 Jira MCP；若不可用，改用 Jira REST API（参见 `references/jira-rest.md`）
- 若无法访问 Jira，明确说明原因并请求用户提供 Jira 导出或关键字段

### STEP 4 — Code Retrieval Trigger
仅在满足任一条件时触发：
- Internal Exception = Yes
- Jira 显示已确认 Bug
- 栈追踪包含类/方法
- 明确业务逻辑错误

**禁止触发场景：**
- 网络超时/连接拒绝
- 权限/鉴权失败
- 云平台限流
- 明显配置问题

**输出格式：**
```
[Code Analysis Trigger]
Triggered: <Yes/No>
Reason: <触发原因说明>
```

### STEP 5 — Code Retrieval & Localization (If Triggered)
定位仓库与分支（依据版本/模块），抽取文件路径、类、方法、上下游调用链（≤2 层）。

**工具调用：** `scripts/code_locate.py`

```bash
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

**输出格式：**
```
[Code Localization]
Repository: <仓库URL>
Branch: <分支名>
File Path: <文件路径>
Class: <类名>
Method: <方法名>
Call Chain: <调用链描述>
Exception Trigger Condition: <触发条件>
```

**注意事项：**
- 如无法访问内部代码仓库，说明原因并请求用户提供目标仓库/分支/文件路径或代码片段
- 仅分析单文件 + 上下游调用深度 ≤ 2 层

### STEP 6 — Code Context Analysis
评估：空值处理、边界条件、外部依赖失败处理、重试逻辑、是否存在已修复提交。

**输出格式：**
```
[Code Analysis Conclusion]
Root Cause: <根因描述>
Logic Defect: <Yes/No>
Boundary Not Handled: <Yes/No>
External Dependency Failure: <Yes/No>
Fix Commit Exists: <Yes/No>
```

### STEP 7 — Root Cause Probability Model (Mandatory)
四类概率之和=100%：
- 环境问题
- 配置问题
- 云平台问题
- 代码缺陷

**输出格式：**
```
[Root Cause Probability]
Environment Issue: <%>
Configuration Issue: <%>
Cloud Platform Issue: <%>
Code Defect: <%>

Primary Root Cause: <主要根因>
Confidence Level: <High/Medium/Low>
```

### STEP 8 — Solution Generation
给出：
- 临时缓解方案（可执行步骤）
- 永久解决方案（可执行步骤）
- 升级建议（版本 + 原因）

**输出格式：**
```
[Mitigation Plan]
Temporary:
1. <步骤1>
2. <步骤2>

Permanent:
1. <步骤1>
2. <步骤2>

Upgrade Suggestion:
- <版本 + 原因>
```

### STEP 9 — R&D Escalation Decision
判断是否需要升级研发，给出优先级与建议摘要。

**输出格式：**
```
[R&D Escalation]
Required: <Yes/No>
Priority: <P1/P2/P3>
Reason: <原因>
Suggested Escalation Content Summary: <摘要>
```

## Scripts Reference

### Jira 搜索脚本
**文件：** `scripts/jira_search.py`
**用途：** 根据关键词搜索 Jira 问题
**依赖：** 仅需 Python 3 标准库

```bash
python3 scripts/jira_search.py \
  --base-url "http://192.168.10.254:9005" \
  --query "timeout error" \
  --stage "同步" \
  --module "newmuse" \
  --version "3.2.0" \
  --max 5
```

**环境变量：**
- `JIRA_BASE_URL`: Jira 服务器地址
- `JIRA_USER`: 用户名
- `JIRA_PASS`: 密码
- `JIRA_PROJECT_KEYS`: 项目代码（默认 REQ,PRJ）

### 代码定位脚本
**文件：** `scripts/code_locate.py`
**用途：** 克隆仓库并在代码中搜索关键词
**依赖：** Python 3, git, ripgrep (rg)

```bash
python3 scripts/code_locate.py \
  --module "newmuse" \
  --product "HyperMotion" \
  --version "3.2.0" \
  --query "timeout" \
  --class "SessionManager" \
  --method "open"
```

**环境变量：**
- `GIT_BASE_URL`: Git 服务器地址（默认 http://192.168.10.254:20080）
- `GIT_USER`: 用户名
- `GIT_PASS`: 密码
- `CODE_WORKDIR`: 代码克隆目录（默认 /tmp/onepro-code）

### 仓库定位脚本
**文件：** `scripts/repo_locate.py`
**用途：** 根据模块名定位仓库和分支

```bash
python3 scripts/repo_locate.py \
  --module "newmuse" \
  --product "HyperMotion" \
  --version "3.2.0" \
  --list-branches
```

### 诊断流程脚本
**文件：** `scripts/diagnose_pipeline.py`
**用途：** 完整的诊断流程编排（Jira + 代码定位）
**依赖：** Python 3, 其他脚本

```bash
python3 scripts/diagnose_pipeline.py \
  --query "同步超时" \
  --product "HyperMotion" \
  --stage "增量同步" \
  --module "newmuse" \
  --version "3.2.0" \
  --log-archive "/path/to/logs.zip" \
  --output-md \
  --output-file "/path/to/report.md"
```

**参数：**
- `--query`: 问题描述（必需）
- `--product`: 产品名称
- `--stage`: 交付阶段
- `--module`: 模块名称
- `--version`: 版本号
- `--class`: 类名（可选）
- `--method`: 方法名（可选）
- `--log-archive`: 日志包路径
- `--log-path`: 日志目录路径
- `--screenshot`: 截图路径
- `--output-md`: 输出 Markdown 格式
- `--output-file`: 输出文件路径
- `--skip-code`: 跳过代码分析

## Installation

### 安装 OCR 依赖（如需截图识别）
```bash
bash scripts/install_ocr_deps.sh
```

或手动安装：
```bash
pip install pillow pytesseract
# 同时需要安装 tesseract-ocr 系统包
# macOS: brew install tesseract
# Ubuntu: apt-get install tesseract-ocr
```

### 安装 ripgrep（代码搜索必需）
```bash
# macOS
brew install ripgrep

# Ubuntu/Debian
apt-get install ripgrep

# 或其他系统参见 https://github.com/BurntSushi/ripgrep#installation
```

## Final Output Format (Mandatory)

### Markdown 报告格式

```markdown
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

## Troubleshooting

### 常见问题 1：Jira 连接失败
**问题：** 脚本返回 `Jira HTTPError 401` 或连接超时  
**解决：** 
1. 检查环境变量 `JIRA_BASE_URL`, `JIRA_USER`, `JIRA_PASS` 是否正确设置
2. 确认网络可以访问 Jira 服务器
3. 尝试手动 curl 测试连接

### 常见问题 2：Git 克隆失败
**问题：** 脚本返回 `clone_failed` 错误  
**解决：**
1. 检查环境变量 `GIT_BASE_URL`, `GIT_USER`, `GIT_PASS`
2. 确认仓库路径在 `references/repo-map.md` 中有映射
3. 检查网络连接和权限

### 常见问题 3：代码搜索无结果
**问题：** `code_locate.py` 返回空 hits  
**解决：**
1. 确认已安装 ripgrep (`rg` 命令可用)
2. 检查关键词是否正确提取
3. 尝试使用 `--list-branches` 查看可用分支

### 常见问题 4：OCR 识别失败
**问题：** 截图无法提取文字  
**解决：**
1. 确认已安装 tesseract-ocr 系统包
2. 检查图片格式是否支持（PNG, JPG）
3. 尝试手动运行 OCR 测试

## Examples

### 示例 1：完整诊断流程
```
用户：HyperMotion 3.2.0 增量同步阶段 newmuse 模块报错 timeout，日志见附件

诊断流程：
1. 解析日志包，提取 timeout 相关错误
2. 调用 jira_search.py 搜索相似问题
3. 检查触发代码分析条件（Internal Exception = No，不触发）
4. 输出诊断报告
```

### 示例 2：带代码定位的诊断
```
用户：HyperBDR 3.1.5 同步失败，日志显示 NullPointerException in SessionManager.open()

诊断流程：
1. 解析日志，发现 Internal Exception = Yes
2. 调用 jira_search.py 搜索
3. 触发代码分析，调用 code_locate.py
4. 定位到 SessionManager.java:156
5. 分析代码发现空指针未处理
6. 输出完整报告
```

## Limitations
- 代码分析仅限于已配置的模块（见 `references/repo-map.md`）
- Jira 查询需要内网访问权限
- 代码仓库访问需要 VPN 或内网环境
- OCR 识别准确度依赖图片质量
- 自动代码分析深度限制为 2 层调用链

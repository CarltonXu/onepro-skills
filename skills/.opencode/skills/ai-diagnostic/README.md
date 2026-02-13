# OnePro AI 故障诊断 - OpenCode Skill

这是一个专为 OpenCode 设计的 AI 故障诊断技能，用于 HyperBDR/HyperMotion 交付问题的闭环诊断。

## 目录结构

```
onepro-ai-diagnostic/
├── SKILL.md                          # 技能定义主文件（必需）
├── agents/
│   └── openai.yaml                   # 代理配置
├── references/
│   ├── jira-rest.md                  # Jira REST API 参考
│   ├── onepro-troubleshooting.md     # 故障处理指南
│   └── repo-map.md                   # 代码仓库映射
└── scripts/
    ├── jira_search.py                # Jira 搜索脚本
    ├── repo_locate.py                # 仓库定位脚本
    ├── code_locate.py                # 代码定位脚本
    ├── diagnose_pipeline.py          # 完整诊断流程
    ├── install_ocr_deps.sh           # OCR 依赖安装
    └── requirements.txt              # Python 依赖
```

## 快速开始

### 1. 安装依赖

```bash
# 安装 OCR 依赖（如需截图识别）
bash skills/onepro-ai-diagnostic/scripts/install_ocr_deps.sh

# 或手动安装
pip install pillow pytesseract

# 安装 ripgrep（代码搜索必需）
# macOS:
brew install ripgrep

# Ubuntu/Debian:
apt-get install ripgrep
```

### 2. 配置环境变量

```bash
# Jira 配置
export JIRA_BASE_URL="http://192.168.10.254:9005"
export JIRA_USER="your_username"
export JIRA_PASS="your_password"
export JIRA_PROJECT_KEYS="REQ,PRJ"

# Git 配置
export GIT_BASE_URL="http://192.168.10.254:20080"
export GIT_USER="your_username"
export GIT_PASS="your_password"
export CODE_WORKDIR="/tmp/onepro-code"
```

### 3. 使用 Skill

在 OpenCode 中，直接描述你的问题：

```
HyperMotion 3.2.0 增量同步阶段 newmuse 模块报错 timeout
```

或提供日志包：

```
请诊断附件中的日志问题
[上传 logs.zip]
```

## 工作流程

技能按以下 10 个步骤执行：

1. **输入解析** - 识别产品、阶段、版本、模块
2. **证据提取** - 解析日志/截图，提取错误信息
3. **阶段一致性验证** - 校验模块与阶段是否匹配
4. **Jira 检索** - 搜索历史相似问题
5. **代码检索触发判断** - 决定是否进行代码分析
6. **代码定位** - 克隆仓库并定位代码
7. **代码上下文分析** - 分析代码逻辑缺陷
8. **根因概率模型** - 计算四类根因概率
9. **解决方案生成** - 提供临时/永久解决方案
10. **研发升级决策** - 判断是否需要升级研发

## 核心脚本使用

### Jira 搜索
```bash
python3 scripts/jira_search.py \
  --query "timeout error" \
  --stage "同步" \
  --module "newmuse" \
  --version "3.2.0"
```

### 代码定位
```bash
python3 scripts/code_locate.py \
  --module "newmuse" \
  --product "HyperMotion" \
  --version "3.2.0" \
  --query "timeout" \
  --class "SessionManager" \
  --method "open"
```

### 完整诊断流程
```bash
python3 scripts/diagnose_pipeline.py \
  --query "同步超时" \
  --product "HyperMotion" \
  --stage "增量同步" \
  --module "newmuse" \
  --version "3.2.0" \
  --log-archive "/path/to/logs.zip" \
  --output-md
```

## 输出格式

诊断报告包含 9 个部分：

1. 基本信息（产品/阶段/版本/模块）
2. 核心错误摘要（错误类型/关键错误/时间/次数）
3. 证据链（截图发现/日志发现）
4. 阶段一致性
5. Jira 历史匹配（Top 5）
6. 代码定位（如触发）
7. 根因概率表（四类总和=100%）
8. 缓解方案（临时/永久/升级建议）
9. 研发升级决策

## 注意事项

1. **代码分析限制**：仅在出现内部异常、已确认 Bug、栈追踪或业务逻辑错误时触发
2. **网络/权限问题**：明显环境问题时不会触发代码分析
3. **分析深度限制**：单文件 + 上下游调用深度 ≤ 2 层
4. **根因概率**：四类概率之和必须等于 100%

## 支持的模块

查看 `references/repo-map.md` 获取完整的模块映射列表，包括：
- newmuse, owl, crab, ant, porter
- mistral, atomy-unicloud, unicloud
- atomy-obstor, storplus, oneway
- proxy, minitgt, s3block, hamal
- Windows Agent, Linux Agent

## 故障排除

### Jira 连接失败
- 检查环境变量是否正确设置
- 确认网络可以访问 Jira 服务器
- 验证用户名密码

### Git 克隆失败
- 检查环境变量
- 确认仓库路径在 repo-map.md 中有映射
- 检查 VPN/网络连接

### 代码搜索无结果
- 确认已安装 ripgrep
- 检查关键词提取
- 使用 `--list-branches` 查看分支

## License

内部使用

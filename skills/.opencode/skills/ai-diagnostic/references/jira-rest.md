# Jira REST（Data Center）检索指引

适用环境：Jira Data Center（内网），使用 Basic 认证。
Base URL：`http://192.168.10.254:9005`

## 1) 认证方式（Basic）
- 使用 `username:password` 做 Base64 编码。
- 请求头：`Authorization: Basic <base64>`

示例：
```
user="your_user"
pass="your_pass"
cred=$(printf "%s:%s" "$user" "$pass" | base64)
```

## 2) 搜索接口
- Endpoint: `POST /rest/api/2/search`
- 必填：`jql`，可选：`fields`、`maxResults`

推荐字段（用于诊断对比）：
- `key`
- `summary`
- `description`
- `resolution`
- `fixVersions`
- `status`
- `priority`
- `components`
- `labels`
- `updated`
- `comment`

## 3) JQL 模板（按关键词/阶段/模块）
```
project in (HB, HM) AND (summary ~ "<keyword>" OR description ~ "<keyword>" OR text ~ "<keyword>")
ORDER BY updated DESC
```

当有阶段/模块时可追加：
```
AND (summary ~ "<stage>" OR description ~ "<stage>")
AND (summary ~ "<module>" OR description ~ "<module>")
```

## 4) cURL 示例
```
BASE="http://192.168.10.254:9005"
JQL='project in (HB, HM) AND (summary ~ "timeout" OR description ~ "timeout" OR text ~ "timeout") ORDER BY updated DESC'

curl -s -X POST "$BASE/rest/api/2/search" \
  -H "Authorization: Basic $cred" \
  -H "Content-Type: application/json" \
  -d '{
    "jql": "'"$JQL"'",
    "maxResults": 5,
    "fields": [
      "summary","description","resolution","fixVersions","status",
      "priority","components","labels","updated","comment"
    ]
  }'
```

## 5) 结果提取要点
- **Solution/Resolution**：优先取 `resolution` + 最近一次有效 comment。
- **Fix Version**：`fixVersions` 里最新版本。
- **Bug 标记**：`issuetype` 或标签中含 `bug`。
- **相似度**：关键词覆盖度（summary/description/comment）。

## 6) 输出映射建议
将 Top 5 结果映射为：
- Key
- Similarity Score（0-1）
- Bug: Yes/No
- Fix Version
- Resolution Summary（优先 comment 最后一次处理结论）

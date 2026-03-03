# Apache Answer API bootstrap (ApiKeyAuth)

You will configure the sync script using the Answer OpenAPI doc.

## 1) Inspect OpenAPI

Run:

```bash
python3 scripts/inspect_openapi.py --swagger-url https://qa.oneprocloud.com/swagger/doc.json
```

From the output, capture:
- Base URL and any API prefix (`/api/...`)
- Security scheme name + header name (ApiKeyAuth)
- Paths/methods for:
  - Create question
  - Create answer (or comment) for a question
  - (Optional) Search questions
  - (Optional) Update question/answer

## 2) Configure env vars

This skill keeps the HTTP logic generic and uses env vars to map to your Answer deployment.

Common env vars:
- `ANSWER_BASE_URL`: e.g. `https://qa.oneprocloud.com`
- `ANSWER_API_KEY`: ApiKeyAuth value
- `ANSWER_API_KEY_HEADER`: header name; default `Authorization`
- `ANSWER_API_KEY_PREFIX`: header value prefix (optional; default empty = send raw key)

Endpoint mapping (set based on swagger):
- `ANSWER_CREATE_QA_PATH`: preferred, one-call create question+answer (Swagger: `/answer/api/v1/question/answer`)
- `ANSWER_CREATE_QUESTION_PATH`: create question only (Swagger: `/answer/api/v1/question`)
- `ANSWER_CREATE_ANSWER_PATH`: create answer only (Swagger: `/answer/api/v1/answer`)
- `ANSWER_SEARCH_PATH`: optional, used for server-side dedupe when state is missing (Swagger: `/answer/api/v1/search`)

## 3) Suggested local `.env` (do not commit)

EN:

```bash
export ANSWER_SITE_NAME="qa-en"
export ANSWER_BASE_URL="https://qa.oneprocloud.com"
export ANSWER_API_KEY="***"
export ANSWER_API_KEY_HEADER="Authorization"
export ANSWER_API_KEY_PREFIX=""
export ANSWER_CREATE_QA_PATH="/answer/api/v1/question/answer"
export ANSWER_CREATE_QUESTION_PATH="/answer/api/v1/question"
export ANSWER_CREATE_ANSWER_PATH="/answer/api/v1/answer"
export ANSWER_SEARCH_PATH="/answer/api/v1/search"
```

ZH:

```bash
export ANSWER_SITE_NAME="wenti-zh"
export ANSWER_BASE_URL="https://wenti.oneprocloud.com"
export ANSWER_API_KEY="***"
export ANSWER_API_KEY_HEADER="Authorization"
export ANSWER_API_KEY_PREFIX=""
export ANSWER_CREATE_QA_PATH="/answer/api/v1/question/answer"
export ANSWER_CREATE_QUESTION_PATH="/answer/api/v1/question"
export ANSWER_CREATE_ANSWER_PATH="/answer/api/v1/answer"
export ANSWER_SEARCH_PATH="/answer/api/v1/search"
```

If your Answer instance uses different paths, adjust them based on swagger output.

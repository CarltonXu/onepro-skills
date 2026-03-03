---
name: onepro-docs-qa-sync
description: Generate categorized Q&A from docs.oneprocloud.com (crawl or ingest exported docs), produce standard Markdown/JSON Q&A packs (English + Chinese), and sync/publish them to Apache Answer instances (qa.oneprocloud.com and wenti.oneprocloud.com) via ApiKeyAuth while preventing duplicates using stable source IDs, content hashes, and a local sync state file.
---

# OnePro Docs Q&A Sync

## Workflow (recommended)

Use this skill to turn OnePro docs into a maintainable Q&A knowledge base, with:
- A repeatable crawl/ingest step for docs content
- A standard “Q&A Pack” format (JSON) + Markdown archives (EN/ZH)
- A safe sync step to Apache Answer (dry-run by default) with dedupe

### Step 0: Prepare access (once)

- Prepare 2 API keys (ApiKeyAuth):
  - `qa.oneprocloud.com` (English Apache Answer)
  - `wenti.oneprocloud.com` (Chinese Apache Answer)
- Keep API keys out of git history (use env vars or a local `.env` file that you do not commit).

### Step 1: Crawl or ingest docs content

Option A (crawl from sitemap):
- Run `scripts/crawl_docs_sitemap.py` to fetch pages listed in `sitemap.xml` (or any sitemap URL you provide).
- Output is a local “docs snapshot” folder with a `manifest.json` so runs are deterministic.

Option B (ingest exports):
- If you already exported docs to local Markdown/HTML, put them into a folder and create your own `manifest.json` in the same shape as produced by the crawler (see `references/qa_pack_format.md` and the crawler’s `manifest.json`).

### Step 2: Generate Q&A packs (EN + ZH)

Use the docs snapshot as the only source of truth and generate two Q&A pack files:
- English pack: `outputs/qa_pack_en.json`
- Chinese pack: `outputs/qa_pack_zh.json`

Rules to follow while generating:
- Every item must have a stable `source_id` derived from docs URL/path + section heading (or your own stable key). Do not change `source_id` once published.
- Include `source_urls` for traceability.
- Provide `category` and `tags` for navigation.
- Write `question_md` and `answer_md` in Markdown (no HTML unless required).

After you create the JSON packs, generate Markdown archives:
- `scripts/render_qa_markdown.py --in outputs/qa_pack_en.json --out outputs/qa_en.md`
- `scripts/render_qa_markdown.py --in outputs/qa_pack_zh.json --out outputs/qa_zh.md`

Optional validation/fill hashes:
- `python3 scripts/validate_qa_pack.py --in outputs/qa_pack_en.json --out outputs/qa_pack_en.json`
- `python3 scripts/validate_qa_pack.py --in outputs/qa_pack_zh.json --out outputs/qa_pack_zh.json`

### Step 3: Sync to Apache Answer (qa/wenti) without duplicates

This skill prevents duplicates using:
- A local `state.json` mapping `source_id -> remote ids + content_hash`
- A hidden marker appended to the post body (so humans don’t see it, but you can search for it if your Answer instance supports full-text search)

Recommended sync flow:
1) Inspect the Answer OpenAPI doc (Swagger) to confirm endpoints and auth header:
   - `scripts/inspect_openapi.py --swagger-url https://qa.oneprocloud.com/swagger/doc.json`
2) Configure environment variables for each site (EN and ZH).
3) Run sync in dry-run mode first.
4) Re-run with `--apply` only after confirming it will not create duplicates.

See `references/apache_answer_api_bootstrap.md` for the exact env vars and a suggested `.env` layout.

## Commands (typical)

1) Crawl docs:
- `python3 scripts/crawl_docs_sitemap.py --sitemap https://docs.oneprocloud.com/sitemap.xml --out outputs/docs_snapshot`
- If sitemap `<loc>` uses a wrong host, add rewrite flags:
  - `python3 scripts/crawl_docs_sitemap.py --sitemap https://docs.oneprocloud.com/sitemap.xml --out outputs/docs_snapshot --rewrite-host-from vuepress-theme-hope-docs-demo.netlify.app --rewrite-host-to docs.oneprocloud.com --rewrite-scheme-to https`
- If docs have both EN(no `/zh`) and ZH(`/zh`), crawl both variants:
  - `python3 scripts/crawl_docs_sitemap.py --sitemap https://docs.oneprocloud.com/sitemap.xml --out outputs/docs_snapshot --lang both --lang-prefix zh`
  - Note: some EN↔ZH mapped pages may not exist and return 404; the crawler will skip 404s and record them in `manifest.json` (`fetch_errors`).

2) Validate OpenAPI and discover endpoints:
- `python3 scripts/inspect_openapi.py --swagger-url https://qa.oneprocloud.com/swagger/doc.json`

2.5) Extract docs content (per page/section) for the LLM step:
- `python3 scripts/extract_docs_snapshot.py --snapshot outputs/docs_snapshot --out outputs/docs_extracted.json`

2.6) Generate real user-intent Q&A packs (LLM step):
- Read `references/llm_generate_qa_pack.md`
- Output: `outputs/qa_pack_en.json` and `outputs/qa_pack_zh.json`

2.6 (offline fallback) Generate Q&A packs without external LLM:
- `python3 scripts/generate_qa_pack_from_extracted.py --in outputs/docs_extracted.json --out-en outputs/qa_pack_en.json --out-zh outputs/qa_pack_zh.json`

3) Render Markdown archive:
- `python3 scripts/render_qa_markdown.py --in outputs/qa_pack_en.json --out outputs/qa_en.md`
- `python3 scripts/render_qa_markdown.py --in outputs/qa_pack_zh.json --out outputs/qa_zh.md`

4) Sync EN site (dry-run, then apply):
- `python3 scripts/sync_answer.py --in outputs/qa_pack_en.json --state outputs/state_qa_en.json --site en`
- `python3 scripts/sync_answer.py --in outputs/qa_pack_en.json --state outputs/state_qa_en.json --site en --apply`

5) Sync ZH site (dry-run, then apply):
- `python3 scripts/sync_answer.py --in outputs/qa_pack_zh.json --state outputs/state_wenti_zh.json --site zh`
- `python3 scripts/sync_answer.py --in outputs/qa_pack_zh.json --state outputs/state_wenti_zh.json --site zh --apply`

Notes:
- Dry-run no longer modifies `--state` (to avoid blocking the real `--apply` run). Use `--write-state-on-dry-run` only if you intentionally want that behavior.

## Key files

- `scripts/crawl_docs_sitemap.py`: Crawl docs by sitemap and write a local snapshot + manifest
- `scripts/inspect_openapi.py`: Print Answer OpenAPI paths/security so you can configure endpoints safely
- `scripts/extract_docs_snapshot.py`: Extract per-page/per-section text from snapshot for Q&A generation
- `scripts/render_qa_markdown.py`: Convert Q&A pack JSON into a standard Markdown archive
- `scripts/generate_qa_pack_from_extracted.py`: Generate EN/ZH Q&A pack JSON from extracted docs (offline fallback)
- `scripts/validate_qa_pack.py`: Validate pack shape and fill `content_hash`
- `scripts/sync_answer.py`: Sync Q&A pack JSON to Apache Answer (dry-run by default) with dedupe
- `references/qa_pack_format.md`: Q&A pack JSON format requirements
- `references/qa_generation_guidelines.md`: How to generate stable, categorized Q&A
- `references/llm_generate_qa_pack.md`: Exact rules for generating Q&A from extracted docs
- `references/apache_answer_api_bootstrap.md`: How to map Swagger/OpenAPI to env vars for sync

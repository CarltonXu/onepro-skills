# LLM step: generate real Q&A from extracted docs (EN + ZH)

This step is where the model reads extracted docs content and produces **user-intent Q&A** (not “what is heading?” templates).

## Inputs

- Extracted docs JSON created by:
  - `python3 scripts/extract_docs_snapshot.py --snapshot outputs/docs_snapshot --out outputs/docs_extracted.json`
- Output packs (must match `references/qa_pack_format.md`):
  - `outputs/qa_pack_en.json`
  - `outputs/qa_pack_zh.json`

## Generation rules

For each `pages[]` entry:

1) Read `title`, `path_url`, `category`, `tags`, and `sections[]`.
2) For each `sections[]` (or for the page as a whole if sections are noisy), generate Q&A that a real user would ask, such as:
   - “How do I …?”
   - “What are the prerequisites/limits?”
   - “Why do I see error X / symptom Y?”
   - “How to verify it worked?”
   - “What logs/steps to collect for escalation?”
3) Avoid superficial questions that just restate headings unless the docs truly define a concept.

### Output count (stability)

To keep `source_id` stable and prevent duplicates across re-runs:

- Generate **exactly 3 Q&As per section** (if section is meaningful).
- If a page has too many sections, cap to the first 6 sections with the most useful content.

### Stable `source_id`

Use this deterministic pattern:

`docs:<path_url>#qa-<section_id>-<text_hash8>-<i>`

Where:
- `section_id` comes from extracted JSON (`pages[].sections[].section_id`)
- `text_hash8` is the first 8 chars of `pages[].sections[].text_hash` (disambiguates repeated headings)
- `i` is `1..3` for the 3 Q&As of that section

If you decide to generate page-level Q&A (no section), use:

`docs:<path_url>#qa-page-<i>`

### Language split

- If `pages[].lang == "zh"` → generate Chinese items into `qa_pack_zh.json`
- Else generate English items into `qa_pack_en.json`

## Required fields per item

Each Q&A item must include:

- `source_id`
- `title`
- `category` (use `pages[].category` unless you have a better stable taxonomy)
- `question_md`
- `answer_md`
- `tags` (start from `pages[].tags`, add 1–5 helpful keywords)
- `source_urls` (must include `pages[].url`)

## Quality checklist

- Answer has: meaning/context → steps → verification → troubleshooting/escalation.
- No confidential info; no API keys; no internal-only links unless intended.
- Keep Markdown simple (lists, code fences).

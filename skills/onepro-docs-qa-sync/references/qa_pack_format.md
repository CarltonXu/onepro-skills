# Q&A Pack format (JSON)

This skill standardizes generated Q&A so it can be re-synced safely without duplicates.

## File shape

Top-level object:

```json
{
  "version": 1,
  "generated_at": "2026-03-02T12:00:00+08:00",
  "lang": "en",
  "source": {
    "kind": "docs_snapshot",
    "snapshot_dir": "outputs/docs_snapshot",
    "notes": "optional"
  },
  "items": []
}
```

## `items[]` fields

Required:
- `source_id` (string): Stable unique ID (do not change once published).
- `title` (string)
- `category` (string)
- `question_md` (string, markdown)
- `answer_md` (string, markdown)
- `tags` (string[])
- `source_urls` (string[])

Optional:
- `content_hash` (string): If omitted, sync script computes it.
- `updated_at` (string): ISO8601.

Example item:

```json
{
  "source_id": "docs:/hyperbdr/backup/retention#how-retention-works",
  "title": "How does retention work in HyperBDR?",
  "category": "HyperBDR / Backup",
  "question_md": "I configured retention but ...",
  "answer_md": "Retention is applied ...",
  "tags": ["hyperbdr", "backup", "retention"],
  "source_urls": ["https://docs.oneprocloud.com/hyperbdr/backup/retention"]
}
```

## Dedupe rules

The sync script relies on:
- `source_id` as the stable primary key across runs
- `content_hash` as the change detector (title/question/answer/tags/category)
- A local `state.json` that maps `source_id -> remote question id`

If you change `source_id`, the script cannot know it is “the same” Q&A and will treat it as new.

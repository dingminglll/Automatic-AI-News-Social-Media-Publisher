# Scoring

Each fetched item is analyzed by the configured LLM and receives:

- `ai_score`: importance from 0 to 10
- `ai_reason`: why the item matters
- `ai_summary`: short digest used in summaries and post generation
- `ai_tags`: topical tags

The orchestrator sorts selected items by `ai_score` descending. Xiaohongshu
publishing defaults to `post_source: "top_scored_item"`, so the highest-scoring
story becomes the source material for the title, body, discussion hook, and
cover prompt.

Use `filtering.ai_score_threshold` to tune selectivity. A threshold around 6
keeps more material; 8 or higher keeps only the strongest stories.

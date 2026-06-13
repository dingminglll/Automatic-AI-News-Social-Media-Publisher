# Configuration

The app uses two local files:

- `.env` stores secrets and API keys.
- `data/config.json` stores source, model, scoring, output, and publishing settings.

Create them from the shareable templates:

```bash
cp .env.example .env
cp data/config.example.json data/config.json
```

## AI Provider

Set `ai.provider`, `ai.model`, and `ai.api_key_env` in `data/config.json`.
The environment variable named by `ai.api_key_env` must exist in `.env`.

Example:

```json
{
  "ai": {
    "provider": "openai",
    "model": "gpt-4o",
    "api_key_env": "OPENAI_API_KEY",
    "temperature": 0.3,
    "max_tokens": 4096
  }
}
```

OpenAI-compatible providers can use `base_url`.

## Sources

Enable only the collectors you need under `sources`. The default example keeps
Hacker News, RSS, Reddit, and selected GitHub sources enabled, while Twitter/X,
OpenBB, and OSS Insight are disabled until credentials or optional dependencies
are configured.

## Scoring

`filtering.ai_score_threshold` controls which analyzed items are kept for the
daily summary and Xiaohongshu post. Higher values produce fewer, stronger items.

`filtering.time_window_hours` controls the default lookback window.

## Xiaohongshu Publishing

For local browser publishing, use the bundled CDP pipeline:

```json
{
  "xiaohongshu": {
    "enabled": true,
    "publish_mode": "local_cdp",
    "languages": ["zh"],
    "post_source": "top_scored_item",
    "polish_with_ai": true,
    "title_max_chars": 28,
    "local_pipeline_env": "XIAOHONGSHU_PIPELINE",
    "preview": true,
    "image_generation": {
      "enabled": true,
      "provider": "openai",
      "api_key_env": "OPENAI_API_KEY",
      "model": "gpt-image-1",
      "size": "1024x1024"
    }
  }
}
```

Set this in `.env`:

```bash
XIAOHONGSHU_PIPELINE=./XiaohongshuSkills/scripts/publish_pipeline.py
```

Keep `preview` enabled until Chrome is logged in and the generated post looks
right. Set `preview` to `false`, or use `ainews-xhs-publish --publish`, only
when you want the automation to click publish.

If image generation is unavailable, set `image_generation.enabled` to `false`
and provide one local image path through `image_paths`.

## Runtime Files

The following files are intentionally ignored by git:

- `.env`
- `data/config.json`
- generated summaries under `data/summaries/`
- generated Xiaohongshu assets under `data/xiaohongshu/`
- local virtual environments, logs, and Python caches

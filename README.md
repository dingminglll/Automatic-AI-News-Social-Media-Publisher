<div align="center">

# AI News XHS Publisher

### From noisy AI feeds to a polished Xiaohongshu post, automatically.

[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://python.org)
[![Package Manager: uv](https://img.shields.io/badge/Package%20Manager-uv-2f6feb)](https://github.com/astral-sh/uv)
[![Tests: pytest](https://img.shields.io/badge/Tests-pytest-0a7)](tests)
[![Xiaohongshu](https://img.shields.io/badge/Publish-Xiaohongshu-ff2442)](XiaohongshuSkills)

<br>

<table>
<tr><td align="left">

Every day, AI news explodes across Hacker News, Reddit, GitHub, RSS, Twitter/X, Telegram, OSS trending lists, and financial feeds.<br>
This project turns that chaos into a usable creator workflow: collect signals, score what matters, enrich the context, write a readable summary, generate a Xiaohongshu-native post, create or attach a cover image, and publish through browser automation.

</td></tr>
</table>

**A personal AI news desk + content editor + publishing robot.**

[What it does](#what-it-does) · [Pipeline](#pipeline) · [Tech stack](#tech-stack) · [Quick start](#quick-start) · [Configuration](#configuration) · [Project structure](#project-structure)

</div>

---

## Why This Project Stands Out

Most news bots stop at "fetch links and ask an LLM to summarize them." This project goes further:

| Layer | What happens |
| --- | --- |
| Signal collection | Pulls from multiple developer, research, social, OSS, and market/news sources |
| Normalization | Converts every source into one typed `ContentItem` model |
| AI ranking | Scores each item and explains why it matters |
| Deduplication | Removes repeated URLs and semantically similar stories |
| Enrichment | Adds related background context before writing the final summary |
| Creator packaging | Turns the top story or full summary into a Xiaohongshu-ready note |
| Publishing | Sends to an endpoint or drives Xiaohongshu Creator Center through Chrome/CDP |

The result is not just an aggregator. It is an end-to-end content production system.

### Recruiter Snapshot

| Signal | Why it matters |
| --- | --- |
| Product thinking | Solves a real creator workflow, not a toy "LLM wrapper" demo |
| Backend depth | Async collectors, typed configs, retries, concurrency limits, storage, notifications |
| AI engineering | Multi-provider abstraction, scoring prompts, JSON parsing fallbacks, enrichment, token tracking |
| Automation | Bridges generated content into a real browser-based publishing workflow |
| Maintainability | Clear module boundaries, focused tests, documented config, replaceable integrations |

## What It Does

- Collects AI and tech signals from Hacker News, RSS, Reddit, GitHub, Telegram, Twitter/X via Apify, OSS Insight, and OpenBB.
- Runs asynchronous scraping and keeps source output consistent with Pydantic models.
- Uses configurable LLM providers to score, summarize, translate, enrich, and rewrite content.
- Supports multiple AI providers: OpenAI, Anthropic, Azure OpenAI, Gemini, DeepSeek, Doubao, MiniMax, Ali DashScope-compatible APIs, and Ollama-compatible local models.
- Generates Chinese or English daily summaries.
- Converts the highest-scored story into a stronger Xiaohongshu post with:
  - short, high-click title
  - deeper Chinese body copy
  - discussion-oriented ending
  - topic tags
  - generated cover prompt or configured media
- Publishes through either a custom HTTP endpoint or the bundled `XiaohongshuSkills` local Chrome/CDP automation pipeline.
- Can send summaries through email or webhooks for Feishu/Lark, DingTalk, Slack, Discord, or generic integrations.

## Pipeline

```text
Sources
  Hacker News · RSS · Reddit · GitHub · Telegram · Twitter/X · OSS Insight · OpenBB
      │
      ▼
Async collectors
      │
      ▼
Unified ContentItem model
      │
      ▼
URL + topic deduplication
      │
      ▼
LLM scoring, reasoning, tags, summary
      │
      ▼
Background enrichment + daily summary
      │
      └── Xiaohongshu note polish + cover image + CDP publishing
```

## Tech Stack

| Area | Technologies |
| --- | --- |
| Language | Python 3.11+ |
| Runtime / packaging | `uv`, Hatchling, console scripts |
| Async I/O | `asyncio`, `httpx` |
| Data modeling | Pydantic v2, typed config models, normalized source models |
| LLM providers | OpenAI, Anthropic, Azure OpenAI, Google Gemini, OpenAI-compatible providers, Ollama |
| Scraping / feeds | Hacker News API, RSS/Atom via `feedparser`, Reddit RSS, GitHub APIs, Telegram channels, Apify Twitter/X, OSS Insight, optional OpenBB SDK |
| Content processing | BeautifulSoup, Markdown parsing, JSON repair/parsing utilities |
| Reliability | Tenacity retries, provider throttling, configurable concurrency, token usage tracking |
| CLI experience | Rich console output, progress bars, installable commands |
| Publishing | Xiaohongshu Creator Center automation through Chrome DevTools Protocol |
| Notifications | SMTP/IMAP email, configurable webhook payloads |
| Testing | `pytest`, `pytest-asyncio`, focused tests for scrapers, storage, AI clients, webhooks, email, and Xiaohongshu publishing |

## Quick Start

Install dependencies:

```bash
uv sync --extra dev
```

Create local config:

```bash
cp data/config.example.json data/config.json
```

Create a local `.env` file with the secrets you actually use:

```bash
OPENAI_API_KEY=your_key_here
ANTHROPIC_API_KEY=your_key_here
GITHUB_TOKEN=optional_but_recommended
APIFY_TOKEN=optional_for_twitter_x
```

Run the full pipeline:

```bash
uv run ainews-xhs
```

Force a longer lookback window:

```bash
uv run ainews-xhs --hours 48
```

Run tests:

```bash
uv run python -m pytest
```

## Xiaohongshu Publishing

The project supports two publishing modes.

| Mode | Use case |
| --- | --- |
| `endpoint` | Send a structured note payload to your own service |
| `local_cdp` | Use the bundled Chrome/CDP automation to publish in Xiaohongshu Creator Center |

For local publishing, set the pipeline path in `.env`:

```bash
XIAOHONGSHU_PIPELINE=./XiaohongshuSkills/scripts/publish_pipeline.py
```

Then configure `data/config.json`:

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

Keep `preview` enabled until Chrome is logged in and the generated note looks right. Only use publish mode after the preview flow is verified.

You can also publish an existing summary:

```bash
uv run ainews-xhs-publish \
  --summary data/summaries/ainews-xhs-YYYY-MM-DD-zh.md \
  --lang zh \
  --preview
```

## Configuration

The app uses two local files:

| File | Purpose |
| --- | --- |
| `.env` | Secrets and API keys |
| `data/config.json` | Sources, model provider, scoring, language, delivery, and publishing settings |

Important knobs:

| Setting | Meaning |
| --- | --- |
| `ai.provider` / `ai.model` | Select the LLM backend |
| `ai.analysis_concurrency` | Parallelism for AI scoring |
| `ai.enrichment_concurrency` | Parallelism for second-stage enrichment |
| `filtering.ai_score_threshold` | Minimum score kept for summaries and posts |
| `filtering.time_window_hours` | Default fetch window |
| `xiaohongshu.post_source` | Choose `top_scored_item` or `summary` |
| `xiaohongshu.polish_with_ai` | Rewrite the note into a Xiaohongshu-native style |
| `webhook.platform` | Format notifications for generic, Feishu/Lark, DingTalk, Slack, or Discord |

See [docs/configuration.md](docs/configuration.md) for details.

## Source Coverage

| Source | Notes |
| --- | --- |
| Hacker News | Top stories with score filtering |
| RSS / Atom | Blogs, research feeds, newsletters, custom feeds |
| Reddit | Subreddits, user feeds, top comments |
| GitHub | User events and repository releases |
| Telegram | Public channel monitoring |
| Twitter/X | Apify-backed collection, optional reply expansion |
| OSS Insight | Trending open-source repositories |
| OpenBB | Optional market news and SEC-style filing sources |

See [docs/scrapers.md](docs/scrapers.md) for collector notes.

## Project Structure

```text
.
├── src/
│   ├── ai/                 LLM clients, prompts, scoring, enrichment, summaries
│   ├── scrapers/           Source collectors and normalized content ingestion
│   ├── services/           Xiaohongshu, email, and webhook delivery
│   ├── storage/            Config loading and runtime output persistence
│   ├── main.py             Main CLI entry point
│   ├── models.py           Pydantic models for config and content
│   └── orchestrator.py     End-to-end pipeline coordinator
├── XiaohongshuSkills/      Bundled Chrome/CDP publisher for Xiaohongshu
├── data/                   Example config and presets
├── docs/                   Configuration, scoring, and scraper docs
├── tests/                  Unit tests for core behavior
├── pyproject.toml          Package metadata, dependencies, CLI scripts
└── LICENSE
```

## CLI Commands

| Command | Description |
| --- | --- |
| `uv run ainews-xhs` | Run collection, ranking, summary generation, and optional publishing |
| `uv run ainews-xhs --hours 48` | Override the configured lookback window |
| `uv run ainews-xhs-publish --summary ... --preview` | Publish or preview an existing summary |
| `uv run ainews-xhs-webhook` | Run webhook helper CLI |
| `uv run python -m pytest` | Run the test suite |

## Security Notes

- Do not commit `.env` or `data/config.json`.
- Keep API keys in environment variables.
- Runtime summaries and Xiaohongshu assets are generated under `data/` and should stay local.
- Use `preview` mode before allowing the browser automation to click publish.


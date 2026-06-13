# Scrapers

Collectors live in `src/scrapers/` and return normalized `ContentItem` objects.
The current project includes collectors for:

- Hacker News
- RSS feeds
- Reddit RSS
- GitHub events and releases
- Telegram channels
- Twitter/X through Apify
- OSS Insight
- OpenBB market/news sources

Most sources are configured under `sources` in `data/config.json`. Expensive or
credentialed sources are disabled in the example config until their tokens or
optional dependencies are available.

Scrapers run asynchronously, then the pipeline deduplicates URLs and related
topics before enrichment, summarization, and Xiaohongshu post generation.

"""CLI for publishing an existing AI news summary to Xiaohongshu."""

import argparse
import asyncio
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console

from ..services.xiaohongshu import XiaohongshuPublisher
from ..storage.manager import ConfigError, StorageManager


console = Console()


def _latest_summary_path(summaries_dir: Path, lang: str) -> Path:
    candidates = sorted(summaries_dir.glob(f"ainews-xhs-*-{lang}.md"))
    candidates.extend(sorted(summaries_dir.glob(f"horizon-*-{lang}.md")))
    if not candidates:
        raise FileNotFoundError(f"No saved AI news summary found for language: {lang}")
    return candidates[-1]


def _date_from_summary_path(path: Path) -> str:
    parts = path.stem.split("-")
    if len(parts) >= 6 and parts[0] == "ainews" and parts[1] == "xhs":
        return "-".join(parts[2:5])
    if len(parts) >= 5 and parts[0] == "horizon":
        return "-".join(parts[1:4])
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


async def _run(args: argparse.Namespace) -> bool:
    load_dotenv()
    storage = StorageManager(data_dir=args.data_dir)
    try:
        config = storage.load_config()
    except (FileNotFoundError, ConfigError) as exc:
        console.print(f"[red]Failed to load config: {exc}[/red]")
        return False

    if not config.xiaohongshu or not config.xiaohongshu.enabled:
        console.print("[red]Xiaohongshu publishing is not enabled in config.[/red]")
        return False

    lang = args.lang
    summary_path = Path(args.summary).expanduser() if args.summary else _latest_summary_path(
        storage.summaries_dir,
        lang,
    )
    if not summary_path.exists():
        console.print(f"[red]Summary file not found: {summary_path}[/red]")
        return False

    summary = summary_path.read_text(encoding="utf-8")
    date = args.date or _date_from_summary_path(summary_path)

    if args.publish:
        config.xiaohongshu.preview = False
    elif args.preview:
        config.xiaohongshu.preview = True

    publisher = XiaohongshuPublisher(config.xiaohongshu, console=console)
    console.print(f"📕 Publishing saved summary: {summary_path}")
    return await publisher.publish_daily_summary(
        summary=summary,
        important_items=[],
        date=date,
        lang=lang,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Publish an existing AI news summary to Xiaohongshu."
    )
    parser.add_argument(
        "--data-dir",
        default="data",
        help="Data directory containing config.json and summaries/.",
    )
    parser.add_argument(
        "--summary",
        default=None,
        help="Path to an existing summary markdown file. Defaults to latest for --lang.",
    )
    parser.add_argument("--lang", default="zh", help="Summary language, default: zh.")
    parser.add_argument("--date", default=None, help="Publish date, default: inferred.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--preview",
        action="store_true",
        help="Fill Xiaohongshu page only, overriding config preview to true.",
    )
    mode.add_argument(
        "--publish",
        action="store_true",
        help="Click publish, overriding config preview to false.",
    )
    args = parser.parse_args()
    ok = asyncio.run(_run(args))
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()

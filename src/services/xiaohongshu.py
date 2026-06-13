"""Xiaohongshu publishing service for AI news summaries."""

import asyncio
import base64
import logging
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, List, Optional
from urllib.parse import urlparse

import httpx

from ..models import ContentItem, XiaohongshuConfig
from ..ai.utils import parse_json_response

logger = logging.getLogger(__name__)


def _strip_markdown(value: str) -> str:
    """Convert common Markdown markup into plain social-post text."""
    text = re.sub(r"<[^>]+>", "", value)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"[*_`>#~-]+", "", text)
    text = "\n".join(line.strip() for line in text.splitlines())
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _truncate_text(value: str, limit: int) -> str:
    """Truncate text to a character limit while keeping a clear suffix."""
    if limit <= 0 or len(value) <= limit:
        return value
    suffix = "\n\n更多内容见今日 AI 新闻汇总。"
    if limit <= len(suffix):
        return value[:limit].rstrip()
    keep = max(0, limit - len(suffix))
    return value[:keep].rstrip() + suffix


def _truncate_title(value: str, limit: int) -> str:
    """Truncate a Xiaohongshu title without adding body-style suffix text."""
    if limit <= 0 or len(value) <= limit:
        return value
    return value[:limit].rstrip()


def _is_http_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.hostname)


class XiaohongshuPublisher:
    """Publishes daily AI news summaries to Xiaohongshu."""

    def __init__(self, config: XiaohongshuConfig, console=None):
        self.config = config
        self.console = console
        self.endpoint = self._load_endpoint()
        self.api_key = os.getenv(config.api_key_env) if config.api_key_env else None

    def _print(self, message: str) -> None:
        if self.console is not None:
            self.console.print(message)

    def _load_endpoint(self) -> Optional[str]:
        if not self.config.enabled or self.config.publish_mode != "endpoint":
            return None
        if not self.config.endpoint_env:
            self._print(
                "[yellow]Xiaohongshu publishing enabled but 'endpoint_env' is not set. "
                "Skipping.[/yellow]"
            )
            return None
        endpoint = os.getenv(self.config.endpoint_env)
        if not endpoint:
            self._print(
                f"[yellow]Xiaohongshu publishing enabled but env var "
                f"'{self.config.endpoint_env}' is not set. Skipping.[/yellow]"
            )
            return None
        endpoint = endpoint.strip()
        parsed = urlparse(endpoint)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError(
                f"Xiaohongshu endpoint must be a valid http(s) URL "
                f"(env var '{self.config.endpoint_env}')"
            )
        return endpoint

    def _resolve_local_pipeline(self) -> Path:
        configured = self.config.local_pipeline_path
        env_path = os.getenv(self.config.local_pipeline_env) if self.config.local_pipeline_env else None
        project_root = Path(__file__).resolve().parents[2]
        candidates = [
            Path(configured).expanduser() if configured else None,
            Path(env_path).expanduser() if env_path else None,
            Path.cwd() / "XiaohongshuSkills" / "scripts" / "publish_pipeline.py",
            project_root / "XiaohongshuSkills" / "scripts" / "publish_pipeline.py",
        ]
        for candidate in candidates:
            if candidate and candidate.exists():
                return candidate.resolve()
        checked = ", ".join(str(c) for c in candidates if c)
        raise FileNotFoundError(
            "Xiaohongshu local CDP pipeline not found. Set "
            f"{self.config.local_pipeline_env} or xiaohongshu.local_pipeline_path. "
            f"Checked: {checked}"
        )

    def should_publish_language(self, lang: str) -> bool:
        """Return whether this language should be posted."""
        return not self.config.languages or lang in self.config.languages

    def build_note(
        self,
        summary: str,
        important_items: List[ContentItem],
        date: str,
        lang: str,
    ) -> dict[str, Any]:
        """Build the text note payload sent to the automation endpoint."""
        if self.config.post_source == "top_scored_item" and important_items:
            return self.build_top_item_note(important_items, date, lang)

        title = self.config.title_template.format(date=date, lang=lang)
        items = important_items[: max(0, self.config.max_items)]
        lines = [title, "", "今日要点："]

        if items:
            for index, item in enumerate(items, start=1):
                item_title = str(item.metadata.get(f"title_{lang}") or item.title)
                item_summary = str(
                    item.metadata.get(f"summary_{lang}")
                    or item.ai_summary
                    or item.ai_reason
                    or ""
                )
                lines.append(f"{index}. {_strip_markdown(item_title)}")
                if item_summary:
                    lines.append(f"   {_strip_markdown(item_summary)}")
                if self.config.include_links:
                    lines.append(f"   {item.url}")
        else:
            cleaned_summary = _strip_markdown(summary)
            lines.append(cleaned_summary or "今天暂无达到重要性阈值的新闻。")

        tags = [tag.strip().lstrip("#") for tag in self.config.tags if tag.strip()]
        if tags:
            lines.extend(["", " ".join(f"#{tag}" for tag in tags)])

        content = _truncate_text("\n".join(lines).strip(), self.config.max_content_chars)
        return {
            "platform": "xiaohongshu",
            "title": title,
            "content": content,
            "tags": tags,
            "date": date,
            "language": lang,
            "items": [
                {
                    "title": str(item.metadata.get(f"title_{lang}") or item.title),
                    "url": str(item.url),
                    "score": item.ai_score,
                    "tags": item.ai_tags,
                }
                for item in items
            ],
        }

    def build_top_item_note(
        self,
        important_items: List[ContentItem],
        date: str,
        lang: str,
    ) -> dict[str, Any]:
        """Build a Xiaohongshu note from the highest-scored item of the day."""
        top_item = max(important_items, key=lambda item: item.ai_score or 0)
        item_title = str(top_item.metadata.get(f"title_{lang}") or top_item.title)
        item_summary = str(
            top_item.metadata.get(f"summary_{lang}")
            or top_item.ai_summary
            or top_item.ai_reason
            or top_item.content
            or ""
        )
        score = top_item.ai_score or 0
        title = _truncate_title(_strip_markdown(item_title), self.config.title_max_chars)

        lines = [
            f"今天最值得聊的一条 AI 新闻：{_strip_markdown(item_title)}",
            "",
        ]
        if item_summary:
            lines.extend(["它在说什么：", _strip_markdown(item_summary), ""])
        if top_item.ai_reason:
            lines.extend(["为什么值得关注：", _strip_markdown(top_item.ai_reason), ""])
        lines.extend([
            "我的观察：",
            "这类更新表面上是产品或技术进展，真正值得讨论的是它会怎样改变工具、平台和人的分工。",
            "",
            "你觉得这是一次真实进步，还是又一轮 AI 热点包装？",
        ])
        if self.config.include_links:
            lines.extend(["", str(top_item.url)])

        tags = [tag.strip().lstrip("#") for tag in self.config.tags if tag.strip()]
        if tags:
            lines.extend(["", " ".join(f"#{tag}" for tag in tags)])

        content = _truncate_text("\n".join(lines).strip(), self.config.max_content_chars)
        return {
            "platform": "xiaohongshu",
            "title": title,
            "content": content,
            "tags": tags,
            "date": date,
            "language": lang,
            "items": [
                {
                    "title": item_title,
                    "url": str(top_item.url),
                    "score": score,
                    "tags": top_item.ai_tags,
                    "summary": item_summary,
                    "reason": top_item.ai_reason,
                    "content": top_item.content,
                    "source": top_item.source_type.value,
                    "author": top_item.author,
                }
            ],
        }

    async def polish_note(
        self,
        note: dict[str, Any],
        ai_client: Any | None = None,
    ) -> dict[str, Any]:
        """Rewrite a note into a Xiaohongshu-native post when an AI client is available."""
        if not self.config.polish_with_ai or ai_client is None:
            return note

        item = (note.get("items") or [{}])[0]
        tags = " ".join(f"#{tag}" for tag in note.get("tags", []))
        user_prompt = f"""
请基于下面素材输出严格 JSON，不要 Markdown，不要代码块。

输出字段：
- title: 小红书标题，中文，最多 {self.config.title_max_chars} 个字，有点击率但不夸张
- content: 小红书正文，中文，分段清晰，有深度、有趣、能引发讨论，结尾必须是开放式问题
- image_prompt: 用于生成封面图的英文提示词，适合科技新闻封面，避免真实公司 logo 和大量文字
- tags: 3 到 6 个中文标签，不带 #

编辑要求：
{self.config.polish_prompt}

素材：
日期：{note.get("date")}
原始标题：{item.get("title") or note.get("title")}
来源：{item.get("source") or ""}
评分：{item.get("score") or ""}
摘要：{item.get("summary") or ""}
重要性原因：{item.get("reason") or ""}
正文/讨论摘录：{_truncate_text(_strip_markdown(str(item.get("content") or "")), 1600)}
默认标签：{tags}
"""
        response = await ai_client.complete(
            system="你是资深中文科技内容编辑，只输出可解析 JSON。",
            user=user_prompt,
            temperature=0.7,
            max_tokens=1200,
        )
        result = parse_json_response(response)
        if not isinstance(result, dict):
            return note

        title = _strip_markdown(str(result.get("title") or "")).strip()
        content = _strip_markdown(str(result.get("content") or "")).strip()
        image_prompt = str(result.get("image_prompt") or "").strip()
        tags_value = result.get("tags")
        if isinstance(tags_value, list):
            tags = [str(tag).strip().lstrip("#") for tag in tags_value if str(tag).strip()]
        else:
            tags = note.get("tags") or []

        if title:
            note["title"] = _truncate_title(title, self.config.title_max_chars)
        if content:
            if tags:
                content = content.rstrip() + "\n\n" + " ".join(f"#{tag}" for tag in tags)
            note["content"] = _truncate_text(content, self.config.max_content_chars)
        if tags:
            note["tags"] = tags
        if image_prompt:
            note["image_prompt"] = image_prompt
        return note

    def build_image_prompt(self, note: dict[str, Any]) -> str:
        """Build the image prompt from the note payload."""
        if note.get("image_prompt"):
            return str(note["image_prompt"])

        image_config = self.config.image_generation
        items = note.get("items") or []
        item_lines = []
        for item in items[: max(1, self.config.max_items)]:
            title = _strip_markdown(str(item.get("title") or "")).strip()
            if title:
                item_lines.append(f"- {title}")
        if not item_lines:
            item_lines.append("- Daily technology news briefing")

        return image_config.prompt_template.format(
            title=note.get("title", ""),
            content=note.get("content", ""),
            date=note.get("date", ""),
            lang=note.get("language", ""),
            items="\n".join(item_lines),
        )

    async def generate_images(self, note: dict[str, Any]) -> list[str]:
        """Generate local image files for the Xiaohongshu note."""
        image_config = self.config.image_generation
        if not image_config.enabled:
            return []
        if image_config.provider != "openai":
            raise ValueError(f"Unsupported Xiaohongshu image provider: {image_config.provider}")

        api_key = os.getenv(image_config.api_key_env)
        if not api_key:
            raise ValueError(f"Missing image generation API key: {image_config.api_key_env}")

        endpoint = os.getenv(image_config.endpoint_env) if image_config.endpoint_env else None
        if not endpoint:
            endpoint = image_config.base_url.rstrip("/") + "/images/generations"

        prompt = self.build_image_prompt(note)
        payload: dict[str, Any] = {
            "model": image_config.model,
            "prompt": prompt,
            "size": image_config.size,
            "n": max(1, image_config.count),
        }
        if image_config.quality:
            payload["quality"] = image_config.quality

        output_dir = Path(image_config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        self._print(f"🖼️  Generating Xiaohongshu image with {image_config.model}...")

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                endpoint,
                json=payload,
                headers={"Authorization": f"Bearer {api_key}"},
            )
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                detail = response.text[:1200]
                raise ValueError(
                    f"Image generation API returned {response.status_code}: {detail}"
                ) from exc
            data = response.json()
            entries = data.get("data") if isinstance(data, dict) else None
            if not isinstance(entries, list) or not entries:
                raise ValueError("Image generation response did not include data[]")

            image_paths: list[str] = []
            for index, entry in enumerate(entries, start=1):
                if not isinstance(entry, dict):
                    continue
                filename = self._generated_image_filename(note, index)
                path = output_dir / filename
                b64_json = entry.get("b64_json")
                image_url = entry.get("url")
                if isinstance(b64_json, str) and b64_json:
                    path.write_bytes(base64.b64decode(b64_json))
                    image_paths.append(str(path))
                elif isinstance(image_url, str) and _is_http_url(image_url):
                    image_response = await client.get(image_url)
                    image_response.raise_for_status()
                    path.write_bytes(image_response.content)
                    image_paths.append(str(path))

        if not image_paths:
            raise ValueError("Image generation did not produce downloadable image data")
        return image_paths

    def _generated_image_filename(self, note: dict[str, Any], index: int) -> str:
        date = re.sub(r"[^0-9-]+", "", str(note.get("date") or "ainews-xhs"))
        lang = re.sub(r"[^A-Za-z0-9_-]+", "", str(note.get("language") or "note"))
        return f"{date}-{lang}-{index}.png"

    def _configured_media_count(self) -> int:
        return sum(
            1
            for selected in (
                self.config.image_paths,
                self.config.image_urls,
                self.config.video_path,
                self.config.video_url,
            )
            if selected
        )

    def _build_local_publish_command(
        self,
        *,
        pipeline_path: Path,
        title_file: Path,
        content_file: Path,
        generated_image_paths: list[str],
    ) -> list[str]:
        media_count = 1 if generated_image_paths else self._configured_media_count()
        if media_count != 1:
            raise ValueError(
                "Local Xiaohongshu publishing requires exactly one media source: "
                "generated images, image_paths, image_urls, video_path, or video_url."
            )

        cmd = [
            sys.executable,
            str(pipeline_path),
            "--title-file",
            str(title_file),
            "--content-file",
            str(content_file),
            "--host",
            self.config.host,
            "--port",
            str(self.config.port),
            "--timing-jitter",
            str(self.config.timing_jitter),
        ]
        if self.config.preview:
            cmd.append("--preview")
        if self.config.headless:
            cmd.append("--headless")
        if self.config.reuse_existing_tab:
            cmd.append("--reuse-existing-tab")
        if self.config.account:
            cmd.extend(["--account", self.config.account])
        if self.config.post_time:
            cmd.extend(["--post-time", self.config.post_time])

        if generated_image_paths:
            cmd.append("--images")
            cmd.extend(generated_image_paths)
        elif self.config.image_paths:
            cmd.append("--images")
            cmd.extend(self.config.image_paths)
        elif self.config.image_urls:
            cmd.append("--image-urls")
            cmd.extend(self.config.image_urls)
        elif self.config.video_path:
            cmd.extend(["--video", self.config.video_path])
        elif self.config.video_url:
            cmd.extend(["--video-url", self.config.video_url])

        return cmd

    async def _publish_via_local_cdp(
        self,
        note: dict[str, Any],
        generated_image_paths: list[str],
    ) -> bool:
        pipeline_path = self._resolve_local_pipeline()
        with tempfile.TemporaryDirectory(prefix="ainews_xhs_") as temp_dir:
            temp_path = Path(temp_dir)
            title_file = temp_path / "title.txt"
            content_file = temp_path / "content.txt"
            title_file.write_text(str(note["title"]), encoding="utf-8")
            content_file.write_text(str(note["content"]), encoding="utf-8")
            cmd = self._build_local_publish_command(
                pipeline_path=pipeline_path,
                title_file=title_file,
                content_file=content_file,
                generated_image_paths=generated_image_paths,
            )

            self._print("📕 Publishing Xiaohongshu note via local CDP pipeline...")
            result = await asyncio.to_thread(
                subprocess.run,
                cmd,
                cwd=str(pipeline_path.parents[2]),
                text=True,
                capture_output=True,
                check=False,
            )

        if result.stdout:
            logger.info("Xiaohongshu pipeline stdout:\n%s", result.stdout)
        if result.stderr:
            logger.warning("Xiaohongshu pipeline stderr:\n%s", result.stderr)
        if result.returncode != 0:
            self._print(
                f"[red]Xiaohongshu local publishing failed with exit code "
                f"{result.returncode}.[/red]"
            )
            return False
        return True

    async def publish_daily_summary(
        self,
        summary: str,
        important_items: List[ContentItem],
        date: str,
        lang: str,
        ai_client: Any | None = None,
    ) -> bool:
        """POST a daily Xiaohongshu note to the configured endpoint."""
        if not self.config.enabled or not self.should_publish_language(lang):
            return False
        if self.config.publish_mode == "endpoint" and not self.endpoint:
            return False

        payload = self.build_note(summary, important_items, date, lang)
        try:
            payload = await self.polish_note(payload, ai_client=ai_client)
        except Exception as e:
            self._print(f"[yellow]Xiaohongshu note polish failed, using fallback: {e}[/yellow]")
            logger.warning("Xiaohongshu note polish failed: %s", e)
        generated_image_paths: list[str] = []
        try:
            generated_image_paths = await self.generate_images(payload)
        except (httpx.HTTPError, ValueError) as e:
            if self._configured_media_count() == 1:
                self._print(
                    "[yellow]Xiaohongshu image generation failed; using configured "
                    f"fallback media: {e}[/yellow]"
                )
                logger.warning(
                    "Xiaohongshu image generation failed; using fallback media: %s",
                    e,
                )
            else:
                self._print(f"[red]Xiaohongshu image generation failed: {e}[/red]")
                logger.error("Xiaohongshu image generation failed: %s", e)
                return False

        if generated_image_paths:
            payload["image_paths"] = generated_image_paths

        if self.config.publish_mode == "local_cdp":
            try:
                return await self._publish_via_local_cdp(payload, generated_image_paths)
            except (OSError, ValueError) as e:
                self._print(f"[red]Xiaohongshu local publishing failed: {e}[/red]")
                logger.error("Xiaohongshu local publishing failed: %s", e)
                return False

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            key_value = self.api_key
            if self.config.api_key_header.lower() == "authorization" and not re.match(
                r"^\w+\s+", key_value
            ):
                key_value = f"Bearer {key_value}"
            headers[self.config.api_key_header] = key_value

        self._print(f"📕 Publishing {lang.upper()} summary to Xiaohongshu...")
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(self.endpoint, json=payload, headers=headers)
                response.raise_for_status()
        except httpx.HTTPError as e:
            self._print(f"[red]Xiaohongshu publishing failed: {e}[/red]")
            logger.error("Xiaohongshu publishing failed: %s", e)
            return False

        logger.info("Published Xiaohongshu daily summary for %s", lang)
        return True

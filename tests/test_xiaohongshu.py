import base64
import os
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models import ContentItem, SourceType, XiaohongshuConfig, XiaohongshuImageConfig
from src.services.xiaohongshu import XiaohongshuPublisher, _strip_markdown, _truncate_text


def make_item(**overrides):
    data = {
        "id": "rss:test:1",
        "source_type": SourceType.RSS,
        "title": "OpenAI releases a new model",
        "url": "https://example.com/news",
        "content": "Full text",
        "published_at": datetime(2026, 5, 29, tzinfo=timezone.utc),
        "metadata": {"title_zh": "OpenAI 发布新模型", "summary_zh": "推理和工具调用能力提升。"},
        "ai_score": 9.0,
        "ai_reason": "Important AI platform update",
        "ai_summary": "A new model was released.",
        "ai_tags": ["AI", "OpenAI"],
    }
    data.update(overrides)
    return ContentItem(**data)


def test_strip_markdown_for_social_text():
    assert _strip_markdown("## [Title](https://example.com)\n> **bold**") == "Title\nbold"


def test_truncate_text_appends_suffix():
    result = _truncate_text("a" * 120, 60)
    assert len(result) <= 60
    assert result.endswith("更多内容见今日 AI 新闻汇总。")


def test_build_note_uses_localized_item_fields():
    cfg = XiaohongshuConfig(
        enabled=True,
        endpoint_env="XHS_ENDPOINT",
        languages=["zh"],
        tags=["AI新闻"],
    )
    publisher = XiaohongshuPublisher(cfg)

    note = publisher.build_note(
        summary="# Daily",
        important_items=[make_item()],
        date="2026-05-29",
        lang="zh",
    )

    assert note["title"] == "AI 新闻每日速递 2026-05-29"
    assert "OpenAI 发布新模型" in note["content"]
    assert "推理和工具调用能力提升。" in note["content"]
    assert "#AI新闻" in note["content"]
    assert note["items"][0]["url"] == "https://example.com/news"


def test_build_top_item_note_uses_highest_scored_item():
    cfg = XiaohongshuConfig(
        enabled=True,
        post_source="top_scored_item",
        languages=["zh"],
        tags=["AI新闻"],
    )
    publisher = XiaohongshuPublisher(cfg)
    lower = make_item(
        title="Lower score",
        metadata={"title_zh": "低分新闻", "summary_zh": "不重要。"},
        ai_score=7.0,
    )
    higher = make_item(
        title="Higher score",
        metadata={"title_zh": "高分新闻", "summary_zh": "最值得关注。"},
        ai_score=9.8,
    )

    note = publisher.build_note("# Daily", [lower, higher], "2026-05-29", "zh")

    assert note["title"] == "高分新闻"
    assert "最值得关注。" in note["content"]
    assert note["items"][0]["score"] == 9.8


@pytest.mark.asyncio
async def test_polish_note_updates_title_content_tags_and_image_prompt():
    cfg = XiaohongshuConfig(
        enabled=True,
        post_source="top_scored_item",
        polish_with_ai=True,
        tags=["AI新闻"],
    )
    publisher = XiaohongshuPublisher(cfg)
    note = publisher.build_note("# Daily", [make_item()], "2026-05-29", "zh")
    ai_client = SimpleNamespace(
        complete=AsyncMock(
            return_value=(
                '{"title":"AI 今天真正变天了吗",'
                '"content":"这条新闻值得看，因为它影响工具入口。\\n\\n你怎么看？",'
                '"image_prompt":"editorial tech cover, abstract AI workflow",'
                '"tags":["AI新闻","科技观察","工具革命"]}'
            )
        )
    )

    result = await publisher.polish_note(note, ai_client=ai_client)

    assert result["title"] == "AI 今天真正变天了吗"
    assert "工具入口" in result["content"]
    assert "#科技观察" in result["content"]
    assert result["image_prompt"] == "editorial tech cover, abstract AI workflow"
    assert result["tags"] == ["AI新闻", "科技观察", "工具革命"]


def test_build_image_prompt_prefers_polished_prompt():
    cfg = XiaohongshuConfig(enabled=True)
    publisher = XiaohongshuPublisher(cfg)

    prompt = publisher.build_image_prompt({"image_prompt": "custom cover prompt"})

    assert prompt == "custom cover prompt"


def test_should_publish_language_respects_filter():
    cfg = XiaohongshuConfig(enabled=True, endpoint_env="XHS_ENDPOINT", languages=["zh"])
    publisher = XiaohongshuPublisher(cfg)

    assert publisher.should_publish_language("zh") is True
    assert publisher.should_publish_language("en") is False


@pytest.mark.asyncio
async def test_publish_skips_when_endpoint_missing(monkeypatch):
    monkeypatch.delenv("XHS_ENDPOINT", raising=False)
    cfg = XiaohongshuConfig(enabled=True, endpoint_env="XHS_ENDPOINT")
    publisher = XiaohongshuPublisher(cfg)

    result = await publisher.publish_daily_summary("# Summary", [make_item()], "2026-05-29", "zh")

    assert result is False


@pytest.mark.asyncio
async def test_publish_posts_payload_with_bearer_token(monkeypatch):
    monkeypatch.setenv("XHS_ENDPOINT", "https://poster.example.com/xhs")
    monkeypatch.setenv("XHS_API_KEY", "secret-token")
    cfg = XiaohongshuConfig(
        enabled=True,
        endpoint_env="XHS_ENDPOINT",
        api_key_env="XHS_API_KEY",
        languages=["zh"],
    )
    publisher = XiaohongshuPublisher(cfg)

    response = MagicMock()
    response.raise_for_status = MagicMock()
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.post = AsyncMock(return_value=response)

    with patch("src.services.xiaohongshu.httpx.AsyncClient", return_value=client):
        result = await publisher.publish_daily_summary(
            "# Summary",
            [make_item()],
            "2026-05-29",
            "zh",
        )

    assert result is True
    client.post.assert_awaited_once()
    _, kwargs = client.post.call_args
    assert kwargs["json"]["platform"] == "xiaohongshu"
    assert kwargs["json"]["language"] == "zh"
    assert kwargs["headers"]["Authorization"] == "Bearer secret-token"


@pytest.mark.asyncio
async def test_generate_images_saves_base64_response(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "image-token")
    cfg = XiaohongshuConfig(
        enabled=True,
        image_generation=XiaohongshuImageConfig(
            enabled=True,
            output_dir=str(tmp_path),
            count=1,
        ),
    )
    publisher = XiaohongshuPublisher(cfg)
    note = publisher.build_note("# Summary", [make_item()], "2026-05-29", "zh")

    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = {
        "data": [{"b64_json": base64.b64encode(b"png-bytes").decode("ascii")}]
    }
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.post = AsyncMock(return_value=response)

    with patch("src.services.xiaohongshu.httpx.AsyncClient", return_value=client):
        paths = await publisher.generate_images(note)

    assert len(paths) == 1
    assert Path(paths[0]).read_bytes() == b"png-bytes"
    _, kwargs = client.post.call_args
    assert kwargs["json"]["model"] == "gpt-image-1"
    assert kwargs["headers"]["Authorization"] == "Bearer image-token"


@pytest.mark.asyncio
async def test_local_cdp_publish_uses_generated_images(monkeypatch, tmp_path):
    monkeypatch.delenv("XHS_ENDPOINT", raising=False)
    pipeline = tmp_path / "XiaohongshuSkills" / "scripts" / "publish_pipeline.py"
    pipeline.parent.mkdir(parents=True)
    pipeline.write_text("# test pipeline\n", encoding="utf-8")
    image_path = tmp_path / "cover.png"
    image_path.write_bytes(b"png")
    cfg = XiaohongshuConfig(
        enabled=True,
        publish_mode="local_cdp",
        preview=False,
        headless=True,
        account="main",
    )
    publisher = XiaohongshuPublisher(cfg)

    run_result = SimpleNamespace(returncode=0, stdout="PUBLISH_STATUS: PUBLISHED", stderr="")
    with (
        patch.object(publisher, "_resolve_local_pipeline", return_value=pipeline),
        patch.object(publisher, "generate_images", new=AsyncMock(return_value=[str(image_path)])),
        patch("src.services.xiaohongshu.subprocess.run", return_value=run_result) as run_mock,
    ):
        result = await publisher.publish_daily_summary(
            "# Summary",
            [make_item()],
            "2026-05-29",
            "zh",
        )

    assert result is True
    cmd = run_mock.call_args.args[0]
    assert str(pipeline) in cmd
    assert "--images" in cmd
    assert str(image_path) in cmd
    assert "--headless" in cmd
    assert "--account" in cmd
    assert "main" in cmd
    assert "--preview" not in cmd


def teardown_module():
    os.environ.pop("XHS_ENDPOINT", None)
    os.environ.pop("XHS_API_KEY", None)
    os.environ.pop("OPENAI_API_KEY", None)

from __future__ import annotations

import json
from datetime import datetime

from scripts.generate_magazine import build_weekly_digest, generate_html, render_briefing
from scripts.notify_feishu import build_feishu_message


def make_story(idx: int, *, label: str = "官方更新", summary: str = "") -> dict:
    return {
        "story_id": f"story-{idx}",
        "title": f"AI update {idx}",
        "url": f"https://example.com/{idx}",
        "summary": summary,
        "importance_label": label,
        "importance_score": 0.9 - idx * 0.01,
        "score": 0.9 - idx * 0.01,
        "source_count": 2,
        "source_names": ["Official Feed", "Community Feed"],
        "reasons": ["official_source", "high_importance"],
    }


def test_weekly_digest_is_compact_and_actionable():
    items = [
        make_story(1, summary="OpenAI 发布了新的 Agent 能力，可用于自动化任务。"),
        make_story(2, label="多源热议", summary="多个来源同时关注安全评测结果。"),
    ]

    digest = build_weekly_digest(items)

    assert "主线集中在" in digest["overview"]
    assert "Agent" in digest["overview"]
    assert len(digest["key_points"]) == 2
    assert len(digest["recommendations"]) == 1
    assert digest["recommendations"][0]["why"]


def test_magazine_html_renders_compact_editor_note():
    items = [make_story(1, summary="这是一条可以看懂的中文摘要。")]
    digest = build_weekly_digest(items)
    briefing = render_briefing(digest)
    html = generate_html({"items": items, "generated_at": "2026-06-02T12:00:00Z"}, "AI 雷达周报", "AI Radar Weekly", "weekly")

    assert "本周重点" in briefing
    assert "我的推荐" in briefing
    assert "这是一条可以看懂的中文摘要。" not in briefing
    assert "AI update 1" in html


def test_feishu_message_is_dynamic_not_link_only():
    brief = {
        "items": [
            make_story(1, summary="OpenAI 发布了新的 Agent 能力，可用于自动化任务。"),
        ]
    }
    message = build_feishu_message(brief, "https://example.com", datetime(2026, 6, 2, 10, 0))

    assert "本周主线：" in message
    assert "重点" in message
    assert "推荐" in message
    assert "AI update 1" in message
    assert "OpenAI 发布了新的 Agent 能力" not in message
    assert "https://example.com" in message

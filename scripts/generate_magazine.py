#!/usr/bin/env python3
"""Generate a magazine-style weekly AI news briefing HTML from daily-brief.json.

Consumes the ai-news-radar pipeline output (data/daily-brief.json) and renders
a self-contained magazine HTML inspired by the "AI builders 日报" style:
Albert Sans + Noto Serif SC, topbar / masthead / story cards / colophon.

Usage:
    python3 scripts/generate_magazine.py \
        --input data/daily-brief.json \
        --output data/weekly-magazine.html \
        --title "AI 雷达周报" \
        --period "weekly"
"""

from __future__ import annotations
import argparse
import json
import sys
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from html import escape

SH_TZ = timezone(timedelta(hours=8))


def fmt_date_zh(dt_str: str) -> str:
    """Parse ISO datetime and format as Chinese date string."""
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        dt = dt.astimezone(SH_TZ)
        return f"{dt.year}年{dt.month}月{dt.day}日"
    except Exception:
        return dt_str[:10]


def fmt_time_zh(dt_str: str) -> str:
    """Parse ISO datetime and format as HH:MM."""
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        dt = dt.astimezone(SH_TZ)
        return f"{dt.month}.{dt.day} {dt.hour:02d}:{dt.minute:02d}"
    except Exception:
        return ""


def split_title(title: str) -> tuple[str, str]:
    """Split '中文标题 / English Title' into (zh, en)."""
    if " / " in title:
        parts = title.split(" / ", 1)
        return parts[0], parts[1]
    return title, ""


def importance_to_label(story: dict) -> str:
    """Get importance label, fall back to category."""
    return story.get("importance_label") or story.get("category", "动态")


def importance_to_section_num(label: str) -> str:
    """Map importance label to section number for magazine layout."""
    mapping = {
        "官方更新": "01",
        "多源热议": "02",
        "行业动态": "03",
    }
    return mapping.get(label, "03")


def clean_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def story_summary(story: dict) -> str:
    """Prefer a curated source summary; fall back cleanly to metadata."""
    title = clean_text(story.get("title")).lower()
    candidates = [
        story.get("summary"),
        (story.get("primary_item") or {}).get("summary"),
        *[
            source.get("summary")
            for source in story.get("sources", [])
            if isinstance(source, dict)
        ],
    ]
    for candidate in candidates:
        text = clean_text(candidate)
        if text and text.lower() != title and not title.startswith(text.lower()):
            return text
    return ""


def trim_text(text: str, max_chars: int = 190) -> str:
    text = clean_text(text)
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def detect_weekly_themes(texts: list[str]) -> list[str]:
    haystack = " ".join(texts).lower()
    themes = [
        ("基础模型与能力更新", ("模型", "model", "gpt", "gemini", "claude", "qwen", "kimi")),
        ("Agent 与自动化", ("agent", "智能体", "自动化", "workflow", "工作流")),
        ("开发工具与 API", ("api", "sdk", "cli", "developer", "开发工具", "copilot", "codex")),
        ("开源生态", ("开源", "open source", "open-source", "权重", "hugging face")),
        ("安全与评测", ("安全", "风险", "security", "评测", "sandbox", "权限")),
        ("算力与基础设施", ("算力", "数据中心", "芯片", "infrastructure", "data center", "gpu")),
        ("商业化与市场", ("融资", "投资", "营收", "收入", "商业化", "市场", "funding", "revenue")),
        ("政策与版权", ("监管", "政策", "版权", "诉讼", "regulation", "copyright")),
    ]
    return [name for name, keywords in themes if any(keyword in haystack for keyword in keywords)]


def human_reason(story: dict) -> str:
    reasons = set(story.get("reasons", []))
    summary = story_summary(story)
    if any(word in summary.lower() for word in ("安全", "风险", "security", "sandbox", "权限")):
        return "这条涉及安全和权限边界，建议检查自己的 Agent/API 使用方式。"
    if "official_source" in reasons:
        return "这是官方一手更新，适合先确认产品/API 是否受影响。"
    if "multi_source" in reasons or int(story.get("source_count") or 1) >= 3:
        return "多个来源同时报道，适合作为本周判断热度的锚点。"
    if any(word in story.get("title", "").lower() for word in ("开源", "open source", "权重", "模型")):
        return "开源或模型更新可以低成本试用，值得放进本周观察清单。"
    if "high_ai_relevance" in reasons or "high_importance" in reasons:
        return "信号强度高，建议点开原文确认与自己的工作是否相关。"
    return "先观察后续落地，不必急着调整现有方案。"


def story_display_detail(story: dict) -> str:
    summary = story_summary(story)
    if summary:
        return trim_text(summary, 80)
    source_names = [clean_text(name) for name in story.get("source_names", []) if clean_text(name)]
    source_text = "、".join(source_names[:2]) if source_names else "已有来源"
    score = float(story.get("importance_score") or story.get("score") or 0)
    return f"{importance_to_label(story)}；来源：{source_text}；信号强度 {score*100:.0f}%。"


def compact_title(story: dict) -> str:
    title_zh, _ = split_title(story.get("title", ""))
    return trim_text(title_zh, 52)


def build_weekly_digest(items: list[dict], period: str = "weekly") -> dict:
    period_word = "本周" if period == "weekly" else "本期"
    ranked = sorted(
        items,
        key=lambda story: (
            float(story.get("importance_score") or story.get("score") or 0),
            int(story.get("source_count") or 1),
        ),
        reverse=True,
    )
    if not ranked:
        return {"overview": "", "mainline": "", "key_points": [], "recommendations": []}

    themes = detect_weekly_themes([f"{story.get('title', '')} {story_summary(story)}" for story in items])
    theme_text = "、".join(themes[:3]) if themes else "官方产品更新和行业观察"

    overview = f"{period_word}主线集中在{theme_text}。"
    mainline = f"{period_word}主线：{theme_text}"

    key_points = []
    for story in ranked[:3]:
        key_points.append(
            {
                "title": clean_text(story.get("title")),
                "short_title": compact_title(story),
                "url": story.get("url", ""),
                "detail": story_display_detail(story),
            }
        )

    recommendations = []
    def story_key(story: dict) -> object:
        return story.get("story_id") or story.get("url") or story.get("title")

    used_ids = {story_key(story) for story in ranked[:3]}
    preferred_labels = ["官方更新", "多源热议", "行业动态", "值得关注"]
    for label in preferred_labels:
        candidates = [story for story in ranked if importance_to_label(story) == label]
        if candidates and story_key(candidates[0]) not in used_ids:
            story = candidates[0]
            recommendations.append(
                {
                    "title": clean_text(story.get("title")),
                    "short_title": compact_title(story),
                    "url": story.get("url", ""),
                    "detail": story_display_detail(story),
                    "why": human_reason(story),
                }
            )
            used_ids.add(story_key(story))
        if recommendations:
            break
    for story in ranked:
        if len(recommendations) >= 1:
            break
        if story_key(story) in used_ids:
            continue
        recommendations.append(
            {
                    "title": clean_text(story.get("title")),
                    "short_title": compact_title(story),
                    "url": story.get("url", ""),
                "detail": story_display_detail(story),
                "why": human_reason(story),
            }
        )
        used_ids.add(story_key(story))
    if not recommendations:
        story = ranked[0]
        recommendations.append(
            {
                "title": clean_text(story.get("title")),
                "short_title": compact_title(story),
                "url": story.get("url", ""),
                "detail": story_display_detail(story),
                "why": human_reason(story),
            }
        )

    return {
        "overview": overview,
        "mainline": mainline,
        "key_points": key_points,
        "recommendations": recommendations,
    }


def render_briefing(digest: dict, period: str = "weekly") -> str:
    period_word = "本周" if period == "weekly" else "本期"
    if not digest.get("overview"):
        return ""

    key_items = []
    for point in digest.get("key_points", []):
        title = clean_text(point.get("title"))
        url = escape(point.get("url", ""))
        key_items.append(
            f'<li><a href="{url}" target="_blank" rel="noopener">{escape(title)}</a></li>'
        )

    recommendation_items = []
    for item in digest.get("recommendations", []):
        title = clean_text(item.get("title"))
        url = escape(item.get("url", ""))
        why = escape(clean_text(item.get("why")))
        recommendation_items.append(
            f'<li><a href="{url}" target="_blank" rel="noopener">{escape(title)}</a>'
            f'<em>{why}</em></li>'
        )

    key_html = f'<h3>{period_word}重点</h3><ol>{"".join(key_items)}</ol>' if key_items else ""
    recommendation_html = (
        f'<h3>我的推荐</h3><ol>{"".join(recommendation_items)}</ol>'
        if recommendation_items
        else ""
    )
    return f"""
  <div class="briefing">
    <div class="briefing-label">本期导读<br>Editor's Note</div>
    <div class="briefing-body">
      <p>{escape(digest.get("overview", ""))}</p>
      {key_html}
      {recommendation_html}
    </div>
  </div>"""


def generate_html(brief: dict, title: str, subtitle: str, period: str) -> str:
    """Render the full magazine HTML."""
    items = brief.get("items", [])
    generated_at = brief.get("generated_at", "")
    date_str = fmt_date_zh(generated_at)
    weekday_zh = ""
    try:
        dt = datetime.fromisoformat(generated_at.replace("Z", "+00:00")).astimezone(SH_TZ)
        weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        weekday_zh = weekdays[dt.weekday()]
    except Exception:
        pass

    # Group stories by importance_label
    groups: dict[str, list] = {}
    for s in items:
        label = importance_to_label(s)
        groups.setdefault(label, []).append(s)

    # Order: 官方更新, 多源热议, 行业动态, then others
    ordered_labels = ["官方更新", "多源热议", "行业动态"]
    other_labels = [l for l in groups if l not in ordered_labels]
    ordered_labels = [l for l in ordered_labels if l in groups] + other_labels

    total_sources = len(set(sn for s in items for sn in s.get("source_names", [])))
    total_stories = len(items)
    digest = build_weekly_digest(items, period)

    # Build story cards HTML
    sections_html = []
    for idx, label in enumerate(ordered_labels):
        stories = groups[label]
        sec_num = f"{idx+1:02d}"
        sec_tape_en = {
            "官方更新": "OFFICIAL UPDATES",
            "多源热议": "MULTI-SOURCE BUZZ",
            "行业动态": "INDUSTRY MOVES",
        }.get(label, "SIGNALS")

        cards = []
        for s in stories:
            title_zh, title_en = split_title(s.get("title", ""))
            url = escape(s.get("url", ""))
            source_names = s.get("source_names", [])
            source_count = s.get("source_count", 1)
            earliest = fmt_time_zh(s.get("earliest_at", ""))
            score = s.get("importance_score", 0)
            score_pct = f"{score*100:.0f}"
            summary = story_summary(s)
            summary_html = f'<p class="card-summary">{escape(trim_text(summary, 260))}</p>' if summary else ""
            breakdown = s.get("importance_breakdown", {})
            ai_rel = breakdown.get("ai_relevance", 0)
            story_heat = breakdown.get("story_heat", 0)
            reasons = s.get("reasons", [])

            reason_tags = " · ".join(reasons[:3]) if reasons else ""

            source_list_html = ""
            if source_names:
                src_items = [f'<span class="src">{escape(sn)}</span>' for sn in source_names[:4]]
                source_list_html = f'<div class="src-list">{"".join(src_items)}</div>'

            en_html = f'<span class="en">{escape(title_en)}</span>' if title_en else ""

            cards.append(f"""
        <article class="story-card">
          <div class="card-head">
            <span class="card-time mono">{earliest}</span>
            <span class="card-score mono">信号强度 {score_pct}</span>
          </div>
          <h3 class="card-title"><a href="{url}" target="_blank" rel="noopener">{escape(title_zh)}</a>{en_html}</h3>
          {summary_html}
          {source_list_html}
          <div class="card-meta mono">
            <span class="src-count">{source_count} 源报道</span>
            <span class="pipe">/</span>
            <span class="ai-rel">AI 相关 {ai_rel*100:.0f}%</span>
            <span class="pipe">/</span>
            <span class="heat">热度 {story_heat*100:.0f}%</span>
            {f'<span class="pipe">/</span><span class="reasons">{escape(reason_tags)}</span>' if reason_tags else ''}
          </div>
        </article>""")

        section_desc = {
            "官方更新": "来自 OpenAI、Anthropic、GitHub、Hugging Face 等官方一手源的更新。",
            "多源热议": "被多个独立信息源同时报道的故事，热度最高。",
            "行业动态": "行业分析与产品动态。",
        }.get(label, "其他值得关注的故事。")

        sections_html.append(f"""
    <section id="sec-{sec_num}">
      <div class="sec-head">
        <div class="sec-num">{sec_num}</div>
        <div class="sec-titles">
          <div class="sec-tape"><b>{escape(label)}</b> · {sec_tape_en}</div>
          <h2 class="sec-title">{escape(label)}</h2>
          <div class="sec-deck">{section_desc}</div>
        </div>
      </div>
      <div class="story-grid">
        {''.join(cards)}
      </div>
    </section>""")

    sections_str = "\n".join(sections_html)

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{escape(title)} · {date_str}</title>
<link rel="preconnect" href="https://fonts.googleapis.com/">
<link rel="preconnect" href="https://fonts.gstatic.com/" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Albert+Sans:wght@300;400;500;600;700;800;900&family=Noto+Serif+SC:wght@400;500;700;900&family=DM+Mono:wght@300;400;500&display=swap" rel="stylesheet">
<style>
  :root{{
    --bg:#ffffff;--ink:#111111;--soft:#666666;--faint:#9a9a9a;
    --line:#e6e6e6;--line-strong:#111111;
    --sans:"Albert Sans","Noto Serif SC",sans-serif;
    --mono:"DM Mono","Noto Sans SC",monospace;
    --accent:#2563eb;
  }}
  *{{box-sizing:border-box;margin:0;padding:0}}
  html{{scroll-behavior:smooth}}
  body{{background:var(--bg);color:var(--ink);font-family:var(--sans);font-weight:400;line-height:1.9;letter-spacing:.02em;-webkit-font-smoothing:antialiased;text-rendering:optimizeLegibility}}
  .mono{{font-family:var(--mono);font-weight:400;letter-spacing:.02em}}
  a{{color:inherit;text-decoration:underline;text-decoration-color:rgba(17,17,17,.25);text-underline-offset:4px;text-decoration-thickness:1px;transition:text-decoration-color .2s}}
  a:hover{{text-decoration-color:rgba(17,17,17,1)}}
  ::selection{{background:#111;color:#fff}}

  .sheet{{max-width:1080px;margin:0 auto;padding:0 40px}}

  .topbar{{display:flex;justify-content:space-between;align-items:center;padding:24px 0 14px;border-bottom:1px solid var(--line);font-size:11px;text-transform:uppercase;letter-spacing:.22em;color:var(--soft)}}
  .topbar .left b{{font-weight:600;color:var(--ink)}}
  .topbar .dot{{display:inline-block;width:5px;height:5px;background:var(--ink);border-radius:50%;margin:0 10px;transform:translateY(-2px)}}

  .masthead{{padding:40px 0 28px;border-bottom:1px solid var(--line)}}
  .kicker{{font-size:11px;letter-spacing:.34em;text-transform:uppercase;color:var(--soft);font-weight:500;text-align:center;margin-bottom:20px}}
  .wordmark{{font-family:var(--sans);font-weight:900;font-size:clamp(30px,6.5vw,76px);line-height:1.18;letter-spacing:.03em;text-align:center;color:var(--ink)}}
  .wordmark .en{{display:block;font-weight:400;font-size:.19em;letter-spacing:.06em;color:var(--soft);margin-top:34px;line-height:1.6}}
  .mast-meta{{display:flex;justify-content:space-between;align-items:flex-end;margin-top:30px;font-size:12px;letter-spacing:.14em;text-transform:uppercase;color:var(--soft)}}
  .mast-meta .center{{text-align:center}}
  .mast-meta .big{{font-weight:500;font-size:15px;letter-spacing:.04em;text-transform:none;color:var(--ink)}}
  .tagline{{text-align:center;margin-top:36px;font-weight:400;font-size:17px;line-height:1.95;color:var(--soft);letter-spacing:.02em;max-width:60ch;margin-left:auto;margin-right:auto}}

  section{{padding:60px 0;border-bottom:1px solid var(--line)}}
  .sec-head{{display:flex;align-items:baseline;gap:22px;margin-bottom:30px}}
  .sec-num{{font-weight:300;font-size:60px;line-height:1;color:#cfcfcf}}
  .sec-titles{{flex:1}}
  .sec-tape{{font-size:11px;letter-spacing:.3em;text-transform:uppercase;color:var(--soft);font-weight:500;margin-bottom:8px}}
  .sec-tape b{{color:var(--ink);font-weight:600}}
  .sec-title{{font-weight:800;font-size:clamp(28px,4vw,46px);line-height:1.32;letter-spacing:.03em}}
  .sec-deck{{font-weight:400;color:var(--soft);font-size:18px;line-height:1.75;margin-top:10px;max-width:62ch;letter-spacing:.01em}}

  .story-grid{{display:grid;grid-template-columns:1fr;gap:0}}
  .story-card{{padding:28px 0;border-bottom:1px solid var(--line)}}
  .story-card:last-child{{border-bottom:0}}
  .card-head{{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:12px}}
  .card-time{{font-size:12px;color:var(--faint);letter-spacing:.1em}}
  .card-score{{font-size:12px;color:var(--ink);font-weight:500;letter-spacing:.06em}}
  .card-title{{font-weight:700;font-size:22px;line-height:1.4;margin-bottom:10px;letter-spacing:.02em}}
  .card-title a{{text-decoration:none;border-bottom:1px solid var(--ink)}}
  .card-title .en{{display:block;font-weight:400;font-size:14px;color:var(--faint);margin-top:4px;letter-spacing:.01em}}
  .card-summary{{font-size:15px;line-height:1.9;color:#333;margin:2px 0 12px;max-width:78ch}}
  .src-list{{margin-bottom:10px}}
  .src-list .src{{display:inline-block;font-size:12px;color:var(--soft);background:#f5f5f5;padding:3px 8px;margin-right:6px;margin-bottom:4px;border-radius:2px;letter-spacing:.02em}}
  .card-meta{{display:flex;align-items:center;gap:10px;flex-wrap:wrap;font-size:11px;color:var(--faint);letter-spacing:.02em}}
  .card-meta .pipe{{color:var(--line);margin:0 4px}}
  .card-meta .src-count{{color:var(--ink);font-weight:500}}
  .card-meta .ai-rel{{color:var(--accent)}}
  .card-meta .reasons{{color:var(--soft)}}

  .briefing{{display:grid;grid-template-columns:150px 1fr;gap:36px;align-items:start;padding:44px 0 44px;border-bottom:1px solid var(--line)}}
  .briefing-label{{font-size:11px;letter-spacing:.26em;text-transform:uppercase;color:var(--ink);border-top:1px solid var(--ink);padding-top:10px;font-weight:600}}
  .briefing-body>p{{font-size:17px;line-height:1.95;max-width:72ch;color:var(--ink)}}
  .briefing-body h3{{font-size:13px;letter-spacing:.16em;text-transform:uppercase;color:var(--soft);margin:28px 0 12px}}
  .briefing-body ol{{padding-left:22px}}
  .briefing-body li{{font-size:15px;line-height:1.85;margin-bottom:10px;color:#333;max-width:82ch}}
  .briefing-body li em{{display:block;font-style:normal;color:var(--soft);font-size:14px;margin-top:2px}}
  .briefing-body .conclusion{{margin-top:26px;padding-top:16px;border-top:1px solid var(--line);font-size:16px}}

  .colophon{{padding:48px 0 72px;text-align:center}}
  .colophon p{{font-size:13px;line-height:1.95;color:var(--soft);max-width:52ch;margin:0 auto}}
  .colophon .fine{{margin-top:16px;font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--faint)}}

  @media(max-width:760px){{
    .sheet{{padding:0 22px}}
    .mast-meta{{flex-direction:column;gap:10px;text-align:center}}
    .mast-meta .center{{order:-1}}
    .card-head{{flex-direction:column;gap:4px}}
  }}
</style>
</head>
<body>
<div class="sheet">

  <div class="topbar">
    <div class="left mono"><b>{escape(title.upper())}</b><span class="dot"></span>{escape(subtitle)}</div>
    <div class="right mono">本周刊 · {date_str} {weekday_zh}</div>
  </div>

  <header class="masthead">
    <div class="kicker">{escape(title.upper())} · {escape(subtitle)}</div>
    <h1 class="wordmark">{escape(title)}<span class="en">{escape(subtitle)}</span></h1>
    <div class="tagline">每周一期，只看真正值得关注的 AI 更新。</div>
    <div class="mast-meta mono">
      <div class="left">{total_sources} 个信息源</div>
      <div class="center"><span class="big">{date_str}</span></div>
      <div class="right">{total_stories} 条精选故事</div>
    </div>
  </header>

  {render_briefing(digest, period)}

{sections_str}

  <footer class="colophon">
    <p>本期内容由 <a href="https://github.com/LearnPrompt/ai-news-radar" target="_blank" rel="noopener">ai-news-radar</a> 管线自动抓取、合并、打分、翻译、精选生成。伯乐 Skill 从一堆信源里选出千里马。所有故事均附原帖跳转链接。</p>
    <div class="fine mono">{escape(title.upper())} · {date_str} · {escape(subtitle)}</div>
  </footer>

</div>
</body>
</html>"""
    return re.sub(r"[ \t]+$", "", html, flags=re.MULTILINE)


def main():
    parser = argparse.ArgumentParser(description="Generate magazine-style weekly briefing HTML")
    parser.add_argument("--input", default="data/daily-brief.json", help="Input daily-brief.json path")
    parser.add_argument("--output", default="data/weekly-magazine.html", help="Output HTML path")
    parser.add_argument("--title", default="AI 雷达周报", help="Magazine title")
    parser.add_argument("--subtitle", default="AI Radar Weekly", help="English subtitle")
    parser.add_argument("--period", default="weekly", choices=["weekly", "daily"], help="Period label")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: {input_path} not found", file=sys.stderr)
        sys.exit(1)

    with open(input_path, "r", encoding="utf-8") as f:
        brief = json.load(f)

    html = generate_html(brief, args.title, args.subtitle, args.period)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Generated: {output_path} ({len(html)} bytes, {len(brief.get('items', []))} stories)")


if __name__ == "__main__":
    main()

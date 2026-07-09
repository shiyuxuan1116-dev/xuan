#!/usr/bin/env python3
"""Send the weekly magazine link to user via Feishu bot after GitHub Pages deployment.

Called by GitHub Actions after the magazine HTML is deployed.
Reads the deployed URL from environment and sends it to the user.

Usage:
    python3 scripts/notify_feishu.py
    # Requires env: FEISHU_APP_ID, FEISHU_APP_SECRET, FEISHU_BOT_OPEN_ID, MAGAZINE_URL
"""

import os
import sys
import json
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta

SH_TZ = timezone(timedelta(hours=8))


def get_tenant_access_token(app_id: str, app_secret: str) -> str:
    """Get tenant_access_token from Feishu OpenAPI."""
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    data = json.dumps({"app_id": app_id, "app_secret": app_secret}).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json; charset=utf-8"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    if result.get("code") != 0:
        raise RuntimeError(f"Failed to get token: {result}")
    return result["tenant_access_token"]


def send_message(token: str, open_id: str, markdown: str) -> dict:
    """Send a markdown message to a user via Feishu bot."""
    url = "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id"
    body = {
        "receive_id": open_id,
        "msg_type": "text",
        "content": json.dumps({"text": markdown}),
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "Authorization": f"Bearer {token}",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main():
    app_id = os.environ.get("FEISHU_APP_ID", "")
    app_secret = os.environ.get("FEISHU_APP_SECRET", "")
    open_id = os.environ.get("FEISHU_BOT_OPEN_ID", "")
    magazine_url = os.environ.get("MAGAZINE_URL", "")

    if not all([app_id, app_secret, open_id, magazine_url]):
        print("Missing required environment variables", file=sys.stderr)
        print(f"  FEISHU_APP_ID: {'set' if app_id else 'missing'}", file=sys.stderr)
        print(f"  FEISHU_APP_SECRET: {'set' if app_secret else 'missing'}", file=sys.stderr)
        print(f"  FEISHU_BOT_OPEN_ID: {'set' if open_id else 'missing'}", file=sys.stderr)
        print(f"  MAGAZINE_URL: {'set' if magazine_url else 'missing'}", file=sys.stderr)
        sys.exit(1)

    now = datetime.now(SH_TZ)
    date_str = f"{now.year}年{now.month}月{now.day}日"
    weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    weekday = weekdays[now.weekday()]

    message = f"""📰 AI 雷达周报 · {date_str} {weekday}

本周 AI 更新精选已发布，点击查看：
{magazine_url}

由 ai-news-radar 自动抓取、去重、故事合并、AI 打分、翻译、精选生成。"""

    print(f"Getting tenant_access_token for app {app_id}...")
    token = get_tenant_access_token(app_id, app_secret)
    print(f"Token acquired, sending message to {open_id}...")

    result = send_message(token, open_id, message)
    if result.get("code") == 0:
        msg_id = result.get("data", {}).get("message_id", "")
        print(f"✓ Message sent successfully! message_id={msg_id}")
    else:
        print(f"✗ Send failed: {result}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

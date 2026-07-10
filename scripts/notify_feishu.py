#!/usr/bin/env python3
"""Send the weekly magazine link to user via Feishu bot after GitHub Pages deployment."""

import os, sys, json, urllib.request
from datetime import datetime, timezone, timedelta

SH_TZ = timezone(timedelta(hours=8))
FEISHU_BASE = "https://open.feishu.cn/open-apis"

def get_tenant_access_token(app_id, app_secret):
    url = f"{FEISHU_BASE}/auth/v3/tenant_access_token/internal"
    data = json.dumps({"app_id": app_id, "app_secret": app_secret}).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json; charset=utf-8"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    if result.get("code") != 0:
        raise RuntimeError(f"Failed to get token: {result}")
    return result["tenant_access_token"]

def send_message(token, open_id, text):
    url = f"{FEISHU_BASE}/im/v1/messages?receive_id_type=open_id"
    body = {"receive_id": open_id, "msg_type": "text", "content": json.dumps({"text": text})}
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json; charset=utf-8", "Authorization": f"Bearer {token}"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))

def main():
    app_id = os.environ.get("FEISHU_APP_ID", "")
    app_secret = os.environ.get("FEISHU_APP_SECRET", "")
    open_id = os.environ.get("FEISHU_BOT_OPEN_ID", "")
    magazine_url = os.environ.get("MAGAZINE_URL", "https://shiyuxuan1116-dev.github.io/xuan/")

    if not all([app_id, app_secret, open_id]):
        print("Missing env vars", file=sys.stderr)
        sys.exit(1)

    now = datetime.now(SH_TZ)
    date_str = f"{now.year}年{now.month}月{now.day}日"
    weekdays = ["周一","周二","周三","周四","周五","周六","周日"]
    weekday = weekdays[now.weekday()]

    message = f"📰 AI 雷达周报 · {date_str} {weekday}\n\n本周 AI 更新精选已发布，点击查看：\n{magazine_url}\n\n由 ai-news-radar 自动抓取、去重、故事合并、AI 打分、翻译、精选生成。"

    print(f"Getting token for {app_id}...")
    token = get_tenant_access_token(app_id, app_secret)
    print(f"Sending link to {open_id}...")
    result = send_message(token, open_id, message)
    if result.get("code") == 0:
        print(f"✓ Message sent! message_id={result.get('data',{}).get('message_id','')}")
    else:
        print(f"✗ Failed: {result}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()

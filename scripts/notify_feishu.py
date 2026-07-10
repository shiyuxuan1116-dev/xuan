#!/usr/bin/env python3
"""Send the weekly magazine HTML file to user via Feishu bot.

Called by GitHub Actions after the magazine HTML is generated.
Uploads the HTML file to Feishu, then sends it as a file message.

Usage:
    python3 scripts/notify_feishu.py
    # Requires env: FEISHU_APP_ID, FEISHU_APP_SECRET, FEISHU_BOT_OPEN_ID, MAGAZINE_HTML_PATH
"""

import os
import sys
import json
import uuid
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta

SH_TZ = timezone(timedelta(hours=8))
FEISHU_BASE = "https://open.feishu.cn/open-apis"


def get_tenant_access_token(app_id: str, app_secret: str) -> str:
    """Get tenant_access_token from Feishu OpenAPI."""
    url = f"{FEISHU_BASE}/auth/v3/tenant_access_token/internal"
    data = json.dumps({"app_id": app_id, "app_secret": app_secret}).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json; charset=utf-8"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    if result.get("code") != 0:
        raise RuntimeError(f"Failed to get token: {result}")
    return result["tenant_access_token"]


def upload_file(token: str, file_path: str, file_name: str) -> str:
    """Upload a file to Feishu and return the file_key."""
    url = f"{FEISHU_BASE}/im/v1/files"
    boundary = "----FormBoundary" + uuid.uuid4().hex[:16]

    with open(file_path, "rb") as f:
        file_data = f.read()

    body = b"--" + boundary.encode() + b"\r\n"
    body += b'Content-Disposition: form-data; name="file_type"\r\n\r\n'
    body += b"stream\r\n"
    body += b"--" + boundary.encode() + b"\r\n"
    body += b'Content-Disposition: form-data; name="file_name"\r\n\r\n'
    body += file_name.encode() + b"\r\n"
    body += b"--" + boundary.encode() + b"\r\n"
    body += b'Content-Disposition: form-data; name="file"; filename="'
    body += file_name.encode() + b'"\r\n'
    body += b"Content-Type: application/octet-stream\r\n\r\n"
    body += file_data + b"\r\n"
    body += b"--" + boundary.encode() + b"--\r\n"

    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    if result.get("code") != 0:
        raise RuntimeError(f"File upload failed: {result}")
    return result["data"]["file_key"]


def send_file_message(token: str, open_id: str, file_key: str) -> dict:
    """Send a file message to a user via Feishu bot."""
    url = f"{FEISHU_BASE}/im/v1/messages?receive_id_type=open_id"
    body = {
        "receive_id": open_id,
        "msg_type": "file",
        "content": json.dumps({"file_key": file_key}),
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def send_text_message(token: str, open_id: str, text: str) -> dict:
    """Send a text message to a user via Feishu bot."""
    url = f"{FEISHU_BASE}/im/v1/messages?receive_id_type=open_id"
    body = {
        "receive_id": open_id,
        "msg_type": "text",
        "content": json.dumps({"text": text}),
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main():
    app_id = os.environ.get("FEISHU_APP_ID", "")
    app_secret = os.environ.get("FEISHU_APP_SECRET", "")
    open_id = os.environ.get("FEISHU_BOT_OPEN_ID", "")
    html_path = os.environ.get("MAGAZINE_HTML_PATH", "data/weekly-magazine.html")

    if not all([app_id, app_secret, open_id]):
        print("Missing required environment variables", file=sys.stderr)
        sys.exit(1)

    if not os.path.exists(html_path):
        print(f"HTML file not found: {html_path}", file=sys.stderr)
        sys.exit(1)

    now = datetime.now(SH_TZ)
    date_str = f"{now.year}年{now.month}月{now.day}日"
    weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    weekday = weekdays[now.weekday()]
    file_name = f"AI_Radar_Weekly_{now.year}{now.month:02d}{now.day:02d}.html"

    print(f"Getting tenant_access_token for app {app_id}...")
    token = get_tenant_access_token(app_id, app_secret)
    print(f"Token acquired, uploading {html_path} as {file_name}...")

    file_key = upload_file(token, html_path, file_name)
    print(f"File uploaded, file_key={file_key}")

    # 先发文字消息
    text_msg = f"📰 AI 雷达周报 · {date_str} {weekday}\n\n本期由 ai-news-radar 自动抓取、去重、故事合并、AI 打分、翻译、精选生成。杂志 HTML 文件见下方附件，下载后用浏览器打开即可阅读。"
    text_result = send_text_message(token, open_id, text_msg)
    if text_result.get("code") == 0:
        print(f"✓ Text message sent")
    else:
        print(f"✗ Text message failed: {text_result}", file=sys.stderr)

    # 再发文件
    file_result = send_file_message(token, open_id, file_key)
    if file_result.get("code") == 0:
        msg_id = file_result.get("data", {}).get("message_id", "")
        print(f"✓ File message sent! message_id={msg_id}")
    else:
        print(f"✗ File message failed: {file_result}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

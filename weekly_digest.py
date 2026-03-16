"""
Knowledge Digest.

Pulls recent captures from Google Sheets, summarizes them via Groq,
generates an HTML report, and sends it as a file via Telegram.
"""

import os
import httpx
import tempfile
from datetime import datetime
from dotenv import load_dotenv

from storage import get_captures_since

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
USER_ID = os.getenv("TELEGRAM_USER_ID")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = "llama-3.3-70b-versatile"
DIGEST_DAYS = int(os.getenv("DIGEST_DAYS", "7"))


def build_digest_prompt(captures: list[dict]) -> str:
    entries = []
    for i, c in enumerate(captures, 1):
        parts = [f"#{i} [{c.get('type', '?')}] — {c.get('timestamp', '?')}"]
        raw = c.get("raw_text", "").strip()
        extracted = c.get("extracted_text", "").strip()
        url = c.get("source_url", "").strip()
        tags = c.get("tags", "").strip()
        if raw:
            parts.append(f"  Content: {raw}")
        if extracted and extracted != raw:
            parts.append(f"  Extracted: {extracted}")
        if url:
            parts.append(f"  URL: {url}")
        if tags:
            parts.append(f"  Tags: {tags}")
        entries.append("\n".join(parts))

    captures_text = "\n\n".join(entries)

    return f"""You are a personal knowledge assistant. The user has captured the following items recently.

For each capture, write a brief, honest summary of what it is and what it's about — based only on the information provided.
If a capture doesn't contain enough context to say much, just say so plainly. Do not invent context, force insights, or speculate about why it was saved.
Go through each capture one by one. No themes, no cross-connections, no questions.

Here are the {len(captures)} captures:

---
{captures_text}
---

For each one, write 2-4 sentences max. Be direct and honest. If you don't have enough information, say "Not enough context to summarize."
"""


def call_groq(prompt: str) -> str:
    response = httpx.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": GROQ_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 2000,
        },
        timeout=60,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def build_html(captures: list[dict], digest: str, days: int) -> str:
    date_str = datetime.now().strftime("%B %d, %Y")

    # Convert digest text to simple HTML paragraphs
    digest_html = ""
    for line in digest.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        if line.startswith("#"):
            digest_html += f"<h3>{line.lstrip('#').strip()}</h3>\n"
        else:
            digest_html += f"<p>{line}</p>\n"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Knowledge Digest — {date_str}</title>
  <style>
    body {{
      font-family: Georgia, serif;
      max-width: 720px;
      margin: 48px auto;
      padding: 0 24px;
      color: #1a1a1a;
      line-height: 1.7;
      background: #fafaf8;
    }}
    header {{
      border-bottom: 2px solid #e0e0e0;
      padding-bottom: 16px;
      margin-bottom: 32px;
    }}
    h1 {{ font-size: 1.6rem; margin: 0 0 4px; }}
    .meta {{ color: #666; font-size: 0.9rem; }}
    h2 {{ font-size: 1.15rem; margin-top: 40px; color: #333; }}
    h3 {{ font-size: 1rem; color: #444; margin-top: 24px; }}
    p {{ margin: 8px 0; }}
    .capture {{
      background: #fff;
      border: 1px solid #e8e8e8;
      border-radius: 8px;
      padding: 16px 20px;
      margin-bottom: 16px;
    }}
    .capture-meta {{ font-size: 0.8rem; color: #888; margin-bottom: 6px; }}
    .capture-content {{ font-size: 0.95rem; }}
    .tag {{
      display: inline-block;
      background: #f0f0f0;
      border-radius: 4px;
      padding: 2px 8px;
      font-size: 0.75rem;
      color: #555;
      margin-right: 4px;
    }}
  </style>
</head>
<body>
  <header>
    <h1>Knowledge Digest</h1>
    <div class="meta">{date_str} &nbsp;·&nbsp; {len(captures)} captures from the last {days} days</div>
  </header>

  <h2>Summary</h2>
  {digest_html}

  <h2>Captures</h2>
  {"".join(_capture_card(c) for c in captures)}
</body>
</html>"""


def _capture_card(c: dict) -> str:
    ctype = c.get("type", "?")
    ts = c.get("timestamp", "")
    raw = c.get("raw_text", "").strip()
    extracted = c.get("extracted_text", "").strip()
    url = c.get("source_url", "").strip()
    tags = c.get("tags", "").strip()

    content = extracted or raw or "<em>No content</em>"
    if len(content) > 400:
        content = content[:400] + "…"

    url_html = f'<div><a href="{url}" target="_blank">{url}</a></div>' if url else ""
    tags_html = "".join(f'<span class="tag">{t.strip()}</span>' for t in tags.split(",") if t.strip()) if tags else ""

    return f"""  <div class="capture">
    <div class="capture-meta">{ctype.upper()} &nbsp;·&nbsp; {ts} {tags_html}</div>
    <div class="capture-content">{content}</div>
    {url_html}
  </div>
"""


def send_telegram_file(path: str, caption: str):
    with open(path, "rb") as f:
        httpx.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument",
            data={"chat_id": USER_ID, "caption": caption},
            files={"document": ("digest.html", f, "text/html")},
            timeout=15,
        )


def send_telegram_message(text: str):
    httpx.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json={"chat_id": USER_ID, "text": text},
        timeout=10,
    )


def main():
    print(f"Fetching captures from the last {DIGEST_DAYS} days...")
    captures = get_captures_since(days=DIGEST_DAYS)

    if not captures:
        msg = f"No knowledge captures in the last {DIGEST_DAYS} days."
        if BOT_TOKEN and USER_ID:
            send_telegram_message(msg)
        print(msg)
        return

    print(f"Found {len(captures)} captures. Generating digest...")
    prompt = build_digest_prompt(captures)
    digest = call_groq(prompt)

    html = build_html(captures, digest, DIGEST_DAYS)

    with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w") as f:
        f.write(html)
        tmp_path = f.name

    date_str = datetime.now().strftime("%B %d, %Y")
    caption = f"Knowledge Digest — {date_str} ({len(captures)} captures)"

    if BOT_TOKEN and USER_ID:
        print("Sending digest via Telegram...")
        send_telegram_file(tmp_path, caption)
        print("Sent!")
    else:
        print(f"No Telegram config. HTML saved to: {tmp_path}")

    os.unlink(tmp_path)
    print(digest)


if __name__ == "__main__":
    main()

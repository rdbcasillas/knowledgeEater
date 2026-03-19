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

TYPE_ICON = {
    "link": "🔗",
    "image": "📷",
    "text": "📝",
    "voice": "🎤",
    "document": "📄",
    "forwarded": "↩️",
}


def fmt_timestamp(ts: str) -> str:
    try:
        dt = datetime.fromisoformat(ts)
        return dt.strftime("%b %d, %I:%M %p")
    except Exception:
        return ts


def build_digest_prompt(captures: list[dict]) -> str:
    entries = []
    for i, c in enumerate(captures, 1):
        parts = [f"CAPTURE {i} [{c.get('type', '?').upper()}]"]
        raw = c.get("raw_text", "").strip()
        extracted = c.get("extracted_text", "").strip()
        url = c.get("source_url", "").strip()
        if raw:
            parts.append(f"Content: {raw[:800]}")
        if extracted and extracted != raw:
            parts.append(f"Extracted: {extracted[:800]}")
        if url:
            parts.append(f"URL: {url}")
        entries.append("\n".join(parts))

    captures_text = "\n\n---\n\n".join(entries)

    return f"""You are summarizing a personal knowledge capture log. The user saves links, book excerpts, screenshots, and notes for later review.

For each capture below, write a short, honest summary. Format each one exactly like this:

CAPTURE 1
<2-3 plain sentences describing what this is and what it's about. No bullet points, no headers. Just prose.>

CAPTURE 2
<summary>

...and so on.

Rules:
- Only use information that is actually present in the capture. Do not invent or infer.
- If there isn't enough information, write: "Not enough context to summarize."
- Do not editorialize, find connections, or add opinions.
- Keep each summary to 2-3 sentences maximum.

Here are the {len(captures)} captures:

{captures_text}
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


def parse_summaries(digest: str, count: int) -> list[str]:
    """Parse the LLM output into a list of per-capture summaries."""
    summaries = [""] * count
    current = None
    buffer = []

    for line in digest.strip().split("\n"):
        stripped = line.strip()
        if stripped.upper().startswith("CAPTURE "):
            if current is not None and current <= count:
                summaries[current - 1] = " ".join(buffer).strip()
            try:
                current = int(stripped.split()[1])
                buffer = []
            except (IndexError, ValueError):
                pass
        elif current is not None and stripped:
            buffer.append(stripped)

    if current is not None and current <= count:
        summaries[current - 1] = " ".join(buffer).strip()

    return summaries


def build_html(captures: list[dict], digest: str, days: int) -> str:
    date_str = datetime.now().strftime("%B %d, %Y")
    summaries = parse_summaries(digest, len(captures))

    cards = "".join(_capture_card(c, summaries[i]) for i, c in enumerate(captures))

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Knowledge Digest — {date_str}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Lora:ital,wght@0,400;0,600;1,400&display=swap" rel="stylesheet">
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: 'Inter', sans-serif;
      background: #f4f1eb;
      color: #1a1a1a;
      padding: 40px 20px 80px;
    }}
    .page {{
      max-width: 680px;
      margin: 0 auto;
    }}
    header {{
      margin-bottom: 40px;
    }}
    .header-label {{
      font-size: 0.7rem;
      font-weight: 600;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: #888;
      margin-bottom: 6px;
    }}
    h1 {{
      font-family: 'Lora', serif;
      font-size: 2rem;
      font-weight: 600;
      color: #111;
      line-height: 1.2;
    }}
    .header-meta {{
      margin-top: 10px;
      font-size: 0.85rem;
      color: #888;
    }}
    .divider {{
      height: 1px;
      background: #ddd;
      margin: 32px 0;
    }}
    .card {{
      background: #fff;
      border-radius: 12px;
      padding: 20px 24px;
      margin-bottom: 16px;
      border: 1px solid #e4e0d8;
    }}
    .card-header {{
      display: flex;
      align-items: center;
      gap: 10px;
      margin-bottom: 12px;
    }}
    .type-badge {{
      font-size: 0.7rem;
      font-weight: 600;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      padding: 3px 8px;
      border-radius: 4px;
    }}
    .badge-link    {{ background: #e8f0fe; color: #3b5bdb; }}
    .badge-image   {{ background: #e6fcf5; color: #0ca678; }}
    .badge-text    {{ background: #fff9db; color: #e67700; }}
    .badge-voice   {{ background: #f3f0ff; color: #7048e8; }}
    .badge-document {{ background: #fff0f6; color: #c2255c; }}
    .badge-forwarded {{ background: #f1f3f5; color: #495057; }}
    .card-time {{
      font-size: 0.75rem;
      color: #aaa;
      margin-left: auto;
    }}
    .card-summary {{
      font-family: 'Lora', serif;
      font-size: 1rem;
      line-height: 1.7;
      color: #222;
    }}
    .card-url {{
      margin-top: 12px;
      font-size: 0.78rem;
    }}
    .card-url a {{
      color: #3b5bdb;
      text-decoration: none;
      word-break: break-all;
    }}
    .card-url a:hover {{ text-decoration: underline; }}
    .no-summary {{ color: #aaa; font-style: italic; font-size: 0.9rem; }}
    .card-image {{ margin-top: 12px; }}
    .card-image img {{ max-width: 100%; border-radius: 8px; border: 1px solid #e4e0d8; }}
  </style>
</head>
<body>
  <div class="page">
    <header>
      <div class="header-label">Knowledge Digest</div>
      <h1>{date_str}</h1>
      <div class="header-meta">{len(captures)} captures from the last {days} days</div>
    </header>

    <div class="divider"></div>

    {cards}
  </div>
</body>
</html>"""


def _capture_card(c: dict, summary: str) -> str:
    ctype = c.get("type", "text").lower()
    icon = TYPE_ICON.get(ctype, "📎")
    ts = fmt_timestamp(c.get("timestamp", ""))
    url = c.get("source_url", "").strip()

    badge_class = f"badge-{ctype}" if ctype in ("link", "image", "text", "voice", "document", "forwarded") else "badge-text"

    summary_html = (
        f'<div class="card-summary">{summary}</div>'
        if summary
        else '<div class="no-summary">Not enough context to summarize.</div>'
    )

    if url and "drive.google.com/uc" in url:
        url_html = f'<div class="card-image"><img src="{url}" alt="captured image"></div>'
    elif url:
        url_html = f'<div class="card-url"><a href="{url}" target="_blank">{url}</a></div>'
    else:
        url_html = ""

    return f"""    <div class="card">
      <div class="card-header">
        <span class="type-badge {badge_class}">{icon} {ctype}</span>
        <span class="card-time">{ts}</span>
      </div>
      {summary_html}
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

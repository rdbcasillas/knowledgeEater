"""
Text extraction utilities: OCR for images, basic link extraction.
"""

import os
import re
import subprocess
import httpx
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = "llama-3.3-70b-versatile"


def ocr_from_image(image_path: str) -> str:
    """Extract text from an image using Tesseract OCR."""
    try:
        import pytesseract
        from PIL import Image

        img = Image.open(image_path)
        text = pytesseract.image_to_string(img)
        return text.strip()
    except ImportError:
        # Fallback: try calling tesseract directly
        try:
            result = subprocess.run(
                ["tesseract", image_path, "stdout"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            return result.stdout.strip()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return "[OCR unavailable — install tesseract]"


def extract_urls(text: str) -> list[str]:
    """Pull URLs out of a text message."""
    url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
    return re.findall(url_pattern, text)


def fetch_page_title(url: str) -> str:
    """Try to get the <title> of a web page. Fails gracefully."""
    try:
        resp = httpx.get(url, follow_redirects=True, timeout=10)
        match = re.search(r"<title[^>]*>(.*?)</title>", resp.text, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip()
    except Exception:
        pass
    return ""


def fetch_article_text(url: str) -> str:
    """Fetch a page and return stripped readable text."""
    try:
        resp = httpx.get(url, follow_redirects=True, timeout=10, headers={
            "User-Agent": "Mozilla/5.0"
        })
        html = resp.text
        # Remove script and style blocks
        html = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
        # Strip all tags
        text = re.sub(r"<[^>]+>", " ", html)
        # Clean up whitespace
        text = re.sub(r"\s+", " ", text).strip()
        return text[:5000]
    except Exception:
        return ""


def summarize_url(url: str) -> str:
    """Fetch article content and summarize it via Groq."""
    if not GROQ_API_KEY:
        return fetch_page_title(url)

    text = fetch_article_text(url)
    if not text:
        return fetch_page_title(url)

    try:
        response = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": GROQ_MODEL,
                "messages": [{"role": "user", "content": (
                    f"Summarize this article in 2-3 sentences. Be direct and factual. "
                    f"Only use what's in the text — don't add context or opinions.\n\n{text}"
                )}],
                "max_tokens": 200,
            },
            timeout=30,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()
    except Exception:
        return fetch_page_title(url)

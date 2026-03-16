"""
Text extraction utilities: OCR for images, basic link extraction.
"""

import re
import subprocess


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
        import httpx

        resp = httpx.get(url, follow_redirects=True, timeout=10)
        match = re.search(r"<title[^>]*>(.*?)</title>", resp.text, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip()
    except Exception:
        pass
    return ""

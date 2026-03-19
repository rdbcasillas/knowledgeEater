"""
Knowledge Capture Telegram Bot.

Send it anything — text, photos, links, voice notes — and it stores
everything in a Google Sheet for later processing.
"""

import os
import logging
import tempfile
from datetime import datetime
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from storage import save_capture, upload_to_drive
from extractors import ocr_from_image, extract_urls, fetch_page_title, summarize_url

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ALLOWED_USER_ID = int(os.getenv("TELEGRAM_USER_ID", "0"))


# --- Auth ---

def authorized(func):
    """Only allow the configured user."""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id != ALLOWED_USER_ID:
            await update.message.reply_text("Not authorized.")
            return
        return await func(update, context)
    return wrapper


# --- Handlers ---

@authorized
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Knowledge bot ready. Send me anything:\n"
        "• Text snippets or quotes\n"
        "• Photos of book pages\n"
        "• Links\n"
        "• Voice notes\n"
        "• Screenshots\n\n"
        "I'll capture everything. Use /stats to see counts."
    )


@authorized
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    urls = extract_urls(text)

    if urls:
        url = urls[0]
        # Strip the URL from the text to get surrounding content
        surrounding = text.replace(url, "").strip()

        if len(surrounding) > 50:
            # Paragraph + link — the text is the insight, link is just the source
            save_capture(
                capture_type="text",
                raw_text=surrounding,
                source_url=url,
            )
            await update.message.reply_text("📝 Captured note with source link.")
        else:
            # Just a link — fetch and summarize
            await update.message.reply_text("🔗 Fetching and summarizing...")
            summary = summarize_url(url)
            save_capture(
                capture_type="link",
                raw_text=text,
                extracted_text=summary,
                source_url=url,
            )
            await update.message.reply_text(f"🔗 Captured.\n\n{summary}")
    else:
        # Plain text / quote / thought
        save_capture(capture_type="text", raw_text=text)
        if len(text) > 200:
            await update.message.reply_text("📝 Captured long note.")
        else:
            await update.message.reply_text("📝 Captured.")


@authorized
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle photos — book pages, screenshots, diagrams."""
    photo = update.message.photo[-1]  # highest resolution
    caption = update.message.caption or ""

    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        file = await context.bot.get_file(photo.file_id)
        await file.download_to_drive(tmp.name)
        extracted = ocr_from_image(tmp.name)
        filename = f"capture_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        drive_url = upload_to_drive(tmp.name, filename)
        os.unlink(tmp.name)

    save_capture(
        capture_type="image",
        raw_text=caption,
        extracted_text=extracted,
        source_url=drive_url,
    )

    if extracted and len(extracted) > 20:
        preview = extracted[:100] + "..." if len(extracted) > 100 else extracted
        await update.message.reply_text(f"📷 Captured image. Extracted:\n\n{preview}")
    else:
        await update.message.reply_text("📷 Captured image (couldn't extract much text).")


@authorized
async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle document files (PDFs, etc.)."""
    doc = update.message.document
    caption = update.message.caption or ""

    save_capture(
        capture_type="document",
        raw_text=f"{doc.file_name} | {caption}",
        extracted_text=f"[Document: {doc.file_name}, {doc.file_size} bytes]",
    )
    await update.message.reply_text(f"📄 Captured document: {doc.file_name}")


@authorized
async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle voice notes — stores metadata, transcription can be added later."""
    voice = update.message.voice
    duration = voice.duration

    save_capture(
        capture_type="voice",
        raw_text=f"[Voice note: {duration}s]",
        extracted_text="[transcription not yet implemented]",
    )
    await update.message.reply_text(f"🎤 Captured voice note ({duration}s). Transcription coming in a future update.")


@authorized
async def handle_forwarded(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle forwarded messages."""
    text = update.message.text or update.message.caption or ""
    forward_from = ""
    if update.message.forward_origin:
        forward_from = str(update.message.forward_origin)

    save_capture(
        capture_type="forwarded",
        raw_text=text,
        extracted_text=f"[Forwarded] {forward_from}",
    )
    await update.message.reply_text("↩️ Captured forwarded message.")


@authorized
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show capture stats for the current week."""
    from storage import get_captures_since

    captures = get_captures_since(days=7)
    if not captures:
        await update.message.reply_text("No captures this week yet.")
        return

    type_counts = {}
    for c in captures:
        t = c.get("type", "unknown")
        type_counts[t] = type_counts.get(t, 0) + 1

    lines = [f"This week: {len(captures)} captures"]
    for t, count in sorted(type_counts.items()):
        lines.append(f"  • {t}: {count}")

    await update.message.reply_text("\n".join(lines))


@authorized
async def tag_last(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tag the most recent capture. Usage: /tag rationality, epistemics"""
    from storage import get_sheet

    args = update.message.text.replace("/tag", "").strip()
    if not args:
        await update.message.reply_text("Usage: /tag your, tags, here")
        return

    sheet = get_sheet()
    all_rows = sheet.get_all_values()
    if len(all_rows) <= 1:
        await update.message.reply_text("No captures to tag.")
        return

    # Update the last row's tags column (column 6)
    last_row = len(all_rows)
    sheet.update_cell(last_row, 6, args)
    await update.message.reply_text(f"🏷️ Tagged last capture: {args}")


# --- Main ---

def main():
    if not BOT_TOKEN:
        print("ERROR: Set TELEGRAM_BOT_TOKEN in .env")
        return
    if ALLOWED_USER_ID == 0:
        print("ERROR: Set TELEGRAM_USER_ID in .env")
        return

    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("tag", tag_last))

    # Forwarded messages first (before general text handler)
    app.add_handler(MessageHandler(filters.FORWARDED, handle_forwarded))

    # Content handlers
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    logger.info("Bot starting...")
    app.run_polling()


if __name__ == "__main__":
    main()

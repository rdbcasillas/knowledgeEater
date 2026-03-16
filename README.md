# Knowledge Capture Bot

A Telegram bot that captures everything you send it (text, images, screenshots, links, voice notes) and stores it in a Google Sheet. A weekly digest script processes everything via Claude API and sends you a summary.

## Architecture

```
You → Telegram Bot → Google Sheet (raw storage)
                          ↓
              Weekly Digest Script (Claude API)
                          ↓
              Telegram message / Email to you
```

## Setup

### 1. Create the Telegram Bot

1. Open Telegram, search for `@BotFather`
2. Send `/newbot`
3. Choose a name (e.g., "My Knowledge Bot")
4. Choose a username (e.g., `zt_knowledge_bot`)
5. BotFather gives you a **token** like `7123456789:AAH...` — copy it

### 2. Get Your Telegram User ID

1. Search for `@userinfobot` on Telegram
2. Send it any message
3. It replies with your user ID (a number like `123456789`) — copy it
4. This is used to restrict the bot so only YOU can use it

### 3. Set Up Google Sheets API

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (e.g., "Knowledge Bot")
3. Enable **Google Sheets API** and **Google Drive API**:
   - Go to APIs & Services → Library
   - Search "Google Sheets API" → Enable
   - Search "Google Drive API" → Enable
4. Create a Service Account:
   - Go to APIs & Services → Credentials
   - Click "Create Credentials" → "Service Account"
   - Name it anything (e.g., "knowledge-bot")
   - Click through (no extra permissions needed)
   - Click on the created service account
   - Go to "Keys" tab → "Add Key" → "Create New Key" → JSON
   - Download the JSON file → rename to `credentials.json`
   - Place it in this project folder
5. Create a Google Sheet:
   - Create a new Google Sheet
   - Name the first sheet tab `captures`
   - Add these headers in row 1: `timestamp | type | raw_text | extracted_text | source_url | tags`
   - **Share the sheet** with the service account email (found in credentials.json as `client_email`, looks like `something@project.iam.gserviceaccount.com`) — give it **Editor** access
   - Copy the **Sheet ID** from the URL: `https://docs.google.com/spreadsheets/d/THIS_PART_HERE/edit`

### 4. Get Claude API Key (for weekly digest)

1. Go to [console.anthropic.com](https://console.anthropic.com/)
2. Create an API key
3. Copy it

### 5. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` and fill in your values.

### 6. Install Dependencies

```bash
pip install python-telegram-bot gspread google-auth httpx python-dotenv Pillow
```

For OCR (reading text from book photos), also install Tesseract:

```bash
# Ubuntu/Debian
sudo apt install tesseract-ocr

# macOS
brew install tesseract

# Then install the Python wrapper
pip install pytesseract
```

### 7. Run the Bot

```bash
python bot.py
```

For the weekly digest (run manually or via cron):

```bash
python weekly_digest.py
```

### 8. Set Up Weekly Cron (Optional)

```bash
crontab -e
```

Add this line to run every Sunday at 9 AM:

```
0 9 * * 0 cd /path/to/knowledge-bot && python weekly_digest.py
```

## Usage

Just send stuff to your bot:

- **Text**: Any text snippet, quote, thought
- **Photo**: Picture of a book page, whiteboard, diagram
- **Link**: Any URL — bot will try to extract the page title
- **Voice note**: Bot will note it (transcription can be added later)
- **Screenshot**: Same as photo — OCR extracts text

The bot confirms each capture with a short acknowledgment.

Every week, the digest script reads your captures, sends them to Claude for analysis, and messages you a summary with themes, connections, and callbacks.

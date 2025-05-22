# Telegram Video Downloader Bot

This Telegram bot can download videos from YouTube and Instagram reels.

## Features

- Download YouTube videos
- Download Instagram reels
- Simple and easy to use interface
- Automatic video quality selection

## Setup

1. Install the required dependencies:
```bash
pip install -r requirements.txt
pip install --upgrade instaloader
```

2. Create a Telegram bot:
   - Open Telegram and search for "@BotFather"
   - Send `/newbot` command
   - Follow the instructions to create your bot
   - Copy the API token provided by BotFather

3. Configure the bot:
   - Open `config.py`
   - Replace `"your_bot_token_here"` with your actual bot token from BotFather

4. Run the bot:
```bash
python bot.py
```

## Usage

1. Start a chat with your bot on Telegram
2. Send `/start` to see the welcome message
3. Send a YouTube or Instagram link to download the video
4. The bot will process the video and send it back to you

## Commands

- `/start` - Show welcome message
- `/help` - Show help message

## Notes

- Make sure the YouTube videos and Instagram reels are public and accessible
- The bot will download the highest quality available for YouTube videos
- For Instagram reels, the original quality will be maintained
- Downloaded files are automatically deleted after sending to maintain privacy 
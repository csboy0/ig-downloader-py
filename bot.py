import os
import logging
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
import instaloader
from config import TELEGRAM_BOT_TOKEN
import json
import requests
import time
import yt_dlp

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize Instagram loader
L = instaloader.Instaloader()

def get_video_info(url):
    """Get video information using yt-dlp."""
    try:
        # Configure yt-dlp options with minimal settings
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'format': 'best',
            'nocheckcertificate': True,
            'ignoreerrors': True,
            'geo_bypass': True,
            'extract_flat': False,
            'no_playlist': True,
        }
        
        logger.info(f"Attempting to get info for URL: {url}")
        
        # Try up to 3 times with different configurations
        for attempt in range(3):
            try:
                logger.info(f"Attempt {attempt + 1} to get video info")
                
                # Modify options based on attempt
                if attempt == 1:
                    ydl_opts['format'] = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
                elif attempt == 2:
                    ydl_opts['format'] = 'best'
                    ydl_opts['extract_flat'] = True
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    
                    if not info:
                        raise Exception("Could not extract video information")
                    
                    logger.info(f"Successfully extracted info on attempt {attempt + 1}")
                    
                    return {
                        'title': info.get('title', 'Unknown Title'),
                        'length': info.get('duration', 0),
                        'author': info.get('uploader', 'Unknown Author'),
                        'views': info.get('view_count', 0),
                        'video_id': info.get('id', '')
                    }
                    
            except Exception as e:
                logger.error(f"Attempt {attempt + 1} failed: {str(e)}")
                if attempt < 2:  # If not the last attempt
                    time.sleep(2)  # Wait before retrying
                    continue
                raise  # Re-raise the exception if all attempts failed
                
    except Exception as e:
        logger.error(f"Error getting video info: {str(e)}")
        import traceback
        logger.error(f"Full error traceback: {traceback.format_exc()}")
        return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /start is issued."""
    await update.message.reply_text(
        '🎉 *Welcome to the Media Downloader Bot!* 🎉\n\n'
        'I can help you download content from YouTube and Instagram.\n\n'
        '📥 *Supported Content:*\n'
        '• 🎥 YouTube videos\n'
        '• 📱 YouTube Shorts\n'
        '• 🎵 YouTube audio (as MP3)\n'
        '• 📸 Instagram posts (photos)\n'
        '• 🎬 Instagram reels\n'
        '• 🎥 Instagram videos\n\n'
        'Just send me a link, and I\'ll download it for you!\n\n'
        '📋 *Commands:*\n'
        '• /start - Show this message\n'
        '• /help - Show help message\n'
        '• /audio - Download YouTube video as audio',
        parse_mode='Markdown'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /help is issued."""
    await update.message.reply_text(
        '📥 *How to Download Content:*\n\n'
        '1️⃣ Send a YouTube video/shorts link to download the video\n'
        '2️⃣ Send an Instagram post/reel link to download the content\n'
        '3️⃣ Use /audio command followed by YouTube link to download as MP3\n\n'
        '⚠️ *Note:* Make sure the content is public and accessible.',
        parse_mode='Markdown'
    )

async def audio_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /audio command."""
    if not context.args:
        await update.message.reply_text(
            "🎵 *Audio Download*\n\n"
            "Please provide a YouTube URL after the /audio command.\n"
            "Example: `/audio https://www.youtube.com/watch?v=...`",
            parse_mode='Markdown'
        )
        return
    
    url = context.args[0]
    if not re.match(r'^(https?://)?(www\.)?(youtube\.com|youtu\.be)/.+$', url):
        await update.message.reply_text(
            "❌ *Invalid YouTube URL*\n"
            "Please provide a valid YouTube link.",
            parse_mode='Markdown'
        )
        return
    
    await download_youtube(update, context, url, audio_only=True)

async def download_youtube(update: Update, context: ContextTypes.DEFAULT_TYPE, url: str, audio_only=False):
    """Download YouTube video and send it to the user."""
    try:
        # Send processing message
        processing_msg = await update.message.reply_text(
            "⏳ *Processing YouTube content...*",
            parse_mode='Markdown'
        )
        
        # Validate URL
        if not re.match(r'^(https?://)?(www\.)?(youtube\.com|youtu\.be)/.+$', url):
            await update.message.reply_text(
                "❌ *Invalid YouTube URL*\n"
                "Please provide a valid YouTube link.",
                parse_mode='Markdown'
            )
            await processing_msg.delete()
            return

        # Get video info first
        video_info = get_video_info(url)
        if not video_info:
            await update.message.reply_text(
                "❌ *Could not get video information*\n\n"
                "This might be due to:\n"
                "1️⃣ The video is private or restricted\n"
                "2️⃣ The video is not available in your region\n"
                "3️⃣ YouTube's API is temporarily unavailable\n\n"
                "Please try a different video or try again later.",
                parse_mode='Markdown'
            )
            await processing_msg.delete()
            return

        # Send video info
        await update.message.reply_text(
            f"📺 *Video Information*\n\n"
            f"📝 *Title:* {video_info['title']}\n"
            f"👤 *Channel:* {video_info['author']}\n"
            f"⏱️ *Length:* {video_info['length']} seconds\n"
            f"👁️ *Views:* {video_info['views']:,}",
            parse_mode='Markdown'
        )

        # Download video/audio
        try:
            # Configure yt-dlp options
            ydl_opts = {
                'format': 'bestaudio/best' if audio_only else 'best[ext=mp4]',
                'outtmpl': '%(id)s.%(ext)s',
                'quiet': True,
                'no_warnings': True,
                'nocheckcertificate': True,
                'geo_bypass': True,
                'no_playlist': True,
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }] if audio_only else []
            }
            
            # Try up to 3 times with different configurations
            for attempt in range(3):
                try:
                    logger.info(f"Download attempt {attempt + 1}")
                    
                    # Modify options based on attempt
                    if attempt == 1:
                        ydl_opts['format'] = 'bestaudio/best' if audio_only else 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
                    elif attempt == 2:
                        ydl_opts['format'] = 'bestaudio/best' if audio_only else 'best'
                    
                    await update.message.reply_text(
                        f"⏳ *Starting download...* (Attempt {attempt + 1}/3)",
                        parse_mode='Markdown'
                    )
                    
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(url, download=True)
                        file_path = f"{info['id']}.{'mp3' if audio_only else 'mp4'}"
                    
                    logger.info(f"Download completed on attempt {attempt + 1}")
                    break
                    
                except Exception as e:
                    logger.error(f"Download attempt {attempt + 1} failed: {str(e)}")
                    if attempt < 2:  # If not the last attempt
                        await update.message.reply_text(
                            f"❌ *Download failed. Retrying...* (Attempt {attempt + 1}/3)",
                            parse_mode='Markdown'
                        )
                        time.sleep(2)  # Wait before retrying
                        continue
                    raise  # Re-raise the exception if all attempts failed
            
        except Exception as e:
            logger.error(f"Error during download: {str(e)}")
            await update.message.reply_text(
                "❌ *Error downloading the content*\n\n"
                "This might be due to:\n"
                "1️⃣ The video is age-restricted\n"
                "2️⃣ The video is private\n"
                "3️⃣ The video is not available in your region\n\n"
                "Please try a different video.",
                parse_mode='Markdown'
            )
            await processing_msg.delete()
            return
        
        # Send file
        try:
            await update.message.reply_text(
                "✅ *Download complete! Sending file...*",
                parse_mode='Markdown'
            )
            with open(file_path, 'rb') as media_file:
                if audio_only:
                    await update.message.reply_audio(
                        audio=media_file,
                        title=video_info['title'],
                        performer=video_info['author'],
                        duration=video_info['length']
                    )
                else:
                    await update.message.reply_video(
                        video=media_file,
                        caption=f"📺 *{video_info['title']}*\n"
                               f"👤 *Channel:* {video_info['author']}\n"
                               f"⏱️ *Duration:* {video_info['length']} seconds",
                        parse_mode='Markdown'
                    )
            logger.info("File sent successfully")
        except Exception as e:
            logger.error(f"Error sending file: {str(e)}")
            await update.message.reply_text(
                f"❌ *Error sending file:* {str(e)}",
                parse_mode='Markdown'
            )
            if os.path.exists(file_path):
                os.remove(file_path)
            await processing_msg.delete()
            return
        
        # Delete the temporary file
        try:
            os.remove(file_path)
            logger.info("Temporary file deleted")
        except:
            pass  # Ignore if file is already deleted
        
        await processing_msg.delete()
        
    except Exception as e:
        logger.error(f"Error in download_youtube: {str(e)}")
        error_message = str(e)
        if "age-restricted" in error_message.lower():
            await update.message.reply_text(
                "🔞 *This video is age-restricted*\n"
                "Cannot be downloaded. Please try a different video.",
                parse_mode='Markdown'
            )
        elif "private" in error_message.lower():
            await update.message.reply_text(
                "🔒 *This video is private*\n"
                "Cannot be downloaded. Please try a different video.",
                parse_mode='Markdown'
            )
        elif "unavailable" in error_message.lower():
            await update.message.reply_text(
                "🌍 *This video is not available in your region*\n"
                "Please try a different video.",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                f"❌ *Error downloading YouTube content:*\n{error_message}",
                parse_mode='Markdown'
            )
        if 'processing_msg' in locals():
            await processing_msg.delete()

async def download_instagram(update: Update, context: ContextTypes.DEFAULT_TYPE, url: str):
    """Download Instagram content and send it to the user."""
    try:
        # Send processing message
        processing_msg = await update.message.reply_text(
            "⏳ *Processing Instagram content...*",
            parse_mode='Markdown'
        )
        
        # Clean URL and extract shortcode
        try:
            # Remove query parameters
            clean_url = url.split('?')[0]
            
            # Handle different URL formats
            if "/p/" in clean_url:
                shortcode = clean_url.split("/p/")[1].split("/")[0]
            elif "/reel/" in clean_url:
                shortcode = clean_url.split("/reel/")[1].split("/")[0]
            else:
                await update.message.reply_text(
                    "❌ *Invalid Instagram URL*\n"
                    "Please provide a valid Instagram post or reel link.",
                    parse_mode='Markdown'
                )
                await processing_msg.delete()
                return
                
            if not shortcode:
                raise ValueError("Could not extract shortcode from URL")
                
        except Exception as e:
            await update.message.reply_text(
                "❌ *Invalid Instagram URL format*\n"
                "Please provide a valid Instagram post or reel link.",
                parse_mode='Markdown'
            )
            await processing_msg.delete()
            return
        
        # Download post
        try:
            post = instaloader.Post.from_shortcode(L.context, shortcode)
        except Exception as e:
            await update.message.reply_text(
                "❌ *Could not access the Instagram post*\n"
                "Make sure the post is public and accessible.",
                parse_mode='Markdown'
            )
            await processing_msg.delete()
            return
        
        # Create temp directory if it doesn't exist
        if not os.path.exists("temp"):
            os.makedirs("temp")
        
        # Download post
        try:
            L.download_post(post, target="temp")
        except Exception as e:
            await update.message.reply_text(
                "❌ *Error downloading the post*\n"
                "Please try again later.",
                parse_mode='Markdown'
            )
            await processing_msg.delete()
            return
        
        # Find downloaded files
        media_files = []
        for file in os.listdir("temp"):
            if file.endswith((".mp4", ".jpg", ".jpeg")):
                media_files.append(os.path.join("temp", file))
        
        if not media_files:
            await update.message.reply_text(
                "❌ *No media files found in the post*",
                parse_mode='Markdown'
            )
            await processing_msg.delete()
            return
        
        # Send each media file
        for media_file in media_files:
            try:
                with open(media_file, 'rb') as f:
                    if media_file.endswith(".mp4"):
                        await update.message.reply_video(
                            video=f,
                            caption=f"📸 *Instagram Post*\n\n"
                                   f"📝 *Caption:* {post.caption}",
                            parse_mode='Markdown'
                        )
                    else:
                        await update.message.reply_photo(
                            photo=f,
                            caption=f"📸 *Instagram Post*\n\n"
                                   f"📝 *Caption:* {post.caption}",
                            parse_mode='Markdown'
                        )
                
                # Clean up
                os.remove(media_file)
            except Exception as e:
                await update.message.reply_text(
                    f"❌ *Error sending media file:* {str(e)}",
                    parse_mode='Markdown'
                )
                continue
        
        # Remove temp directory
        try:
            os.rmdir("temp")
        except:
            pass  # Ignore if directory is not empty
        
        await processing_msg.delete()
        
    except Exception as e:
        await update.message.reply_text(
            f"❌ *Error downloading Instagram content:*\n{str(e)}",
            parse_mode='Markdown'
        )
        if 'processing_msg' in locals():
            await processing_msg.delete()

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming messages."""
    message_text = update.message.text
    
    if "youtube.com" in message_text or "youtu.be" in message_text:
        # Create inline keyboard for YouTube download options
        keyboard = [
            [
                InlineKeyboardButton("🎥 Download Video", callback_data=f"yt_video_{message_text}"),
                InlineKeyboardButton("🎵 Download Audio", callback_data=f"yt_audio_{message_text}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Get video info first
        video_info = get_video_info(message_text)
        if not video_info:
            await update.message.reply_text(
                "❌ *Could not get video information*\n\n"
                "This might be due to:\n"
                "1️⃣ The video is private or restricted\n"
                "2️⃣ The video is not available in your region\n"
                "3️⃣ YouTube's API is temporarily unavailable\n\n"
                "Please try a different video or try again later.",
                parse_mode='Markdown'
            )
            return

        # Send video info with download options
        await update.message.reply_text(
            f"📺 *Video Information*\n\n"
            f"📝 *Title:* {video_info['title']}\n"
            f"👤 *Channel:* {video_info['author']}\n"
            f"⏱️ *Length:* {video_info['length']} seconds\n"
            f"👁️ *Views:* {video_info['views']:,}\n\n"
            "🎯 *Choose download option:*",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    elif "instagram.com" in message_text:
        await download_instagram(update, context, message_text)
    else:
        await update.message.reply_text(
            "❓ *Invalid Link*\n\n"
            "Please send a valid YouTube or Instagram link.",
            parse_mode='Markdown'
        )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button callbacks."""
    query = update.callback_query
    await query.answer()  # Answer the callback query
    
    # Extract the action and URL from the callback data
    action, url = query.data.split('_', 1)
    
    if action == "yt":
        # Remove the action prefix from the URL
        url = url[5:]  # Remove "yt_video_" or "yt_audio_"
        
        # Download based on the selected option
        if "video" in query.data:
            await download_youtube(update, context, url, audio_only=False)
        elif "audio" in query.data:
            await download_youtube(update, context, url, audio_only=True)

def main():
    """Start the bot."""
    # Get token from config
    token = TELEGRAM_BOT_TOKEN
    if not token or token == "your_bot_token_here":
        logger.error("Please set your bot token in config.py")
        return

    # Create the Application
    application = Application.builder().token(token).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("audio", audio_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(button_callback))

    # Start the Bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main() 
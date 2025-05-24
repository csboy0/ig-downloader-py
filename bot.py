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
from datetime import datetime
import humanize
import asyncio

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Initialize Instagram loader
L = instaloader.Instaloader()

class DownloadProgress:
    def __init__(self, message, context):
        self.message = message
        self.context = context
        self.status_message = None
        self.queue = asyncio.Queue()
        self.finished = False
        self._loop = None

    def progress_hook(self, d):
        # This runs in the yt-dlp thread, so just put data in the queue
        if self._loop is None:
            try:
                self._loop = asyncio.get_event_loop()
            except RuntimeError:
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)
        
        if self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self.queue.put(d), self._loop)
        else:
            self._loop.run_until_complete(self.queue.put(d))

    async def updater(self):
        while not self.finished:
            try:
                d = await asyncio.wait_for(self.queue.get(), timeout=1)
            except asyncio.TimeoutError:
                continue

            if d['status'] == 'downloading':
                percent = 0
                total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
                downloaded = d.get('downloaded_bytes', 0)
                if total > 0:
                    percent = downloaded * 100 / total
                speed = d.get('speed', 0)
                speed_str = f"{speed/1024/1024:.1f} MB/s" if speed else "N/A"
                eta = d.get('eta', 0)
                eta_str = f"{int(eta)}s" if eta else "N/A"
                bar_length = 20
                filled_length = int(bar_length * percent / 100)
                bar = '█' * filled_length + '░' * (bar_length - filled_length)
                status_text = (
                    f"⏳ *Downloading...*\n\n"
                    f"📊 Progress: {percent:.1f}%\n"
                    f"`{bar}`\n\n"
                    f"📥 Downloaded: {downloaded/1024/1024:.1f} MB\n"
                    f"📦 Total: {total/1024/1024:.1f} MB\n"
                    f"🚀 Speed: {speed_str}\n"
                    f"⏱️ ETA: {eta_str}"
                )
                if self.status_message:
                    try:
                        await self.status_message.edit_text(status_text, parse_mode='Markdown')
                    except Exception:
                        pass
                else:
                    self.status_message = await self.message.reply_text(status_text, parse_mode='Markdown')
            elif d['status'] == 'finished':
                self.finished = True
                if self.status_message:
                    await self.status_message.edit_text(
                        "✅ *Download complete!*\n"
                        "⏳ Processing file...",
                        parse_mode='Markdown'
                    )

def format_duration(seconds):
    """Format duration in seconds to human readable format."""
    return humanize.naturaldelta(seconds)

def format_views(views):
    """Format view count to human readable format."""
    return humanize.intword(views)

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
                    
                    # Get upload date
                    upload_date = info.get('upload_date', '')
                    if upload_date:
                        try:
                            upload_date = datetime.strptime(upload_date, '%Y%m%d').strftime('%B %d, %Y')
                        except:
                            upload_date = 'Unknown'
                    else:
                        upload_date = 'Unknown'
                    
                    return {
                        'title': info.get('title', 'Unknown Title'),
                        'length': info.get('duration', 0),
                        'author': info.get('uploader', 'Unknown Author'),
                        'views': info.get('view_count', 0),
                        'video_id': info.get('id', ''),
                        'upload_date': upload_date,
                        'thumbnail': info.get('thumbnail', ''),
                        'description': info.get('description', '')[:200] + '...' if info.get('description') else 'No description available'
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
        '• /audio - Download YouTube video as audio\n'
        '• /about - Show bot information\n\n'
        '💡 *Tip:* You can also use the buttons below to choose download options.',
        parse_mode='Markdown'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /help is issued."""
    await update.message.reply_text(
        '📥 *How to Download Content:*\n\n'
        '1️⃣ Send a YouTube video/shorts link to download the video\n'
        '2️⃣ Send an Instagram post/reel link to download the content\n'
        '3️⃣ Use /audio command followed by YouTube link to download as MP3\n\n'
        '⚠️ *Note:* Make sure the content is public and accessible.\n\n'
        '💡 *Tips:*\n'
        '• For best quality, use the download buttons\n'
        '• Audio downloads are in high quality (192kbps)\n'
        '• Videos are downloaded in the best available quality',
        parse_mode='Markdown'
    )

async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send information about the bot."""
    await update.message.reply_text(
        '🤖 *About Media Downloader Bot*\n\n'
        'Version: 2.0.0\n'
        'Last Updated: March 2024\n\n'
        '✨ *Features:*\n'
        '• High-quality video downloads\n'
        '• High-quality audio downloads (192kbps)\n'
        '• Instagram content support\n'
        '• Beautiful UI with emojis\n'
        '• Progress tracking\n'
        '• Error handling\n\n'
        '🔧 *Technical Details:*\n'
        '• Built with python-telegram-bot\n'
        '• Uses yt-dlp for YouTube downloads\n'
        '• Uses instaloader for Instagram downloads\n\n'
        '💝 *Support:*\n'
        'If you encounter any issues, please contact the bot administrator.',
        parse_mode='Markdown'
    )

def is_valid_youtube_url(url):
    """Check if the URL is a valid YouTube URL."""
    # Clean the URL
    url = url.strip().lstrip('@')  # Remove whitespace and @ symbol
    
    logger.info(f"Validating URL: {url}")
    
    youtube_regex = (
        r'(https?://)?(www\.)?'
        r'(youtube\.com/(watch\?v=|shorts/|embed/|v/)|youtu\.be/)'
        r'([a-zA-Z0-9_-]{11})'
    )
    is_valid = bool(re.match(youtube_regex, url))
    logger.info(f"URL validation result: {is_valid}")
    return is_valid

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
    # Remove @ symbol if present at the start
    url = url.lstrip('@')
    
    if not is_valid_youtube_url(url):
        await update.message.reply_text(
            "❌ *Invalid YouTube URL*\n"
            "Please provide a valid YouTube link.\n\n"
            "Supported formats:\n"
            "• youtube.com/watch?v=...\n"
            "• youtu.be/...\n"
            "• youtube.com/shorts/...\n"
            "• youtube.com/embed/...",
            parse_mode='Markdown'
        )
        return
    
    await download_youtube(update, context, url, audio_only=True)

async def download_youtube(message, context: ContextTypes.DEFAULT_TYPE, url: str, audio_only=False):
    try:
        if not message:
            logger.error("No message object found")
            return
        url = url.lstrip('@')
        processing_msg = await message.reply_text(
            "⏳ *Processing YouTube content...*",
            parse_mode='Markdown'
        )
        # Initialize progress tracker
        progress = DownloadProgress(message, context)
        updater_task = asyncio.create_task(progress.updater())
        # Validate URL
        if not is_valid_youtube_url(url):
            await message.reply_text(
                "❌ *Invalid YouTube URL*\n"
                "Please provide a valid YouTube link.\n\n"
                "Supported formats:\n"
                "• youtube.com/watch?v=...\n"
                "• youtu.be/...\n"
                "• youtube.com/shorts/...\n"
                "• youtube.com/embed/...",
                parse_mode='Markdown'
            )
            await processing_msg.delete()
            progress.finished = True
            await updater_task
            return
        video_info = get_video_info(url)
        if not video_info:
            await message.reply_text(
                "❌ *Could not get video information*\n\n"
                "This might be due to:\n"
                "1️⃣ The video is private or restricted\n"
                "2️⃣ The video is not available in your region\n"
                "3️⃣ YouTube's API is temporarily unavailable\n\n"
                "Please try a different video or try again later.",
                parse_mode='Markdown'
            )
            await processing_msg.delete()
            progress.finished = True
            await updater_task
            return
        await message.reply_text(
            f"📺 *Video Information*\n\n"
            f"📝 *Title:* {video_info['title']}\n"
            f"👤 *Channel:* {video_info['author']}\n"
            f"⏱️ *Length:* {format_duration(video_info['length'])}\n"
            f"👁️ *Views:* {format_views(video_info['views'])}\n"
            f"📅 *Upload Date:* {video_info['upload_date']}",
            parse_mode='Markdown'
        )
        try:
            ydl_opts = {
                'format': 'bestaudio/best' if audio_only else 'best[ext=mp4]',
                'outtmpl': '%(id)s.%(ext)s',
                'quiet': True,
                'no_warnings': True,
                'nocheckcertificate': True,
                'geo_bypass': True,
                'no_playlist': True,
                'progress_hooks': [progress.progress_hook],
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }] if audio_only else []
            }
            for attempt in range(3):
                try:
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = await asyncio.get_event_loop().run_in_executor(
                            None, lambda: ydl.extract_info(url, download=True)
                        )
                        file_path = f"{info['id']}.{'mp3' if audio_only else 'mp4'}"
                    break
                except Exception as e:
                    if attempt < 2:
                        await asyncio.sleep(2)
                        continue
                    raise
        finally:
            progress.finished = True
            await updater_task
        try:
            if progress.status_message:
                await progress.status_message.edit_text(
                    "✅ *Download complete!*\n"
                    "📤 *Sending file...*",
                    parse_mode='Markdown'
                )
            with open(file_path, 'rb') as media_file:
                if audio_only:
                    await message.reply_audio(
                        audio=media_file,
                        title=video_info['title'],
                        performer=video_info['author'],
                        duration=video_info['length']
                    )
                else:
                    await message.reply_video(
                        video=media_file,
                        caption=f"📺 *{video_info['title']}*\n"
                               f"👤 *Channel:* {video_info['author']}\n"
                               f"⏱️ *Duration:* {video_info['length']} seconds",
                        parse_mode='Markdown'
                    )
            logger.info("File sent successfully")
        except Exception as e:
            logger.error(f"Error sending file: {str(e)}")
            await message.reply_text(
                f"❌ *Error sending file:* {str(e)}",
                parse_mode='Markdown'
            )
            if os.path.exists(file_path):
                os.remove(file_path)
            if progress.status_message:
                await progress.status_message.delete()
            await processing_msg.delete()
            return
        try:
            os.remove(file_path)
            logger.info("Temporary file deleted")
        except:
            pass
        if progress.status_message:
            await progress.status_message.delete()
        await processing_msg.delete()
    except Exception as e:
        logger.error(f"Error in download_youtube: {str(e)}")
        error_message = str(e)
        if "age-restricted" in error_message.lower():
            await message.reply_text(
                "🔞 *This video is age-restricted*\n"
                "Cannot be downloaded. Please try a different video.",
                parse_mode='Markdown'
            )
        elif "private" in error_message.lower():
            await message.reply_text(
                "🔒 *This video is private*\n"
                "Cannot be downloaded. Please try a different video.",
                parse_mode='Markdown'
            )
        elif "unavailable" in error_message.lower():
            await message.reply_text(
                "🌍 *This video is not available in your region*\n"
                "Please try a different video.",
                parse_mode='Markdown'
            )
        else:
            await message.reply_text(
                f"❌ *Error downloading YouTube content:*\n{error_message}",
                parse_mode='Markdown'
            )
        if 'processing_msg' in locals():
            await processing_msg.delete()
        if 'progress' in locals() and progress.status_message:
            await progress.status_message.delete()

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

def extract_youtube_url(text):
    """Extract YouTube URL from text."""
    try:
        # Clean the text
        text = text.strip()
        logger.info(f"Extracting URL from text: {text}")
        
        # Remove any @ symbol at the start
        text = text.lstrip('@')
        
        # Try to find the video ID first
        video_id = None
        
        # Pattern for video ID in various formats
        patterns = [
            r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/|youtube\.com/embed/)([a-zA-Z0-9_-]{11})',
            r'v=([a-zA-Z0-9_-]{11})',
            r'/([a-zA-Z0-9_-]{11})'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                video_id = match.group(1)
                logger.info(f"Found video ID: {video_id}")
                break
        
        if video_id:
            # Construct the full URL
            url = f"https://www.youtube.com/watch?v={video_id}"
            logger.info(f"Constructed URL: {url}")
            return url
            
        logger.error("No video ID found in text")
        return None
        
    except Exception as e:
        logger.error(f"Error in extract_youtube_url: {str(e)}")
        return None

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming messages."""
    try:
        message_text = update.message.text.strip()
        logger.info(f"Received message: {message_text}")
        
        # Extract YouTube URL from message
        youtube_url = extract_youtube_url(message_text)
        logger.info(f"Extracted URL: {youtube_url}")
        
        if youtube_url:
            logger.info(f"Processing YouTube URL: {youtube_url}")
            # Create inline keyboard for YouTube download options
            keyboard = [
                [
                    InlineKeyboardButton("🎥 Download Video", callback_data=f"yt_video_{youtube_url}"),
                    InlineKeyboardButton("🎵 Download Audio", callback_data=f"yt_audio_{youtube_url}")
                ],
                [
                    InlineKeyboardButton("ℹ️ Show Info", callback_data=f"yt_info_{youtube_url}")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Get video info first
            logger.info("Getting video info...")
            video_info = get_video_info(youtube_url)
            if not video_info:
                logger.error("Failed to get video info")
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

            logger.info("Successfully got video info")
            # Send video info with download options
            await update.message.reply_text(
                f"📺 *Video Information*\n\n"
                f"📝 *Title:* {video_info['title']}\n"
                f"👤 *Channel:* {video_info['author']}\n"
                f"⏱️ *Length:* {format_duration(video_info['length'])}\n"
                f"👁️ *Views:* {format_views(video_info['views'])}\n"
                f"📅 *Upload Date:* {video_info['upload_date']}\n\n"
                "🎯 *Choose download option:*",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        elif "youtube.com" in message_text or "youtu.be" in message_text:
            logger.error(f"Invalid YouTube URL format: {message_text}")
            await update.message.reply_text(
                "❌ *Invalid YouTube URL*\n\n"
                "Please provide a valid YouTube link.\n\n"
                "Supported formats:\n"
                "• youtube.com/watch?v=...\n"
                "• youtu.be/...\n"
                "• youtube.com/shorts/...\n"
                "• youtube.com/embed/...\n\n"
                "Example: `https://www.youtube.com/watch?v=dQw4w9WgXcQ`\n\n"
                "Or just send the video ID: `dQw4w9WgXcQ`",
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
    except Exception as e:
        logger.error(f"Error in handle_message: {str(e)}")
        await update.message.reply_text(
            "❌ *An error occurred*\n"
            "Please try again later.",
            parse_mode='Markdown'
        )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button callbacks."""
    query = update.callback_query
    await query.answer()  # Answer the callback query
    
    try:
        # Extract the action and URL from the callback data
        parts = query.data.split('_', 2)  # Split into max 3 parts
        if len(parts) != 3:
            logger.error(f"Invalid callback data format: {query.data}")
            return
            
        action_type, action, url = parts
        
        if action_type == "yt":
            logger.info(f"Processing YouTube action: {action} for URL: {url}")
            
            # Handle different actions
            if action == "video":
                await download_youtube(query.message, context, url, audio_only=False)
            elif action == "audio":
                await download_youtube(query.message, context, url, audio_only=True)
            elif action == "info":
                await show_video_info(query.message, context, url)
            else:
                logger.error(f"Unknown action: {action}")
                await query.message.reply_text(
                    "❌ *Invalid action*\n"
                    "Please try again.",
                    parse_mode='Markdown'
                )
    except Exception as e:
        logger.error(f"Error in button callback: {str(e)}")
        await query.message.reply_text(
            "❌ *An error occurred*\n"
            "Please try again.",
            parse_mode='Markdown'
        )

async def show_video_info(message, context: ContextTypes.DEFAULT_TYPE, url: str):
    """Show detailed video information."""
    try:
        if not message:
            logger.error("No message object found")
            return
            
        # Get video info
        video_info = get_video_info(url)
        if not video_info:
            await message.reply_text(
                "❌ *Could not get video information*\n\n"
                "This might be due to:\n"
                "1️⃣ The video is private or restricted\n"
                "2️⃣ The video is not available in your region\n"
                "3️⃣ YouTube's API is temporarily unavailable\n\n"
                "Please try a different video or try again later.",
                parse_mode='Markdown'
            )
            return

        # Create inline keyboard for download options
        keyboard = [
            [
                InlineKeyboardButton("🎥 Download Video", callback_data=f"yt_video_{url}"),
                InlineKeyboardButton("🎵 Download Audio", callback_data=f"yt_audio_{url}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Send detailed video info
        await message.reply_text(
            f"📺 *Detailed Video Information*\n\n"
            f"📝 *Title:* {video_info['title']}\n"
            f"👤 *Channel:* {video_info['author']}\n"
            f"⏱️ *Length:* {format_duration(video_info['length'])}\n"
            f"👁️ *Views:* {format_views(video_info['views'])}\n"
            f"📅 *Upload Date:* {video_info['upload_date']}\n\n"
            f"📄 *Description:*\n{video_info['description']}\n\n"
            "🎯 *Choose download option:*",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    except Exception as e:
        logger.error(f"Error showing video info: {str(e)}")
        await message.reply_text(
            "❌ *Error getting video information*\n"
            "Please try again later.",
            parse_mode='Markdown'
        )

def main():
    """Start the bot."""
    # Get token from config
    token = TELEGRAM_BOT_TOKEN
    if not token or token == "your_bot_token_here":
        logger.error("Please set your bot token in config.py")
        return

    # Create the Application with custom settings
    application = (
        Application.builder()
        .token(token)
        .connect_timeout(30.0)  # Increase connection timeout
        .read_timeout(30.0)     # Increase read timeout
        .write_timeout(30.0)    # Increase write timeout
        .pool_timeout(30.0)     # Increase pool timeout
        .build()
    )

    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("audio", audio_command))
    application.add_handler(CommandHandler("about", about_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(button_callback))

    # Add error handler
    application.add_error_handler(error_handler)

    # Start the Bot with retry logic
    while True:
        try:
            logger.info("Starting bot...")
            application.run_polling(allowed_updates=Update.ALL_TYPES)
        except Exception as e:
            logger.error(f"Error running bot: {str(e)}")
            logger.info("Retrying in 5 seconds...")
            time.sleep(5)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle errors in the bot."""
    logger.error(f"Exception while handling an update: {context.error}")
    
    if update and update.effective_message:
        await update.effective_message.reply_text(
            "❌ *An error occurred*\n"
            "Please try again in a few moments.",
            parse_mode='Markdown'
        )

if __name__ == '__main__':
    main() 
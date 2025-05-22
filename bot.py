import os
import logging
import re
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
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
        # Configure yt-dlp options
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
            'format': 'best',
            'nocheckcertificate': True,
            'ignoreerrors': True,
            'geo_bypass': True,
            'extractor_args': {
                'youtube': {
                    'skip': ['dash', 'hls'],
                    'player_client': ['android'],
                    'player_skip': ['js', 'configs', 'webpage'],
                }
            },
            'verbose': True,  # Enable verbose output for debugging
            'dump_single_json': True,  # Get all available information
            'no_playlist': True,  # Only download single video
            'extract_flat': False,  # Get full video info
            'force_generic_extractor': False,  # Use YouTube extractor
            'youtube_include_dash_manifest': False,  # Skip DASH manifest
            'youtube_include_hls_manifest': False,  # Skip HLS manifest
        }
        
        logger.info(f"Attempting to get info for URL: {url}")
        
        # Get video info
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(url, download=False)
                logger.info(f"Successfully extracted info: {json.dumps(info, indent=2)}")
            except Exception as e:
                logger.error(f"Error during extraction: {str(e)}")
                raise
            
            if not info:
                raise Exception("Could not extract video information")
            
            # Log specific fields for debugging
            logger.info(f"Title: {info.get('title')}")
            logger.info(f"Duration: {info.get('duration')}")
            logger.info(f"Uploader: {info.get('uploader')}")
            logger.info(f"View count: {info.get('view_count')}")
            logger.info(f"Video ID: {info.get('id')}")
            
            return {
                'title': info.get('title', 'Unknown Title'),
                'length': info.get('duration', 0),
                'author': info.get('uploader', 'Unknown Author'),
                'views': info.get('view_count', 0),
                'video_id': info.get('id', '')
            }
                
    except Exception as e:
        logger.error(f"Error getting video info: {str(e)}")
        # Log the full error traceback
        import traceback
        logger.error(f"Full error traceback: {traceback.format_exc()}")
        return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /start is issued."""
    await update.message.reply_text(
        'Hi! I can help you download content from YouTube and Instagram.\n\n'
        'Supported content:\n'
        '- YouTube videos\n'
        '- YouTube Shorts\n'
        '- Instagram posts (photos)\n'
        '- Instagram reels\n'
        '- Instagram videos\n\n'
        'Just send me a link, and I\'ll download it for you!\n\n'
        'Commands:\n'
        '/start - Show this message\n'
        '/help - Show help message'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /help is issued."""
    await update.message.reply_text(
        'To download content:\n\n'
        '1. Send a YouTube video/shorts link to download the video\n'
        '2. Send an Instagram post/reel link to download the content\n\n'
        'Note: Make sure the content is public and accessible.'
    )

async def download_youtube(update: Update, context: ContextTypes.DEFAULT_TYPE, url: str):
    """Download YouTube video and send it to the user."""
    try:
        # Send processing message
        processing_msg = await update.message.reply_text("Processing YouTube content...")
        
        # Validate URL
        if not re.match(r'^(https?://)?(www\.)?(youtube\.com|youtu\.be)/.+$', url):
            await update.message.reply_text("Invalid YouTube URL. Please provide a valid YouTube link.")
            await processing_msg.delete()
            return

        # Get video info first
        video_info = get_video_info(url)
        if not video_info:
            await update.message.reply_text(
                "Could not get video information. This might be due to:\n"
                "1. The video is private or restricted\n"
                "2. The video is not available in your region\n"
                "3. YouTube's API is temporarily unavailable\n\n"
                "Please try a different video or try again later."
            )
            await processing_msg.delete()
            return

        # Send video info
        await update.message.reply_text(
            f"Title: {video_info['title']}\n"
            f"Channel: {video_info['author']}\n"
            f"Length: {video_info['length']} seconds\n"
            f"Views: {video_info['views']:,}"
        )

        # Download video
        try:
            # Configure yt-dlp options
            ydl_opts = {
                'format': 'best[ext=mp4]',
                'outtmpl': '%(id)s.%(ext)s',
                'quiet': True,
                'no_warnings': True,
                'nocheckcertificate': True,
                'geo_bypass': True,
                'extractor_args': {
                    'youtube': {
                        'skip': ['dash', 'hls'],
                        'player_client': ['android'],
                        'player_skip': ['js', 'configs', 'webpage'],
                    }
                },
                'verbose': True,  # Enable verbose output for debugging
                'no_playlist': True,  # Only download single video
                'force_generic_extractor': False,  # Use YouTube extractor
                'youtube_include_dash_manifest': False,  # Skip DASH manifest
                'youtube_include_hls_manifest': False,  # Skip HLS manifest
            }
            
            # Download the video
            await update.message.reply_text("Starting download... This might take a few minutes.")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                try:
                    info = ydl.extract_info(url, download=True)
                    logger.info(f"Successfully downloaded video: {json.dumps(info, indent=2)}")
                except Exception as e:
                    logger.error(f"Error during download: {str(e)}")
                    logger.error(f"Full error traceback: {traceback.format_exc()}")
                    raise
                
                file_path = f"{info['id']}.mp4"
            
            logger.info(f"Download completed: {file_path}")
            
        except Exception as e:
            logger.error(f"Error during download: {str(e)}")
            await update.message.reply_text(
                "Error downloading the video. This might be due to:\n"
                "1. The video is age-restricted\n"
                "2. The video is private\n"
                "3. The video is not available in your region\n"
                "Please try a different video."
            )
            await processing_msg.delete()
            return
        
        # Send video file
        try:
            await update.message.reply_text("Download complete! Sending video...")
            with open(file_path, 'rb') as video_file:
                await update.message.reply_video(
                    video=video_file,
                    caption=f"Title: {video_info['title']}\nChannel: {video_info['author']}\nDuration: {video_info['length']} seconds"
                )
            logger.info("Video sent successfully")
        except Exception as e:
            logger.error(f"Error sending video: {str(e)}")
            await update.message.reply_text(f"Error sending video: {str(e)}")
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
                "This video is age-restricted and cannot be downloaded. Please try a different video."
            )
        elif "private" in error_message.lower():
            await update.message.reply_text(
                "This video is private and cannot be downloaded. Please try a different video."
            )
        elif "unavailable" in error_message.lower():
            await update.message.reply_text(
                "This video is not available in your region. Please try a different video."
            )
        else:
            await update.message.reply_text(f"Error downloading YouTube content: {error_message}")
        if 'processing_msg' in locals():
            await processing_msg.delete()

async def download_instagram(update: Update, context: ContextTypes.DEFAULT_TYPE, url: str):
    """Download Instagram content and send it to the user."""
    try:
        # Send processing message
        processing_msg = await update.message.reply_text("Processing Instagram content...")
        
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
                await update.message.reply_text("Invalid Instagram URL. Please provide a valid Instagram post or reel link.")
                await processing_msg.delete()
                return
                
            if not shortcode:
                raise ValueError("Could not extract shortcode from URL")
                
        except Exception as e:
            await update.message.reply_text("Invalid Instagram URL format. Please provide a valid Instagram post or reel link.")
            await processing_msg.delete()
            return
        
        # Download post
        try:
            post = instaloader.Post.from_shortcode(L.context, shortcode)
        except Exception as e:
            await update.message.reply_text("Could not access the Instagram post. Make sure the post is public and accessible.")
            await processing_msg.delete()
            return
        
        # Create temp directory if it doesn't exist
        if not os.path.exists("temp"):
            os.makedirs("temp")
        
        # Download post
        try:
            L.download_post(post, target="temp")
        except Exception as e:
            await update.message.reply_text("Error downloading the post. Please try again later.")
            await processing_msg.delete()
            return
        
        # Find downloaded files
        media_files = []
        for file in os.listdir("temp"):
            if file.endswith((".mp4", ".jpg", ".jpeg")):
                media_files.append(os.path.join("temp", file))
        
        if not media_files:
            await update.message.reply_text("No media files found in the post.")
            await processing_msg.delete()
            return
        
        # Send each media file
        for media_file in media_files:
            try:
                with open(media_file, 'rb') as f:
                    if media_file.endswith(".mp4"):
                        await update.message.reply_video(
                            video=f,
                            caption=f"Instagram Post\nCaption: {post.caption}"
                        )
                    else:
                        await update.message.reply_photo(
                            photo=f,
                            caption=f"Instagram Post\nCaption: {post.caption}"
                        )
                
                # Clean up
                os.remove(media_file)
            except Exception as e:
                await update.message.reply_text(f"Error sending media file: {str(e)}")
                continue
        
        # Remove temp directory
        try:
            os.rmdir("temp")
        except:
            pass  # Ignore if directory is not empty
        
        await processing_msg.delete()
        
    except Exception as e:
        await update.message.reply_text(f"Error downloading Instagram content: {str(e)}")
        if 'processing_msg' in locals():
            await processing_msg.delete()

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming messages."""
    message_text = update.message.text
    
    if "youtube.com" in message_text or "youtu.be" in message_text:
        await download_youtube(update, context, message_text)
    elif "instagram.com" in message_text:
        await download_instagram(update, context, message_text)
    else:
        await update.message.reply_text(
            "Please send a valid YouTube or Instagram link."
        )

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
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Start the Bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main() 
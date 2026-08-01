import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import json
import os
import threading
import time
import re
from pyzbar.pyzbar import decode
from PIL import Image
import io

TOKEN = '8920769724:AAHsBMzcEQILYb259m6ozAMXxbEGU0wzekY'
ADMIN_CHANNEL_ID = -1004290008401 
SUPER_ADMIN_ID = "6788856373"

bot = telebot.TeleBot(TOKEN)
USERS_FILE = 'users.json'

def load_users():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'r') as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                data = {}
            # Migrate old data
            for uid, info in data.items():
                if 'total_urls' not in info:
                    info['total_urls'] = 0
                if 'expires_at' not in info:
                    info['expires_at'] = None
            return data
    return {}

def save_users(users):
    with open(USERS_FILE, 'w') as f:
        json.dump(users, f)

def parse_time(time_str):
    match = re.match(r"(\d+)([smhd])", time_str.lower())
    if not match:
        return None
    val = int(match.group(1))
    unit = match.group(2)
    if unit == 's': return val
    if unit == 'm': return val * 60
    if unit == 'h': return val * 3600
    if unit == 'd': return val * 86400
    return None

def find_user_id(users, identifier):
    identifier = str(identifier).strip()
    if identifier in users:
        return identifier
    if identifier.startswith('@'):
        username_query = identifier[1:].lower()
    else:
        username_query = identifier.lower()
        
    for uid, info in users.items():
        if info.get('username', '').lower() == username_query:
            return uid
    return None

def check_expiration(users, user_id):
    info = users.get(user_id)
    if not info: return False
    
    expires = info.get('expires_at')
    if expires and time.time() > expires:
        info['status'] = 'pending'
        info['expires_at'] = None
        save_users(users)
        return True 
    return False

# Dictionary to hold links for each media group
media_groups = {} # media_group_id -> {"chat_id": chat_id, "links": [], "user_id": user_id}
media_timers = {} # media_group_id -> timer_object

def send_media_group_links(group_id):
    if group_id in media_groups:
        data = media_groups.pop(group_id)
        if group_id in media_timers:
            del media_timers[group_id]
        
        links = data['links']
        chat_id = data['chat_id']
        user_id = data['user_id']
        
        if links:
            users = load_users()
            if user_id in users:
                users[user_id]['total_urls'] = users[user_id].get('total_urls', 0) + len(links)
                save_users(users)
                
            links_text = "\n".join(links)
            text = f"<code>{links_text}</code>"
            try:
                bot.send_message(chat_id, text, parse_mode="HTML")
            except Exception as e:
                print(f"Error sending message: {e}")

@bot.message_handler(commands=['help'])
def admin_help(message):
    if str(message.from_user.id) != SUPER_ADMIN_ID:
        return
    help_text = """
<b>Admin Commands:</b>
/help - Show this message
/totalusers - Show total number of users
/users - List all users, usernames, and their total URLs decoded
/approve [username/id] - Approve a user permanently
/approve [username/id] [time] - Approve a user temporarily (e.g. 1h, 5m, 2d)
/block [username/id] - Block a user permanently
/block [username/id] [time] - Block a user temporarily (e.g. 10m, 1h)
/unapprove [username/id] - Revert user back to pending status

<i>Time formats: s (seconds), m (minutes), h (hours), d (days). E.g., 2m, 1h</i>
    """
    bot.reply_to(message, help_text, parse_mode="HTML")

@bot.message_handler(commands=['totalusers'])
def total_users(message):
    if str(message.from_user.id) != SUPER_ADMIN_ID:
        return
    users = load_users()
    bot.reply_to(message, f"Total users registered: {len(users)}")

@bot.message_handler(commands=['users'])
def list_users(message):
    if str(message.from_user.id) != SUPER_ADMIN_ID:
        return
    users = load_users()
    if not users:
        bot.reply_to(message, "No users found.")
        return
        
    text = "<b>User List:</b>\n\n"
    for uid, info in users.items():
        name = info.get('name', 'Unknown')
        username = info.get('username', 'No username')
        urls = info.get('total_urls', 0)
        status = info.get('status', 'unknown')
        text += f"Name: {name}\nUsername: @{username}\nID: <code>{uid}</code>\nTotal URLs: {urls}\nStatus: {status}\n---\n"
    
    for i in range(0, len(text), 4000):
        bot.send_message(message.chat.id, text[i:i+4000], parse_mode="HTML")

@bot.message_handler(commands=['approve', 'block', 'unapprove'])
def handle_admin_actions(message):
    if str(message.from_user.id) != SUPER_ADMIN_ID:
        return
        
    parts = message.text.split()
    command = parts[0].lower()
    
    if len(parts) < 2:
        bot.reply_to(message, f"Usage: {command} [username/id] [time]")
        return
        
    identifier = parts[1]
    time_str = parts[2] if len(parts) > 2 else None
    
    users = load_users()
    user_id = find_user_id(users, identifier)
    
    if not user_id:
        bot.reply_to(message, "User not found in database. Make sure they have started the bot at least once.")
        return
        
    expires_at = None
    if time_str:
        seconds = parse_time(time_str)
        if not seconds:
            bot.reply_to(message, "Invalid time format. Use s, m, h, or d (e.g. 5m, 1h).")
            return
        expires_at = time.time() + seconds
        
    if command == '/approve':
        users[user_id]['status'] = 'approved'
        action_text = "Approved"
    elif command == '/block':
        users[user_id]['status'] = 'rejected'
        action_text = "Blocked"
    elif command == '/unapprove':
        users[user_id]['status'] = 'pending'
        action_text = "Unapproved (set to pending)"
        expires_at = None
        
    users[user_id]['expires_at'] = expires_at
    save_users(users)
    
    expiry_msg = f" until {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(expires_at))}" if expires_at else " permanently"
    if command == '/unapprove': expiry_msg = ""
    
    bot.reply_to(message, f"User <code>{user_id}</code> (@{users[user_id].get('username', '')}) has been {action_text}{expiry_msg}.", parse_mode="HTML")
    
    try:
        notif = f"Your account has been {action_text.lower()}{expiry_msg}."
        if command == '/unapprove':
            notif = "Your account has been reverted to pending status."
        bot.send_message(user_id, notif)
    except:
        pass

@bot.message_handler(commands=['start'])
def handle_start(message):
    users = load_users()
    user_id = str(message.from_user.id)
    
    check_expiration(users, user_id)
    
    if user_id in users:
        status = users[user_id]['status']
        if status == 'approved':
            bot.reply_to(message, "You are already approved. Send me QR code photos!")
        elif status == 'pending':
            bot.reply_to(message, "Your approval is still pending.")
        elif status == 'rejected':
            bot.reply_to(message, "Your request was rejected.")
        return

    name = message.from_user.first_name
    if message.from_user.last_name:
        name += f" {message.from_user.last_name}"
    username = message.from_user.username or "No username"

    users[user_id] = {
        'status': 'pending',
        'name': name,
        'username': username,
        'total_urls': 0,
        'expires_at': None
    }
    save_users(users)
    
    bot.reply_to(message, "Your request has been sent to the admin for approval. Please wait.")
    
    if ADMIN_CHANNEL_ID:
        markup = InlineKeyboardMarkup()
        markup.row_width = 2
        markup.add(
            InlineKeyboardButton("Approve", callback_data=f"approve_{user_id}"),
            InlineKeyboardButton("Reject", callback_data=f"reject_{user_id}")
        )
        admin_text = f"New user request:\nName: {name}\nUsername: @{username}\nUser ID: <code>{user_id}</code>"
        try:
            bot.send_message(ADMIN_CHANNEL_ID, admin_text, reply_markup=markup, parse_mode="HTML")
        except Exception as e:
            print(f"Failed to send to admin channel: {e}")
            bot.send_message(message.chat.id, "Error: The bot failed to send the request to the admin channel. Please check the bot console.")

@bot.channel_post_handler(content_types=['text', 'photo', 'video', 'document'])
def handle_channel_post(message):
    print(f"\n--- Channel Detected! ---")
    print(f"Channel Title: {message.chat.title}")
    print(f"Channel ID: {message.chat.id}")
    print(f"Please copy this ID and put it in bot.py for ADMIN_CHANNEL_ID")
    print(f"-------------------------\n")
    
@bot.callback_query_handler(func=lambda call: call.data.startswith('approve_') or call.data.startswith('reject_'))
def handle_approval(call):
    action, user_id = call.data.split('_')
    users = load_users()
    
    if user_id not in users:
        bot.answer_callback_query(call.id, "User not found in database.")
        return
        
    status = 'approved' if action == 'approve' else 'rejected'
    users[user_id]['status'] = status
    users[user_id]['expires_at'] = None # Clear any previous expirations
    save_users(users)
    
    try:
        bot.send_message(int(user_id), f"Your request has been {status}!")
    except Exception as e:
        print(f"Could not notify user {user_id}: {e}")
        
    bot.edit_message_text(
        chat_id=call.message.chat.id,
        message_id=call.message.message_id,
        text=f"{call.message.text}\n\n<b>Status: {status.upper()}</b>",
        parse_mode="HTML"
    )
    bot.answer_callback_query(call.id, f"User {status}.")

@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    users = load_users()
    user_id = str(message.from_user.id)
    
    check_expiration(users, user_id)
    
    if user_id not in users or users[user_id]['status'] != 'approved':
        bot.reply_to(message, "You are not approved to use this bot.")
        return
        
    try:
        file_info = bot.get_file(message.photo[-1].file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        image = Image.open(io.BytesIO(downloaded_file))
        decoded_objects = decode(image)
        
        url = None
        if decoded_objects:
            url = decoded_objects[0].data.decode('utf-8')
        else:
            url = "No QR found"
            
        group_id = message.media_group_id
        if group_id:
            if group_id not in media_groups:
                media_groups[group_id] = {'chat_id': message.chat.id, 'links': [], 'user_id': user_id}
                timer = threading.Timer(1.5, send_media_group_links, args=(group_id,))
                timer.start()
                media_timers[group_id] = timer
            else:
                if group_id in media_timers:
                    media_timers[group_id].cancel()
                timer = threading.Timer(1.5, send_media_group_links, args=(group_id,))
                timer.start()
                media_timers[group_id] = timer
                
            media_groups[group_id]['links'].append(url)
        else:
            # Single photo stats update
            users[user_id]['total_urls'] = users[user_id].get('total_urls', 0) + 1
            save_users(users)
            bot.send_message(message.chat.id, f"<code>{url}</code>", parse_mode="HTML")
            
    except Exception as e:
        bot.reply_to(message, f"Error processing image: {e}")

if __name__ == '__main__':
    print("Bot is starting...")
    bot.infinity_polling()

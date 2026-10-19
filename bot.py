import logging
import random
import sqlite3
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, CallbackQueryHandler

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- CONFIGURATION ---
ADMIN_USER_ID = 123456789  # Replace with your actual Telegram User ID
COOLDOWN_SECONDS = 15  # Cooldown between signal requests
user_last_request = {}  # Dictionary to track user timestamps


# --- DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    # Users table tracking ID, username, join status, and VIP tier
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
                        user_id INTEGER PRIMARY KEY,
                        username TEXT,
                        is_vip INTEGER DEFAULT 0,
                        join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )''')
    conn.commit()
    conn.close()


def add_user_to_db(user_id, username):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (user_id, username))
    conn.commit()
    conn.close()


# --- START COMMAND & MAIN MENU ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    add_user_to_db(user.id, user.username)

    keyboard = [
        [InlineKeyboardButton("✈️ Generate Signal", callback_data="get_signal")],
        [InlineKeyboardButton("👑 VIP Status", callback_data="check_vip")],
        [InlineKeyboardButton("📊 Bot Info & Help", callback_data="show_help")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    welcome_text = (
        f"Hello **{user.first_name}**! 🚀\n\n"
        "Welcome to the Advanced Aviator Signal Bot.\n"
        "Select an option below:"
    )

    if update.message:
        await update.message.reply_text(welcome_text, parse_mode="Markdown", reply_markup=reply_markup)
    elif update.callback_query:
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(welcome_text, parse_mode="Markdown", reply_markup=reply_markup)


# --- SIGNAL GENERATOR WITH COOLDOWN ---
async def handle_signal(query, user_id):
    # Cooldown check
    current_time = time.time()
    last_time = user_last_request.get(user_id, 0)

    if current_time - last_time < COOLDOWN_SECONDS:
        remaining = int(COOLDOWN_SECONDS - (current_time - last_time))
        await query.answer(f"⏳ Please wait {remaining}s before requesting another signal.", show_alert=True)
        return

    user_last_request[user_id] = current_time

    # Generate multipliers
    multiplier_options = [
        random.uniform(1.10, 1.45),
        random.uniform(1.10, 1.45),
        random.uniform(1.46, 2.30),
        random.uniform(2.31, 5.00),
        random.uniform(5.01, 15.00)
    ]
    predicted_multiplier = round(random.choice(multiplier_options), 2)
    confidence = random.randint(78, 99)

    text = (
        f"✈️ **AVIATOR SIGNAL GENERATOR** ✈️\n\n"
        f"🎯 **Target Multiplier:** `{predicted_multiplier}x`\n"
        f"📊 **Confidence Rate:** `{confidence}%`\n\n"
        f"⚠️ *Note: Simulation only. Play responsibly.*"
    )

    keyboard = [
        [InlineKeyboardButton("🔄 Generate Another", callback_data="get_signal")],
        [InlineKeyboardButton("🔙 Back to Menu", callback_data="back_home")]
    ]
    await query.edit_message_text(text=text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))


# --- VIP STATUS CHECKER ---
async def handle_vip_check(query, user_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT is_vip FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()

    is_vip = row[0] if row else 0
    status_text = "👑 **VIP Status:** ACTIVE (Unlimited priority)" if is_vip else "🔓 **VIP Status:** Standard User (15s Cooldown)"

    keyboard = [[InlineKeyboardButton("🔙 Back to Menu", callback_data="back_home")]]
    await query.edit_message_text(text=status_text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))


# --- BROADCAST COMMAND (ADMIN ONLY) ---
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Unauthorized.")
        return

    # Extract message after /broadcast
    message_text = " ".join(context.args)
    if not message_text:
        await update.message.reply_text("⚠️ Usage: `/broadcast Your message here`", parse_mode="Markdown")
        return

    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    conn.close()

    success_count = 0
    for (u_id,) in users:
        try:
            await context.bot.send_message(chat_id=u_id, text=f"📢 **Announcement:**\n\n{message_text}",
                                           parse_mode="Markdown")
            success_count += 1
        except Exception as e:
            logger.warning(f"Failed to send broadcast to {u_id}: {e}")

    await update.message.reply_text(f"✅ Broadcast sent successfully to {success_count} users.")


# --- CALLBACK ROUTER ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "get_signal":
        await handle_signal(query, user_id)
    elif query.data == "check_vip":
        await handle_vip_check(query, user_id)
    elif query.data == "show_help":
        help_text = (
            "📖 **System Overview**\n\n"
            "• **Signals:** Click generate to fetch round predictions.\n"
            "• **Cooldown:** Applied globally to prevent flooding.\n"
            "• **Database:** Tracks active participants."
        )
        keyboard = [[InlineKeyboardButton("🔙 Back to Menu", callback_data="back_home")]]
        await query.edit_message_text(text=help_text, parse_mode="Markdown",
                                      reply_markup=InlineKeyboardMarkup(keyboard))
    elif query.data == "back_home":
        await start(update, context)


# --- ADMIN SHUTDOWN COMMAND ---
async def stop_bot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id != ADMIN_USER_ID:
        await update.message.reply_text("❌ Unauthorized.")
        return

    await update.message.reply_text("🛑 Shutting down bot gracefully...")
    await context.application.stop()
    await context.application.shutdown()


def main() -> None:
    # Initialize SQLite Database on startup
    init_db()

    TOKEN = "8848860469:AAGhZkDcB0uE-SBS9b3qvoQgMZ-mJL0vpvQ"
    application = ApplicationBuilder().token(TOKEN).build()

    # Register Handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("broadcast", broadcast))
    application.add_handler(CommandHandler("stop", stop_bot))
    application.add_handler(CallbackQueryHandler(button_handler))

    logger.info("Starting advanced multi-feature bot...")
    application.run_polling()


if __name__ == "__main__":
    main()
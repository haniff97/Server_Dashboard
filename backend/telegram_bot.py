
import os

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from ai_agent import analyze_system, get_live_data
from dotenv import load_dotenv


env_path = "/mnt/nvme/Projects/dashboard/.env" 
load_dotenv(env_path)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

async def top(update: Update, context: ContextTypes.DEFAULT_TYPE):

    stats = get_live_data()

    msg = f"🔥 *Top Processes (CPU %):*\n```\n{stats['top_app']}```"

    await update.message.reply_text(msg, parse_mode='Markdown')



async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text("🤖 Consulting Gemini...")

    await update.message.reply_text(analyze_system())



async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):

    s = get_live_data()

    msg = (f"📊 *System Live Stats:*\n"

           f"🌡️ Temp: {s['cpu_temp']}°C\n"

           f"⚙️ CPU: {s['cpu_percent']}%\n"

           f"🧠 RAM: {s['memory_percent']}%")

    await update.message.reply_text(msg, parse_mode='Markdown')



async def reboot(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text("🔄 Rebooting Orange Pi...")

    os.system("sudo reboot")



if __name__ == '__main__':

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("top", top))

    app.add_handler(CommandHandler("status", status))

    app.add_handler(CommandHandler("stats", stats))

    app.add_handler(CommandHandler("reboot", reboot))

    print("Bot is listening...")

    app.run_polling()


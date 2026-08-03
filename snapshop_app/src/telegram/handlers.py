import os
import logging
from pathlib import Path
from typing import Optional, Callable, Awaitable
from telegram import Update
from telegram.ext import (
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
    ApplicationBuilder,
)
from src.config.settings import settings

logger = logging.getLogger(__name__)

# Global state for interactive OTP entry
_pending_otp_future = None


def set_otp_future(future):
    global _pending_otp_future
    _pending_otp_future = future


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    welcome_msg = (
        "🤖 *ربات مدیریت هوشمند قیمت اسنپ‌شاپ (SnappShop)*\n\n"
        "این ربات به‌صورت خودکار قیمت محصولات شما را بر اساس قیمت رقبا پایش و تنظیم می‌کند.\n\n"
        "*دستورات:* \n"
        "• `/status` - مشاهده وضعیت اجرا\n"
        "• `/run_now` - اجرای فوری پایش قیمت\n"
        "• `/set_interval <minutes>` - تغییر بازه زمانی پایش\n\n"
        "📁 می‌توانید فایل Excel/CSV تنظیمات محصولات را نیز مستقیماً ارسال کنید."
    )
    await update.message.reply_text(welcome_msg, parse_mode="Markdown")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /status command."""
    status_msg = (
        "⚙️ *وضعیت ربات اسنپ‌شاپ*\n\n"
        f"⏱ بازه پایش: هر *{settings.CHECK_INTERVAL_MINUTES}* دقیقه\n"
        f"📱 شماره فروشگاه: `{settings.SNAPSHOP_PHONE_NUMBER or 'تنظیم نشده'}`\n"
        f"🏢 نام فروشگاه: *{settings.SNAPSHOP_COMPANY_NAME}*\n"
        f"🟢 وضعیت: *فعال و آماده*"
    )
    await update.message.reply_text(status_msg, parse_mode="Markdown")


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive and save Excel/CSV config files uploaded via Telegram."""
    document = update.message.document
    filename = document.file_name

    if not filename.endswith((".xlsx", ".csv", ".xls")):
        await update.message.reply_text("❌ لطفاً یک فایل Excel (.xlsx) یا CSV معتبر ارسال کنید.")
        return

    file = await context.bot.get_file(document.file_id)
    save_path = settings.DOWNLOADS_DIR / f"telegram_upload_{filename}"
    await file.download_to_drive(str(save_path))

    await update.message.reply_text(
        f"✅ فایل با موفقیت دریافت و ذخیره شد:\n`{filename}`\n\n"
        f"تنظیمات محصولات در چرخه بعدی اجرا اعمال خواهند شد.",
        parse_mode="Markdown",
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle plain text messages (e.g., OTP code entry)."""
    global _pending_otp_future
    text = update.message.text.strip()

    if _pending_otp_future and not _pending_otp_future.done():
        if text.isdigit() and len(text) in (4, 5, 6):
            _pending_otp_future.set_result(text)
            await update.message.reply_text(f"✅ کد OTP دریافت شد: `{text}`", parse_mode="Markdown")
            return

    await update.message.reply_text("کد یا دستور ناشناخته. برای راهنمایی /start را بزنید.")

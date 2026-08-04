import os
import asyncio
import logging
from pathlib import Path
from typing import Optional
import pandas as pd

from telegram import Update
from telegram.ext import ContextTypes

from src.config.settings import settings
from src.core.database import DatabaseManager
from src.core.scraper import normalize_persian_text

logger = logging.getLogger(__name__)

# Global state for interactive OTP entry
_pending_otp_future = None
_is_sync_running = False


def set_otp_future(future):
    global _pending_otp_future
    _pending_otp_future = future


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    welcome_msg = (
        "🤖 *ربات مدیریت هوشمند قیمت اسنپ‌شاپ (SnappShop)*\n\n"
        "این ربات به‌صورت خودکار قیمت محصولات شما را بر اساس قیمت رقبا پایش و تنظیم می‌کند.\n\n"
        "*دستورات:* \n"
        "• `/status` - مشاهده وضعیت اجرا و تنظیمات\n"
        "• `/run_now` - اجرای فوری پایش قیمت\n"
        "• `/set_interval <minutes>` - تغییر بازه زمانی پایش (مثلاً `/set_interval 60` برای ۱ ساعت)\n\n"
        "📁 *ارسال فایل محصولات:* می‌توانید فایل Excel (.xlsx) یا CSV محصولات شامل قیمت، حداقل، حداکثر و گام تغییرات را مستقیماً ارسال کنید تا ربات آن را خوانده و در دیتابیس اعمال کند."
    )
    await update.message.reply_text(welcome_msg, parse_mode="Markdown")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /status command."""
    db_mgr = DatabaseManager(settings.DATABASE_PATH)
    status_msg = (
        "⚙️ *وضعیت ربات اسنپ‌شاپ*\n\n"
        f"⏱ بازه پایش: هر *{settings.CHECK_INTERVAL_MINUTES}* دقیقه\n"
        f"📱 شماره فروشگاه: `{settings.SNAPSHOP_PHONE_NUMBER or 'تنظیم نشده'}`\n"
        f"🏢 نام فروشگاه: *{settings.SNAPSHOP_COMPANY_NAME}*\n"
        f"🟢 وضعیت: *فعال و آماده*"
    )
    await update.message.reply_text(status_msg, parse_mode="Markdown")


async def run_now_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /run_now command to trigger an immediate price sync cycle."""
    global _is_sync_running
    if _is_sync_running:
        await update.message.reply_text("⚠️ یک چرخه پایش قیمت در حال حاضر در حال اجرا است.")
        return

    await update.message.reply_text("🚀 چرخه پایش فوری قیمت شروع شد. پس از اتمام نتیجه گزارش می‌شود...")
    _is_sync_running = True

    async def run_task():
        global _is_sync_running
        try:
            from src.scheduler.job_runner import run_sync_cycle
            res = await run_sync_cycle()
            if res:
                await update.message.reply_text("✅ *چرخه پایش قیمت با موفقیت به پایان رسید.*", parse_mode="Markdown")
            else:
                await update.message.reply_text("❌ *خطا در اجرای چرخه پایش قیمت.*", parse_mode="Markdown")
        except Exception as err:
            logger.error(f"Error running manual sync via Telegram: {err}")
            await update.message.reply_text(f"❌ خطا: `{err}`", parse_mode="Markdown")
        finally:
            _is_sync_running = False

    asyncio.create_task(run_task())


async def set_interval_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /set_interval <minutes> command to dynamically change check frequency."""
    if not context.args or not context.args[0].isdigit():
        await update.message.reply_text(
            "❌ لطفاً بازه زمانی را به دقیقه مشخص کنید.\nمثال: `/set_interval 60` (برای ۱ ساعت)",
            parse_mode="Markdown",
        )
        return

    minutes = int(context.args[0])
    if minutes < 1:
        await update.message.reply_text("❌ بازه زمانی باید حداقل ۱ دقیقه باشد.")
        return

    settings.CHECK_INTERVAL_MINUTES = minutes

    # Update .env file
    try:
        env_path = Path(__file__).resolve().parent.parent.parent / ".env"
        if env_path.exists():
            lines = env_path.read_text(encoding="utf-8").splitlines()
            new_lines = []
            updated = False
            for line in lines:
                if line.startswith("CHECK_INTERVAL_MINUTES="):
                    new_lines.append(f"CHECK_INTERVAL_MINUTES={minutes}")
                    updated = True
                else:
                    new_lines.append(line)
            if not updated:
                new_lines.append(f"CHECK_INTERVAL_MINUTES={minutes}")
            env_path.write_text("\n".join(new_lines), encoding="utf-8")
    except Exception as e:
        logger.warning(f"Could not update .env file: {e}")

    await update.message.reply_text(
        f"✅ *بازه زمانی پایش قیمت به {minutes} دقیقه تغییر یافت.*\n"
        f"از این پس پایش هر *{minutes}* دقیقه اجرا خواهد شد.",
        parse_mode="Markdown",
    )


def parse_int_value(val) -> Optional[int]:
    if val is None or pd.isna(val):
        return None
    s = str(val).strip()
    if not s:
        return None
    s = normalize_persian_text(s)
    s = s.replace(",", "").replace("،", "").replace(" ", "").replace("_", "")
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return None


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive, parse, and store product settings from uploaded Excel/CSV files."""
    document = update.message.document
    filename = document.file_name

    if not filename.endswith((".xlsx", ".csv", ".xls")):
        await update.message.reply_text("❌ لطفاً یک فایل Excel (.xlsx) یا CSV معتبر ارسال کنید.")
        return

    await update.message.reply_text(f"📥 در حال دانلود و پردازش فایل `{filename}`...", parse_mode="Markdown")

    file = await context.bot.get_file(document.file_id)
    save_path = settings.DOWNLOADS_DIR / f"telegram_upload_{filename}"
    save_path.parent.mkdir(parents=True, exist_ok=True)
    await file.download_to_drive(str(save_path))

    try:
        # Read Excel or CSV file
        if filename.endswith(".csv"):
            df = pd.read_csv(save_path)
        else:
            df = pd.read_excel(save_path)

        # Identify Column Mapping
        title_col = None
        min_col = None
        max_col = None
        inc_col = None
        dec_col = None
        price_col = None

        for col in df.columns:
            clean_c = str(col).strip()
            norm_c = normalize_persian_text(clean_c).lower()

            if any(k in norm_c for k in ["عنوان", "title", "product", "کالا", "نام"]):
                if not title_col:
                    title_col = col
            elif any(k in norm_c for k in ["حداقل", "min", "کف"]):
                min_col = col
            elif any(k in norm_c for k in ["حداکثر", "max", "سقف"]):
                max_col = col
            elif any(k in norm_c for k in ["افزایش", "increase", "گام افزایش"]):
                inc_col = col
            elif any(k in norm_c for k in ["کاهش", "decrease", "گام کاهش"]):
                dec_col = col
            elif any(k in norm_c for k in ["قیمت", "price", "قیمت پایه"]):
                if not price_col:
                    price_col = col

        if not title_col:
            title_col = df.columns[0]

        products_list = []
        for idx, row in df.iterrows():
            title = str(row[title_col]).strip() if pd.notna(row[title_col]) else ""
            if not title:
                continue

            min_p = parse_int_value(row[min_col]) if min_col else None
            max_p = parse_int_value(row[max_col]) if max_col else None
            inc_s = parse_int_value(row[inc_col]) if inc_col else None
            dec_s = parse_int_value(row[dec_col]) if dec_col else None
            last_p = parse_int_value(row[price_col]) if price_col else None

            products_list.append({
                "product_title": title,
                "min_price": min_p,
                "max_price": max_p,
                "increase_step": inc_s,
                "decrease_step": dec_s,
                "last_price": last_p,
            })

        db_mgr = DatabaseManager(settings.DATABASE_PATH)
        imported_count = db_mgr.bulk_import_product_rules(products_list)

        sample_lines = ""
        for p in products_list[:5]:
            min_str = f"{p['min_price']:,}" if p['min_price'] else "پیش‌فرض"
            max_str = f"{p['max_price']:,}" if p['max_price'] else "پیش‌فرض"
            sample_lines += f"• `{p['product_title'][:30]}` | حداقل: {min_str} | حداکثر: {max_str}\n"

        reply_msg = (
            f"✅ *فایل با موفقیت دریافت و پردازش شد!*\n\n"
            f"📊 **آمار پردازش فایل:**\n"
            f"• نام فایل: `{filename}`\n"
            f"• تعداد کل سطرها: *{len(df)}*\n"
            f"• قوانین قیمت‌گذاری بروزشده: *{imported_count}*\n\n"
            f"📋 **نمونه محصولات بروزشده:**\n{sample_lines}\n"
            f"⚙️ **توضیحات:**\n"
            f"تنظیمات جدید در دیتابیس ثبت شدند و در چرخه‌های پایش پیاپی (هر *{settings.CHECK_INTERVAL_MINUTES}* دقیقه) به طور خودکار بر روی فروشگاه اسنپ‌شاپ اعمال خواهند شد."
        )
        await update.message.reply_text(reply_msg, parse_mode="Markdown")

    except Exception as e:
        logger.error(f"Error processing Telegram document {filename}: {e}")
        await update.message.reply_text(f"❌ خطا در پردازش فایل: `{e}`", parse_mode="Markdown")


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

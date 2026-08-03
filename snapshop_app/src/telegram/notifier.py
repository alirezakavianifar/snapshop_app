import logging
from typing import Optional, List, Dict, Any
from src.config.settings import settings

logger = logging.getLogger(__name__)

try:
    from telegram import Bot
    HAS_TELEGRAM = True
except ImportError:
    HAS_TELEGRAM = False
    Bot = None


class TelegramNotifier:
    """Sends structured notification reports and alerts to the Telegram admin chat."""

    def __init__(self, bot_token: Optional[str] = None, admin_chat_id: Optional[str] = None):
        self.bot_token = bot_token or settings.TELEGRAM_BOT_TOKEN
        self.admin_chat_id = admin_chat_id or settings.TELEGRAM_ADMIN_CHAT_ID

    async def _send_message(self, text: str):
        if not HAS_TELEGRAM or not self.bot_token or not self.admin_chat_id:
            logger.info(f"[Telegram Notification Skip]\n{text}")
            return
        try:
            bot = Bot(token=self.bot_token)
            await bot.send_message(
                chat_id=self.admin_chat_id,
                text=text,
                parse_mode="Markdown",
            )
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")

    async def send_status_report(self, updated_count: int, skipped_count: int, changes: List[Dict[str, Any]]):
        """Send price sync execution report."""
        msg = f"📊 *گزارش همگام‌سازی قیمت اسنپ‌شاپ*\n\n"
        msg += f"✅ تعداد تغییرات قیمت: *{updated_count}*\n"
        msg += f"⏳ تعداد محصولات بدون تغییر/رد شده (قانون 24 ساعته): *{skipped_count}*\n\n"

        if changes:
            msg += "*جزئیات تغییرات قیمت:*\n"
            for c in changes[:10]:  # Limit top 10 changes
                msg += f"• `{c['title'][:30]}`: {c['old_price']:,} ➔ *{c['new_price']:,}* تومان\n"
                if c.get("competitor_price"):
                    msg += f"  (قیمت رقیب: {c['competitor_price']:,})\n"

            if len(changes) > 10:
                msg += f"\n... و {len(changes) - 10} تغییر دیگر."

        await self._send_message(msg)

    async def send_error_alert(self, error_msg: str):
        """Send error alert notification."""
        msg = f"⚠️ *خطای اجرای ربات اسنپ‌شاپ*\n\n`{error_msg}`"
        await self._send_message(msg)

    async def send_otp_request(self, phone_number: str):
        """Request OTP code from admin via Telegram."""
        msg = (
            f"🔐 *درخواست کد تایید OTP اسنپ‌شاپ*\n\n"
            f"کد تایید پیامک شده به شماره `{phone_number}` را ارسال کنید."
        )
        await self._send_message(msg)

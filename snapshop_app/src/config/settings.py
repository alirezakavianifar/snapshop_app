import os
import sys
from pathlib import Path
from typing import Optional

if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
    meipass_dir = Path(getattr(sys, "_MEIPASS", sys.executable)).resolve()
    if meipass_dir.exists() and str(meipass_dir) not in sys.path:
        sys.path.insert(0, str(meipass_dir))
    internal_dir = BASE_DIR / "_internal"
    if internal_dir.exists() and str(internal_dir) not in sys.path:
        sys.path.insert(0, str(internal_dir))
else:
    BASE_DIR = Path(__file__).resolve().parent.parent.parent

try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass


class Settings:
    # Telegram Bot Settings
    TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_ADMIN_CHAT_ID: Optional[str] = os.getenv("TELEGRAM_ADMIN_CHAT_ID", None)
    TELEGRAM_PROXY_URL: Optional[str] = os.getenv("TELEGRAM_PROXY_URL", None)

    # SnappShop Seller Panel Credentials
    SNAPSHOP_PHONE_NUMBER: str = os.getenv("SNAPSHOP_PHONE_NUMBER", "09207051391")
    SNAPSHOP_PASSWORD: Optional[str] = os.getenv("SNAPSHOP_PASSWORD", "Roya9084@")
    SNAPSHOP_STORE_URL: str = os.getenv(
        "SNAPSHOP_STORE_URL", "https://snappshop.ir/seller/qP4j1w"
    )
    SNAPSHOP_COMPANY_NAME: str = os.getenv("SNAPSHOP_COMPANY_NAME", "گالری فیگارو")

    # Bot Execution Config
    CHECK_INTERVAL_MINUTES: int = int(os.getenv("CHECK_INTERVAL_MINUTES", "20"))
    DOWNLOADS_DIR: Path = BASE_DIR / os.getenv("DOWNLOADS_DIR", "downloads")
    SESSION_STATE_FILE: Path = BASE_DIR / os.getenv(
        "SESSION_STATE_FILE", "downloads/storage_state.json"
    )
    DATABASE_PATH: Path = BASE_DIR / os.getenv("DATABASE_PATH", "downloads/bot_state.db")

    # Default Product Pricing Steps (in Tomans)
    DEFAULT_INCREASE_STEP: int = int(os.getenv("DEFAULT_INCREASE_STEP", "1000"))
    DEFAULT_DECREASE_STEP: int = int(os.getenv("DEFAULT_DECREASE_STEP", "1000"))

    def __init__(self):
        self.DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
        self.SESSION_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        self.DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)


settings = Settings()

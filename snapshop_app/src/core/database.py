import os
import sqlite3
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class DatabaseManager:
    """SQLite state manager for tracking product checks, competitor presence, and history."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self):
        return sqlite3.connect(str(self.db_path))

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS product_state (
                    product_title TEXT PRIMARY KEY,
                    has_competitors INTEGER NOT NULL DEFAULT 0,
                    last_checked_at TEXT NOT NULL,
                    last_price INTEGER,
                    min_price INTEGER,
                    max_price INTEGER,
                    increase_step INTEGER,
                    decrease_step INTEGER
                )
            """)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS price_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_title TEXT NOT NULL,
                    old_price INTEGER,
                    new_price INTEGER,
                    competitor_price INTEGER,
                    reason TEXT,
                    timestamp TEXT NOT NULL
                )
            """)
            conn.commit()
            logger.info(f"Database initialized at {self.db_path}")

    def should_check_product(self, product_title: str) -> bool:
        """
        Check if a product needs scraping/updating based on competitor status and 24-hour rule.
        Products without competitors are checked only once per 24 hours.
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT has_competitors, last_checked_at FROM product_state WHERE product_title = ?",
                (product_title,),
            )
            row = cursor.fetchone()
            if not row:
                return True  # Never checked before

            has_competitors, last_checked_str = row
            if has_competitors == 1:
                return True  # Always check active competitor products on schedule

            # Competitor-less product check: 24h rule
            try:
                last_checked = datetime.fromisoformat(last_checked_str)
                if datetime.now() - last_checked < timedelta(hours=24):
                    logger.debug(f"Skipping product '{product_title}': checked < 24h ago without competitors.")
                    return False
            except Exception as e:
                logger.warning(f"Error parsing date {last_checked_str}: {e}")
                return True

            return True

    def update_product_state(
        self,
        product_title: str,
        has_competitors: bool,
        last_price: Optional[int] = None,
        min_price: Optional[int] = None,
        max_price: Optional[int] = None,
        increase_step: Optional[int] = None,
        decrease_step: Optional[int] = None,
    ):
        now_str = datetime.now().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO product_state (
                    product_title, has_competitors, last_checked_at, last_price,
                    min_price, max_price, increase_step, decrease_step
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(product_title) DO UPDATE SET
                    has_competitors = excluded.has_competitors,
                    last_checked_at = excluded.last_checked_at,
                    last_price = COALESCE(excluded.last_price, last_price),
                    min_price = COALESCE(excluded.min_price, min_price),
                    max_price = COALESCE(excluded.max_price, max_price),
                    increase_step = COALESCE(excluded.increase_step, increase_step),
                    decrease_step = COALESCE(excluded.decrease_step, decrease_step)
            """,
                (
                    product_title,
                    1 if has_competitors else 0,
                    now_str,
                    last_price,
                    min_price,
                    max_price,
                    increase_step,
                    decrease_step,
                ),
            )
            conn.commit()

    def log_price_change(
        self,
        product_title: str,
        old_price: Optional[int],
        new_price: int,
        competitor_price: Optional[int],
        reason: str,
    ):
        now_str = datetime.now().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO price_history (product_title, old_price, new_price, competitor_price, reason, timestamp)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (product_title, old_price, new_price, competitor_price, reason, now_str),
            )
            conn.commit()

    def bulk_import_product_rules(self, products_list: list) -> int:
        """
        Bulk upsert custom product pricing rules (min_price, max_price, increase_step, decrease_step)
        from Excel/CSV files uploaded via Telegram or UI.
        """
        now_str = datetime.now().isoformat()
        count = 0
        with self._get_connection() as conn:
            cursor = conn.cursor()
            for prod in products_list:
                title = prod.get("product_title")
                if not title:
                    continue

                cursor.execute(
                    """
                    INSERT INTO product_state (
                        product_title, has_competitors, last_checked_at, last_price,
                        min_price, max_price, increase_step, decrease_step
                    ) VALUES (?, 0, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(product_title) DO UPDATE SET
                        last_price = COALESCE(excluded.last_price, last_price),
                        min_price = COALESCE(excluded.min_price, min_price),
                        max_price = COALESCE(excluded.max_price, max_price),
                        increase_step = COALESCE(excluded.increase_step, increase_step),
                        decrease_step = COALESCE(excluded.decrease_step, decrease_step)
                """,
                    (
                        title,
                        now_str,
                        prod.get("last_price"),
                        prod.get("min_price"),
                        prod.get("max_price"),
                        prod.get("increase_step"),
                        prod.get("decrease_step"),
                    ),
                )
                count += 1
            conn.commit()
        logger.info(f"Bulk imported custom rules for {count} products into database.")
        return count

    def get_product_rules(self, product_title: str) -> Optional[Dict[str, Any]]:
        """Retrieve stored pricing rules for a given product title."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT min_price, max_price, increase_step, decrease_step, last_price FROM product_state WHERE product_title = ?",
                (product_title,),
            )
            row = cursor.fetchone()
            if row:
                return {
                    "min_price": row[0],
                    "max_price": row[1],
                    "increase_step": row[2],
                    "decrease_step": row[3],
                    "last_price": row[4],
                }
            return None

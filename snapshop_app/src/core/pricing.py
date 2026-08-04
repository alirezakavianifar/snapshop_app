import os
import re
import logging
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
import pandas as pd
import numpy as np
import jdatetime
import pytz
from datetime import datetime
from openpyxl import load_workbook
from src.config.settings import settings
from src.core.database import DatabaseManager

logger = logging.getLogger(__name__)


def calculate_product_price(
    current_price: int,
    competitor_price: Optional[int],
    min_price: Optional[int] = None,
    max_price: Optional[int] = None,
    increase_step: int = 1000,
    decrease_step: int = 1000,
) -> Tuple[int, str]:
    """
    Calculate new competitive price based on competitor status, min/max bounds, and steps.
    """
    # Fallback bounds if not explicitly provided
    if min_price is None or min_price <= 0:
        min_price = int(current_price * 0.7)  # Floor protection: max 30% drop below current
    if max_price is None or max_price <= 0:
        max_price = int(current_price * 1.5)  # Ceiling protection

    # Case 1: No competitor exists -> Maintain current price
    if competitor_price is None or competitor_price <= 0:
        return current_price, "No competitor: maintaining current price"

    # Case 2: Competitor is cheaper than our current price -> Reduce price by decrease_step
    if competitor_price < current_price:
        target_price = competitor_price - decrease_step
        if target_price < min_price:
            new_price = min_price
            reason = f"Competitor at {competitor_price}: target {target_price} below min_price ({min_price})"
        else:
            new_price = target_price
            reason = f"Competitor at {competitor_price}: reduced by step ({decrease_step})"
        return new_price, reason

    # Case 3: Competitor is higher than our current price -> Increase price up towards competitor price
    if competitor_price > current_price:
        target_price = competitor_price - decrease_step
        if target_price > max_price:
            new_price = max_price
            reason = f"Competitor at {competitor_price}: capped at max_price ({max_price})"
        elif target_price > current_price:
            new_price = min(target_price, current_price + increase_step)
            reason = f"Competitor increased to {competitor_price}: stepping up price"
        else:
            new_price = current_price
            reason = "Already optimally priced relative to competitor"
        return new_price, reason

    return current_price, "No price change required"


def clean_title_key(title: str) -> str:
    """
    Clean and normalize product titles for robust matching between Excel catalog and Web Scraper.
    Strips 'وزن:', 'گارانتی سلامت فیزیکی کالا 1 ماه', ZWNJ, and extra spaces.
    """
    if not title:
        return ""
    from src.core.scraper import normalize_persian_text
    t = normalize_persian_text(title)
    t = re.sub(r"وزن\s*:\s*", "", t)
    t = re.sub(r"گارانتی\s+سلامت\s+فیزیکی\s+کالا\s+\d+\s+ماه", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def process_inventory_and_generate_update(
    excel_path: Path,
    competitors_data: List[Dict[str, Any]],
    output_path: Path,
    db_manager: DatabaseManager,
) -> Dict[str, Any]:
    """
    Read inventory Excel, apply competitor pricing strategy & Telegram custom rules,
    and save updated 01.xlsx file ready for SnappShop seller panel upload.
    """
    logger.info(f"Reading downloaded inventory Excel: {excel_path}")
    df = pd.read_excel(excel_path)

    # Filter active products with discounts
    if "فعال" in df.columns:
        df = df[df["فعال"] != 0]
    if "تخفیف دارد" in df.columns:
        df = df[df["تخفیف دارد"] != 0]

    # Set current Persian date & Tehran time
    current_persian_date = jdatetime.date.today().strftime("%Y/%m/%d")
    tehran_tz = pytz.timezone("Asia/Tehran")
    current_time_str = datetime.now(tehran_tz).strftime("%H:%M")

    if "تاریخ شروع تخفیف" in df.columns:
        df["تاریخ شروع تخفیف"] = current_persian_date
    if "زمان شروع تخفیف" in df.columns:
        df["زمان شروع تخفیف"] = current_time_str

    # Build normalized competitor map from scraped data
    comp_map = {}
    for item in competitors_data:
        t_key = clean_title_key(item.get("title", ""))
        if t_key:
            comp_map[t_key] = item

    updated_count = 0
    skipped_count = 0
    price_changes = []

    title_col = "عنوان کالا" if "عنوان کالا" in df.columns else df.columns[0]
    price_col = (
        "قیمت بعد از تخفیف به تومان"
        if "قیمت بعد از تخفیف به تومان" in df.columns
        else "قیمت"
    )

    new_prices = []

    for idx, row in df.iterrows():
        title = str(row[title_col]).strip()
        current_p = int(row[price_col]) if pd.notna(row[price_col]) else 0

        # Read optional custom bounds from Excel or fallback to database rules stored from Telegram uploads
        db_rules = db_manager.get_product_rules(title) or {}

        min_p = (
            int(row["قیمت حداقل"])
            if "قیمت حداقل" in df.columns and pd.notna(row["قیمت حداقل"])
            else db_rules.get("min_price")
        )
        max_p = (
            int(row["قیمت حداکثر"])
            if "قیمت حداکثر" in df.columns and pd.notna(row["قیمت حداکثر"])
            else db_rules.get("max_price")
        )
        inc_step = (
            int(row["گام افزایش قیمت"])
            if "گام افزایش قیمت" in df.columns and pd.notna(row["گام افزایش قیمت"])
            else (db_rules.get("increase_step") or settings.DEFAULT_INCREASE_STEP)
        )
        dec_step = (
            int(row["گام کاهش قیمت"])
            if "گام کاهش قیمت" in df.columns and pd.notna(row["گام کاهش قیمت"])
            else (db_rules.get("decrease_step") or settings.DEFAULT_DECREASE_STEP)
        )

        norm_title = clean_title_key(title)
        comp_info = comp_map.get(norm_title, {})
        
        # Read direct Buybox information from Inventory Excel row
        excel_buybox_price = (
            int(row["قیمت بای باکس"])
            if "قیمت بای باکس" in df.columns and pd.notna(row["قیمت بای باکس"]) and row["قیمت بای باکس"] > 0
            else None
        )
        # Determine Buybox Winner: live scraper storefront status takes priority over Excel export
        if "live_is_buybox_winner" in comp_info:
            is_buybox_winner = comp_info["live_is_buybox_winner"]
        else:
            is_buybox_winner = (
                str(row["برنده بای باکس"]).strip() == "بله"
                if "برنده بای باکس" in df.columns and pd.notna(row["برنده بای باکس"])
                else True
            )

        # Scraped web competitor price overrides static excel export price if available
        scraped_comp_price = comp_info.get("second_price", None)
        if scraped_comp_price and scraped_comp_price > 0:
            comp_price = scraped_comp_price
            has_comp = True
        elif excel_buybox_price and excel_buybox_price > 0:
            comp_price = excel_buybox_price
            has_comp = True
        else:
            has_comp = False
            comp_price = None

        # Check 24-hour rule for competitor-less items
        if not db_manager.should_check_product(title):
            skipped_count += 1
            new_prices.append(current_p)
            continue

        # Core Buybox Winner Strategy Logic
        if has_comp and comp_price and comp_price > 0:
            if not is_buybox_winner:
                # We are NOT winning the Buybox -> Undercut competitor to WIN Buybox!
                target_p = comp_price - dec_step
                floor_min = min_p if (min_p and min_p > 0) else int(current_p * 0.7)
                calculated_p = max(target_p, floor_min)
                reason = f"Not Buybox winner: undercutting competitor ({comp_price:,}) to win Buybox"
            else:
                # We ARE the Buybox winner -> Maintain current price
                calculated_p = current_p
                reason = "Already Buybox winner: maintaining current price"
        else:
            calculated_p, reason = calculate_product_price(
                current_price=current_p,
                competitor_price=comp_price,
                min_price=min_p,
                max_price=max_p,
                increase_step=inc_step,
                decrease_step=dec_step,
            )

        db_manager.update_product_state(
            product_title=title,
            has_competitors=has_comp,
            last_price=calculated_p,
            min_price=min_p,
            max_price=max_p,
            increase_step=inc_step,
            decrease_step=dec_step,
        )

        if calculated_p != current_p:
            updated_count += 1
            db_manager.log_price_change(
                product_title=title,
                old_price=current_p,
                new_price=calculated_p,
                competitor_price=comp_price,
                reason=reason,
            )
            price_changes.append({
                "title": title,
                "old_price": current_p,
                "new_price": calculated_p,
                "competitor_price": comp_price,
                "reason": reason,
            })

        new_prices.append(calculated_p)

    df[price_col] = new_prices

    # Save output Excel
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet_name = "فهرست محصولات"
    df.to_excel(str(output_path), index=False, sheet_name=sheet_name)

    # Set Right-to-Left formatting
    wb = load_workbook(str(output_path))
    ws = wb.active
    ws.sheet_view.rightToLeft = True
    wb.save(str(output_path))

    logger.info(f"Generated updated Excel file at {output_path}. Updated: {updated_count}, Skipped (24h rule): {skipped_count}")

    return {
        "output_path": output_path,
        "updated_count": updated_count,
        "skipped_count": skipped_count,
        "price_changes": price_changes,
    }

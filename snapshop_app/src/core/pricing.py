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
    strategy_mode: str = "SMART_HYBRID",
    consecutive_floor_count: int = 0,
) -> Tuple[int, str, int, str]:
    """
    Calculate new competitive price using Smart Hybrid strategy (Price Matching + Reset Probe).
    Returns (new_price, reason, new_consecutive_floor_count, strategy_action).
    """
    if min_price is None or min_price <= 0:
        min_price = int(current_price * 0.7)  # Floor protection: max 30% drop
    if max_price is None or max_price <= 0:
        max_price = int(current_price * 1.5)  # Ceiling protection

    # Case 1: No competitor exists -> Maintain current price
    if competitor_price is None or competitor_price <= 0:
        return current_price, "No competitor: maintaining current price", 0, "MAINTAIN"

    # Strategy Option: PROBE_RESET Check (Escape Price War Traps)
    # If price has been stuck near min_price for >= threshold consecutive cycles, execute a Probe Reset!
    threshold = getattr(settings, "PROBE_RESET_THRESHOLD", 3)
    bounce_pct = getattr(settings, "PROBE_RESET_BOUNCE_PERCENT", 0.15)
    
    is_at_floor = current_price <= (min_price + decrease_step)
    
    if strategy_mode == "SMART_HYBRID" and is_at_floor and consecutive_floor_count >= (threshold - 1):
        bounce_price = min(max_price, int(current_price * (1 + bounce_pct)))
        reason = f"PROBE RESET: Stuck near floor ({current_price:,}) for {consecutive_floor_count + 1} cycles. Bouncing price to {bounce_price:,} to reset market."
        return bounce_price, reason, 0, "PROBED"

    # Case 2: Competitor is cheaper than or equal to our current price
    if competitor_price <= current_price:
        if strategy_mode == "MATCH":
            target_price = competitor_price
            action = "MATCHED"
        else:
            # SMART_HYBRID & UNDERCUT: Undercut by step to guarantee winning the Buybox!
            target_price = competitor_price - decrease_step
            action = "UNDERCUT"

        if target_price < min_price:
            new_price = min_price
            new_floor_count = consecutive_floor_count + 1
            reason = f"Competitor at {competitor_price:,}: target below min_price ({min_price:,}). Capped at floor."
        else:
            new_price = target_price
            new_floor_count = consecutive_floor_count + 1 if new_price <= (min_price + decrease_step) else 0
            reason = f"Competitor at {competitor_price:,}: {action.lower()} price to {new_price:,}"
        return new_price, reason, new_floor_count, action

    # Case 3: Competitor is higher than our current price -> Step up towards competitor price
    if competitor_price > current_price:
        target_price = competitor_price if strategy_mode in ("SMART_HYBRID", "MATCH") else (competitor_price - decrease_step)
        if target_price > max_price:
            new_price = max_price
            reason = f"Competitor at {competitor_price:,}: capped at max_price ({max_price:,})"
        elif target_price > current_price:
            new_price = min(target_price, current_price + increase_step)
            reason = f"Competitor higher at {competitor_price:,}: stepping up price to {new_price:,}"
        else:
            new_price = current_price
            reason = "Optimally priced relative to competitor"
        return new_price, reason, 0, "STEP_UP"

    # Case 4: Equal price
    return current_price, "Prices equal: maintaining position", 0, "MATCHED"


def clean_title_key(title: str) -> str:
    """
    Clean and normalize product titles for robust matching between Excel catalog and Web Scraper.
    Strips 'وزن:', 'گارانتی سلامت فیزیکی کالا 1 ماه', ZWNJ, extra spaces, and normalizes digits.
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

        if not comp_info:
            # Robust fuzzy/numeric token matching for catalog title mismatches (e.g. 'گوشواره' vs 'پلاک')
            title_tokens = set(norm_title.split())
            def extract_numbers(text):
                return set(re.findall(r"\d+\.?\d*", text))
            def get_float_values(num_strings):
                floats = set()
                for ns in num_strings:
                    try:
                        floats.add(float(ns))
                    except ValueError:
                        pass
                return floats

            title_floats = get_float_values(extract_numbers(norm_title))
            title_weights = {f for f in title_floats if f < 5.0}

            best_match_key = None
            best_match_score = 0

            for scraped_key, scraped_item in comp_map.items():
                scraped_tokens = set(scraped_key.split())
                scraped_floats = get_float_values(extract_numbers(scraped_key))
                scraped_weights = {f for f in scraped_floats if f < 5.0}

                # Weights (floats < 5.0) must match exactly
                if title_weights and scraped_weights:
                    # If one of the weights is different, mismatch
                    # Let's ensure the intersection of weights is non-empty
                    if not title_weights.intersection(scraped_weights):
                        continue
                elif title_weights != scraped_weights:
                    # One has weight and the other doesn't
                    continue

                # Ensure main model number/karat overlaps (e.g. 18 karat, or model code 9)
                if not title_floats.intersection(scraped_floats):
                    continue

                # Exclude extremely common gold catalog stop words to prevent false matching collisions
                STOP_WORDS = {"طلا", "18", "عیار", "زنانه", "گرم", "مدل", "طرح", "کد", "آویز", "پلاک", "گردنبند", "گوشواره"}
                title_unique = title_tokens - STOP_WORDS
                scraped_unique = scraped_tokens - STOP_WORDS
                token_overlap = title_unique.intersection(scraped_unique)
                score = len(token_overlap)
                if score > best_match_score and score >= 2:
                    best_match_score = score
                    best_match_key = scraped_key

            if best_match_key:
                comp_info = comp_map[best_match_key]
                logger.info(f"Fuzzy matched Excel product '{title}' with scraped storefront '{comp_info.get('title')}' (Score: {best_match_score})")
        
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

        # Check 24-hour rule for competitor-less items (only if live scraper also found no competitor)
        if not has_comp and not db_manager.should_check_product(title):
            skipped_count += 1
            new_prices.append(current_p)
            continue

        # Core Buybox Winner Strategy Logic
        strat_state = db_manager.get_product_strategy_state(title)
        floor_count = strat_state.get("consecutive_floor_count", 0)
        strategy_mode = getattr(settings, "REPRICING_STRATEGY", "SMART_HYBRID")

        if is_buybox_winner:
            calculated_p = current_p
            reason = "Already Buybox winner: maintaining current price"
            new_floor_count = 0
            action = "MAINTAIN"
        else:
            calculated_p, reason, new_floor_count, action = calculate_product_price(
                current_price=current_p,
                competitor_price=comp_price,
                min_price=min_p,
                max_price=max_p,
                increase_step=inc_step,
                decrease_step=dec_step,
                strategy_mode=strategy_mode,
                consecutive_floor_count=floor_count,
            )

        db_manager.update_product_strategy_state(
            product_title=title,
            consecutive_floor_count=new_floor_count,
            last_strategy_action=action,
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

    base_p_col = "قیمت به تومان"
    disc_p_col = "قیمت بعد از تخفیف به تومان"
    
    # Assign prices based on discount flag for each row
    if base_p_col in df.columns and disc_p_col in df.columns and "تخفیف دارد" in df.columns:
        updated_base = []
        updated_disc = []
        for row_idx, (_, row) in enumerate(df.iterrows()):
            new_p = new_prices[row_idx]
            has_d = (row.get("تخفیف دارد") == 1)
            old_base = row.get(base_p_col, new_p)
            if pd.isna(old_base): old_base = new_p
            
            if has_d:
                updated_disc.append(new_p)
                updated_base.append(max(int(old_base), int(new_p)))
            else:
                updated_base.append(new_p)
                updated_disc.append(None)
                
        df[base_p_col] = updated_base
        df[disc_p_col] = updated_disc
    elif disc_p_col in df.columns:
        df[disc_p_col] = new_prices
    elif base_p_col in df.columns:
        df[base_p_col] = new_prices

    # Ensure valid discount stock for SnappShop bulk update validation
    if "تخفیف دارد" in df.columns and "موجود در تخفیف" in df.columns:
        stock_col = "موجودی فروشگاه" if "موجودی فروشگاه" in df.columns else None
        if stock_col:
            df["موجود در تخفیف"] = df["موجود در تخفیف"].fillna(df[stock_col]).fillna(99)
        else:
            df["موجود در تخفیف"] = df["موجود در تخفیف"].fillna(99)

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

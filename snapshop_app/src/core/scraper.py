import os
import re
import glob
import asyncio
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
import pandas as pd
from src.config.settings import settings
from src.core.browser import random_delay, smooth_scroll_down

logger = logging.getLogger(__name__)


async def download_inventory_excel(context, download_dir: Path) -> Optional[Path]:
    """
    Download current inventory Excel file from SnappShop seller panel.
    """
    page = await context.new_page()
    try:
        logger.info("Navigating to bulk-update page...")
        await page.goto("https://seller.snappshop.ir/inventory/bulk-update", timeout=30000)
        await page.wait_for_load_state("networkidle")

        # Click request Excel export button
        button = await page.wait_for_selector(".BulkUpdateHeader_card__button__1AEYW", timeout=15000)
        if button:
            await button.click()
            logger.info("Export requested, waiting for file preparation...")
            await asyncio.sleep(5)

        # Listen for download event
        async with page.expect_download(timeout=60000) as download_info:
            download_btn = await page.wait_for_selector(".BulkUpdateHeader_card__download__f_r_n", timeout=30000)
            if download_btn:
                await download_btn.click()

        download = await download_info.value
        saved_path = download_dir / download.suggested_filename
        await download.save_as(str(saved_path))
        logger.info(f"Downloaded inventory Excel: {saved_path}")
        return saved_path
    except Exception as e:
        logger.error(f"Failed to download inventory Excel: {e}")
        return None
    finally:
        await page.close()


async def upload_inventory_excel(context, file_path: Path) -> bool:
    """
    Upload updated inventory Excel file (01.xlsx) to SnappShop seller panel.
    """
    page = await context.new_page()
    try:
        logger.info(f"Uploading file {file_path} to seller panel...")
        await page.goto("https://seller.snappshop.ir/inventory/bulk-update", timeout=30000)
        
        file_input = await page.wait_for_selector("input[type='file']", timeout=15000)
        if file_input:
            await file_input.set_input_files(str(file_path))
            await random_delay(3, 5)
            logger.info("Excel file uploaded successfully.")
            return True
        return False
    except Exception as e:
        logger.error(f"Error uploading Excel file: {e}")
        return False
    finally:
        await page.close()


async def scrape_storefront_buybox(
    context,
    store_url: str,
    company_name: str
) -> List[Dict[str, Any]]:
    """
    Scrape seller store items and competitor prices from SnappShop public storefront.
    """
    page = await context.new_page()
    competitor_data = []

    try:
        logger.info(f"Scraping storefront: {store_url}")
        target_url = f"{store_url}?is_available=true&has_discount=true&page=1"
        await page.goto(target_url, timeout=30000)
        await smooth_scroll_down(page)

        # Extract total pages
        li_elements = await page.query_selector_all(".PLPSection_plp-container__content__tBFHF li")
        total_pages = 1
        if len(li_elements) >= 2:
            page_text = await li_elements[-2].inner_text()
            if page_text.isdigit():
                total_pages = int(page_text)

        logger.info(f"Total product pages found: {total_pages}")
        product_hrefs = []

        for p_num in range(1, total_pages + 1):
            url = f"{store_url}?is_available=true&has_discount=true&page={p_num}"
            await page.goto(url, timeout=20000)
            await random_delay(0.5, 1.0)
            
            a_tags = await page.query_selector_all(".PLPSection_plp-products-container__HSjLH a")
            for a in a_tags:
                href = await a.get_attribute("href")
                if href and href not in product_hrefs:
                    product_hrefs.append(href)

        logger.info(f"Collected {len(product_hrefs)} product URLs. Extracting buybox details...")

        for href in product_hrefs:
            try:
                await page.goto(href, timeout=20000)
                await random_delay(0.5, 1.0)

                title_el = await page.query_selector("h1.text-gray-900")
                title = await title_el.inner_text() if title_el else ""

                seller_el = await page.query_selector(".SellerItem_pdp-seller-item__info__1Uljc span")
                current_seller = await seller_el.inner_text() if seller_el else ""

                vendor_sections = await page.query_selector_all(".VendorBox_vendor-box-desktop__3HwfD section")
                
                second_seller = ""
                second_price = None

                if len(vendor_sections) >= 2 and current_seller == company_name:
                    sec = vendor_sections[1]
                    s_a = await sec.query_selector("a")
                    second_seller = await s_a.get_attribute("title") if s_a else ""

                    p_span = await sec.query_selector(".VendorBox_vendor-box-desktop__vendor-properties__price__KAMSG span")
                    if p_span:
                        raw_p = await p_span.inner_text()
                        cleaned_p = re.sub(r"\D", "", raw_p)
                        if cleaned_p.isdigit():
                            second_price = int(cleaned_p)

                competitor_data.append({
                    "url": href,
                    "title": title.strip(),
                    "current_seller": current_seller.strip(),
                    "has_competitor": bool(second_seller and second_price),
                    "second_seller": second_seller.strip(),
                    "second_price": second_price,
                })
            except Exception as item_err:
                logger.warning(f"Error scraping product {href}: {item_err}")

        return competitor_data
    except Exception as e:
        logger.error(f"Error scraping Buybox details: {e}")
        return competitor_data
    finally:
        await page.close()

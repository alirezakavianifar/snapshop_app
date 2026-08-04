import os
import re
import glob
import random
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
    page = context.pages[0] if context.pages else await context.new_page()
    try:
        logger.info("Navigating to bulk-update page...")
        await page.goto("https://seller.snappshop.ir/inventory/bulk-update", timeout=30000)
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(3)

        # 1. Inspect header for existing export download link
        header_els = await page.query_selector_all("[class*='BulkUpdateHeader'] a, [class*='BulkUpdateHeader'] button")
        logger.info(f"Bulk update header elements found: {len(header_els)}")

        download_el = None
        for el in header_els:
            txt = (await el.inner_text()).strip()
            cls = (await el.get_attribute("class")) or ""
            if "download" in cls.lower() or "خروجی" in txt or "دانلود" in txt:
                tag = await el.evaluate("e => e.tagName")
                if tag == "A" or "download" in cls.lower():
                    download_el = el
                    break

        if download_el:
            logger.info("Found available header download link. Triggering download...")
            try:
                async with page.expect_download(timeout=20000) as download_info:
                    await download_el.click(force=True)
                download = await download_info.value
                saved_path = download_dir / download.suggested_filename
                await download.save_as(str(saved_path))
                logger.info(f"Downloaded inventory Excel: {saved_path}")
                return saved_path
            except Exception as dl_err:
                logger.warning(f"Direct download click failed: {dl_err}. Attempting new export request...")

        # 2. If not immediately downloadable, request new export
        req_btn = await page.query_selector(".BulkUpdateHeader_card__button__1AEYW, button:has-text('دریافت خروجی'), button:has-text('خروجی')")
        if req_btn and not await req_btn.is_disabled():
            await req_btn.click(force=True)
            logger.info("Requested new inventory export, waiting 8s for preparation...")
            await asyncio.sleep(8)

        # 3. Re-inspect header for newly generated download link
        header_els = await page.query_selector_all("[class*='BulkUpdateHeader'] a, [class*='BulkUpdateHeader'] button")
        for el in header_els:
            txt = (await el.inner_text()).strip()
            cls = (await el.get_attribute("class")) or ""
            if "download" in cls.lower() or "خروجی" in txt or "دانلود" in txt:
                download_el = el
                break

        if not download_el:
            raise RuntimeError("Download link not found in header after export request.")

        async with page.expect_download(timeout=30000) as download_info:
            await download_el.click(force=True)

        download = await download_info.value
        saved_path = download_dir / download.suggested_filename
        await download.save_as(str(saved_path))
        logger.info(f"Downloaded inventory Excel: {saved_path}")
        return saved_path
    except Exception as e:
        logger.error(f"Failed to download inventory Excel: {e}")
        return None
    except Exception as e:
        logger.error(f"Failed to download inventory Excel: {e}")
        return None
    finally:
        await page.close()


async def upload_inventory_excel(context, file_path: Path) -> bool:
    """
    Upload updated inventory Excel file (01.xlsx) to SnappShop seller panel.
    """
    page = context.pages[0] if context.pages else await context.new_page()
    try:
        logger.info(f"Uploading file {file_path} to seller panel...")
        await page.goto("https://seller.snappshop.ir/inventory/bulk-update", timeout=30000)
        await page.wait_for_load_state("networkidle")
        await asyncio.sleep(2)
        
        file_input = await page.wait_for_selector("input[type='file']", state="attached", timeout=15000)
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


def normalize_persian_text(text: str) -> str:
    """
    Normalize Persian string characters to avoid mismatch due to Ye (ي/ی), Kef (ك/ک), ZWNJ, and spacing.
    """
    if not text:
        return ""
    text = text.replace("\u064a", "\u06cc").replace("\u0649", "\u06cc")
    text = text.replace("\u0643", "\u06a9")
    text = text.replace("\u200c", " ").replace("\u200b", " ").replace("\xa0", " ")
    return " ".join(text.split()).strip()


async def scrape_storefront_buybox(
    context,
    store_url: str,
    company_name: str
) -> List[Dict[str, Any]]:
    """
    Scrape seller store items and competitor prices from SnappShop public storefront.
    """
    page = context.pages[0] if context.pages else await context.new_page()
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

        clean_company = normalize_persian_text(company_name or "گالری فیگارو")

        for href in product_hrefs:
            try:
                full_url = href if href.startswith("http") else f"https://snappshop.ir{href}"
                
                # Rate Limiting & Anti-Ban: Randomized delay between product page loads (1.5 - 3.5s)
                await random_delay(1.5, 3.5)

                # Retry loop for 429 Too Many Requests rate limiting
                max_retries = 3
                for attempt in range(max_retries):
                    res = await page.goto(full_url, timeout=20000)
                    
                    # Detect 429 status code or 'too many requests' message on page
                    content = await page.content()
                    is_rate_limited = (
                        (res and res.status == 429)
                        or "too many requests" in content.lower()
                        or "تعداد درخواست" in content
                    )
                    
                    if is_rate_limited:
                        backoff_sec = (attempt + 1) * 8 + random.uniform(2, 5)
                        logger.warning(
                            f"⚠️ 429 Rate limit detected on {href}. Backing off for {backoff_sec:.1f}s (Attempt {attempt+1}/{max_retries})..."
                        )
                        await asyncio.sleep(backoff_sec)
                    else:
                        break

                title_el = await page.query_selector("h1")
                base_title = (await title_el.inner_text()).strip() if title_el else ""

                # Check for weight variant pills (e.g. 0.19 گرم, 0.22 گرم...)
                variant_btns = await page.query_selector_all("button:has-text('گرم'), div:has-text('گرم'), [class*='variant'] button")
                
                distinct_variants = []
                seen_weights = set()
                for btn in variant_btns:
                    txt = (await btn.inner_text()).strip()
                    m = re.search(r"\d+\.?\d*\s*گرم", txt)
                    if m and txt not in seen_weights and len(txt) < 15:
                        seen_weights.add(txt)
                        distinct_variants.append((btn, txt))

                # If no variant pills exist, process single product page
                if not distinct_variants:
                    distinct_variants = [(None, "")]

                for v_btn, v_label in distinct_variants:
                    if v_btn:
                        try:
                            await v_btn.click(force=True)
                            await asyncio.sleep(0.9)
                        except Exception:
                            pass

                    full_product_title = f"{base_title} {v_label}".strip() if v_label else base_title

                    # Extract all sellers from JS DOM for active variant
                    sellers = await page.evaluate("""() => {
                        const toEng = (s) => s.replace(/[۰-۹]/g, d => '۰۱۲۳۴۵۶۷۸۹'.indexOf(d)).replace(/[,\\u066C]/g, '');
                        const sections = Array.from(document.querySelectorAll('section[id*="vendor-item"], [class*="vendor-box"], [class*="VendorBox"]'));
                        return sections.map(sec => {
                            const aTag = sec.querySelector('a[title]');
                            const nameEl = sec.querySelector('a div, .text-bold');
                            const sellerName = aTag ? aTag.getAttribute('title').trim() : (nameEl ? nameEl.innerText.trim() : '');
                            
                            const priceEls = Array.from(sec.querySelectorAll('span'));
                            let price = 0;
                            for (const pel of priceEls) {
                                const txt = pel.innerText || '';
                                if (txt.includes('تومان') || /[۰-۹\\d]/.test(txt)) {
                                    const digits = toEng(txt).replace(/\\D/g, '');
                                    if (digits.length >= 5) {
                                        price = parseInt(digits);
                                        break;
                                    }
                                }
                            }
                            return { sellerName, price };
                        }).filter(s => s.price > 0 && s.sellerName);
                    }""")

                    comp_seller = ""
                    comp_price = None

                    if sellers:
                        winner = sellers[0]
                        clean_winner = normalize_persian_text(winner["sellerName"])
                        
                        is_our_win = (
                            clean_company in clean_winner
                            or clean_winner in clean_company
                            or "فیگارو" in clean_winner
                            or "figaro" in clean_winner.lower()
                        )

                        if not is_our_win:
                            # WE ARE NOT WINNING BUYBOX -> Winner seller IS our competitor!
                            comp_seller = winner["sellerName"]
                            comp_price = winner["price"]
                        elif len(sellers) >= 2:
                            # WE ARE WINNING BUYBOX -> Second seller IS our competitor!
                            sec_seller = sellers[1]
                            comp_seller = sec_seller["sellerName"]
                            comp_price = sec_seller["price"]

                    competitor_data.append({
                        "url": href,
                        "title": full_product_title,
                        "current_seller": sellers[0]["sellerName"] if sellers else "",
                        "has_competitor": bool(comp_seller and comp_price),
                        "second_seller": comp_seller,
                        "second_price": comp_price,
                    })
            except Exception as item_err:
                logger.warning(f"Error scraping product {href}: {item_err}")

        return competitor_data
    except Exception as e:
        logger.error(f"Error scraping Buybox details: {e}")
        return competitor_data
    finally:
        await page.close()

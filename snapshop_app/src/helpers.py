import os
import time
import jdatetime
import glob
import pandas as pd
import numpy as np
from datetime import datetime
import pytz
from openpyxl import load_workbook
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from bs4 import BeautifulSoup
import re
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.action_chains import ActionChains

from contextlib import contextmanager
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.firefox.options import Options as FirefoxOptions

from contextlib import contextmanager
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.firefox.options import Options as FirefoxOptions

import time
from contextlib import contextmanager
from functools import wraps
from urllib.parse import urlparse


class MyHandler(FileSystemEventHandler):
    def __init__(self, observer):
        self.observer = observer

    def on_any_event(self, event):
        if event.is_directory:
            return
        print(f"Change detected: {event.event_type} - {event.src_path}")
        self.observer.stop()  # Stop the observer on the first change


def wait_for_dir_changes(path_to_watch):
    # Initialize observer and event handler
    observer = Observer()
    event_handler = MyHandler(observer)

    # Schedule the observer
    observer.schedule(event_handler, path=path_to_watch, recursive=True)

    # Start the observer
    observer.start()

    try:
        # Keep the script running until an event is detected
        observer.join()  # This will block until observer.stop() is called
    except KeyboardInterrupt:
        observer.stop()

    observer.join()  # Ensure the observer is stopped cleanly


def url_logger(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()  # Record the start time
        print(f"\nscraping {kwargs['url']}")
        result = func(*args, **kwargs)  # Execute the function
        end_time = time.time()  # Record the end time
        execution_time = end_time - start_time  # Calculate the execution time
        # print(f"It took {execution_time:.4f} seconds")
        return result
    return wrapper


@contextmanager
def init_driver(pathsave, driver_type='firefox', headless=False, prefs={'maximize': False, 'zoom': '1.0'},
                driver=None, info={}, use_proxy=False, disable_popups=False, *args, **kwargs):
    """
    Context manager for initializing and managing a Selenium WebDriver.

    Args:
    - pathsave (str): The directory path where downloaded files will be saved.
    - driver_type (str): Type of the WebDriver, 'chrome' or 'firefox'. Default is 'firefox'.
    - headless (bool): Whether to run the browser in headless mode, default is False.
    - prefs (dict): Dictionary of preferences for the WebDriver.
    - driver: Existing WebDriver instance, if provided.
    - info (dict): Additional information, if needed.
    - *args, **kwargs: Additional arguments and keyword arguments.

    Yields:
    - driver: The initialized WebDriver instance.

    Note: Ensure proper installation of Selenium and WebDriver executables.
    """
    if driver_type == 'chrome':
        # Chrome WebDriver configuration
        options = ChromeOptions()
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument(
            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36")
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--remote-debugging-port=9222')
        options.add_argument("start-maximized")

        if headless:
            options.add_argument('--headless')

        # Chrome-specific preferences
        chrome_prefs = {
            'download.default_directory': pathsave,
            'download.prompt_for_download': False,
            'directory_upgrade': True,
            'safebrowsing.enabled': False
        }
        options.add_experimental_option("prefs", chrome_prefs)
        options.add_experimental_option(
            "excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)

        # Initialize Chrome WebDriver
        service = ChromeService()
        driver = webdriver.Chrome(service=service, options=options)

    elif driver_type == 'firefox':
        # Firefox WebDriver configuration
        options = FirefoxOptions()

        if headless:
            options.add_argument('--headless')

        # Firefox-specific preferences
        # Use custom download directory
        options.set_preference('browser.download.folderList', 2)
        options.set_preference('browser.download.dir', pathsave)
        options.set_preference('browser.helperApps.neverAsk.saveToDisk',
                               'application/octet-stream')  # Automatic download without asking
        # Disable PDF preview in browser
        options.set_preference('pdfjs.disabled', True)

        if prefs.get('maximize'):
            options.add_argument('--start-maximized')

        # Initialize Firefox WebDriver
        service = FirefoxService(executable_path=r'geckodriver.exe')
        driver = webdriver.Firefox(service=service, options=options)

    try:
        # Yield the driver to the caller
        driver.set_page_load_timeout(10)
        yield driver

    finally:
        # Ensure the WebDriver is properly closed
        driver.quit()


def get_base_url(url):
    parsed_url = urlparse(url)
    return f"{parsed_url.scheme}://{parsed_url.netloc}"


def maybemakedir(directory_path: str):
    """
    Ensure that the directory at `directory_path` exists.
    If the directory does not exist, it is created.
    If it already exists, do nothing.

    :param directory_path: The path to the directory to check or create.
    """
    if not os.path.exists(directory_path):
        try:
            os.makedirs(directory_path)
            print(f"Directory {directory_path} created.")
        except OSError as e:
            print(f"Failed to create directory {directory_path}: {e}")
    else:
        print(f"Directory {directory_path} already exists.")

# Decorating the function with wrap_it_with_params to handle parameters for the scraping process


@url_logger
def go_to_url(driver, info, url='https://www.google.com/'):
    try:
        driver.get(url)
        time.sleep(3)
    except:
        ...  # Navigating to the specified URL using the provided web driver

    return driver, info  # Returning the driver and additional info

# Function to scroll to the end of the page


def scroll_to_end(driver, pause_time=1):
    last_height = driver.execute_script("return document.body.scrollHeight")

    while True:
        # Scroll to the bottom of the page
        driver.execute_script(
            "window.scrollTo(0, document.body.scrollHeight);")

        # Wait for new content to load
        time.sleep(pause_time)

        # Calculate new scroll height
        new_height = driver.execute_script("return document.body.scrollHeight")

        # Break the loop if the page height has not increased
        if new_height == last_height:
            break

        last_height = new_height

# Function for smooth scrolling to the end of the page


def smooth_scroll_to_end(driver, scroll_pause_time=0.5, scroll_step=500):
    last_height = driver.execute_script("return document.body.scrollHeight")

    while True:
        # Scroll down in small increments
        for _ in range(0, last_height, scroll_step):
            driver.execute_script(f"window.scrollBy(0, {scroll_step});")
            time.sleep(scroll_pause_time)

        # Wait for new content to load
        time.sleep(scroll_pause_time)

        # Calculate the new height of the page
        new_height = driver.execute_script("return document.body.scrollHeight")

        # Break the loop if the page height hasn't changed
        if new_height == last_height:
            break

        # Update last height for the next iteration
        last_height = new_height


def scrape_buybox(pathsave, url, company_name):
    with init_driver(pathsave=pathsave, driver_type='firefox', headless=False) as driver:

        url_ = f'{url}?is_available=true&has_discount=true&page=1'
        # Navigating to the URL
        driver, info = go_to_url(driver=driver, info={}, url=url_)
        smooth_scroll_to_end(driver)
        # indentify last page number
        uls = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located(
                (By.CLASS_NAME, 'PLPSection_plp-container__content__tBFHF'))
        )
        li_s = int(uls.find_elements(By.TAG_NAME, 'li')
                   [-2:-1][0].find_element(By.TAG_NAME, 'a').text) + 1

        urls = [
            f'{url_[:-1]}{i}' for i in range(1, li_s)]

        data = []
        colors = []
        # Initialize an empty set to track unique Titles
        unique_titles = set()

        for ul in urls:

            driver.get(ul)
            try:
                container_div = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located(
                        (By.CLASS_NAME, 'PLPSection_plp-products-container__HSjLH.pt-l.pb-s'))
                )
            except:
                continue
            # Find all <a> tags within this div
            a_tags = container_div.find_elements(By.TAG_NAME, 'a')
            hrefs = [a.get_attribute('href')
                     for a in a_tags if a.get_attribute('href')]
            predefined_text = 'گارانتی سلامت فیزیکی کالا 1 ماه'
            # Visit each extracted URL one by one
            for href in hrefs:
                while (True):
                    try:
                        driver.get(href)
                        break
                    except:
                        continue
                mahsool_code = re.search(r'\b\d+\b', href).group()
                try:
                    try:

                        ul_element = WebDriverWait(driver, 1).until(
                            EC.presence_of_element_located(
                                (By.CSS_SELECTOR, 'ul.Variations_variations__color-radio-button__VlV_D.mt-xs.mb-l.pl-xs'))
                        )

                        variants = ul_element.find_elements(By.TAG_NAME, 'li')

                        if len(variants) > 1:
                            for variant in variants:
                                variant.click()
                                time.sleep(0.1)
                                color = driver.find_element(
                                    By.XPATH, "/html/body/div[1]/div/main/div/div/div[1]/div/div[2]/div[2]/div[1]/div[3]/div/div[1]/div/div/div/div/span[2]").text
                                # Wait for the <h1> element to be present, then get the text
                                h1_text = WebDriverWait(driver, 10).until(
                                    EC.presence_of_element_located(
                                        (By.CSS_SELECTOR, '.d-flex.flex-column > h1.text-gray-900.body-1.text-bold.text-iransans-en-digits'))
                                ).text

                                # Construct the full Title (with color and predefined text if applicable)
                                full_title = h1_text + ' ' + color + ' ' + predefined_text

                                # Wait for the <span> element to be present, then get the text

                                span_text = WebDriverWait(driver, 10).until(
                                    EC.presence_of_element_located(
                                        (By.CSS_SELECTOR, '.d-flex.align-items-center > span.h5.text-bold'))
                                ).text

                                seller_text = WebDriverWait(driver, 10).until(
                                    EC.presence_of_element_located(
                                        (By.CSS_SELECTOR, '.SellerItem_pdp-seller-item__info__1Uljc.d-flex.flex-column.mr-s > span.body-2.md\\:caption.text-gray-800'))
                                ).text

                                vendor_box_div = driver.find_element(
                                    By.CLASS_NAME, "VendorBox_vendor-box-desktop__3HwfD")

                                sections = vendor_box_div.find_elements(
                                    By.TAG_NAME, "section")

                                if (len(sections) >= 2 and seller_text == company_name):
                                    # Index 1 for the second
                                    second_section = sections[1]
                                    second_seller = second_section.find_element(
                                        By.TAG_NAME, 'a').get_attribute("title")
                                    second_price = second_section.find_element(By.CSS_SELECTOR, ".VendorBox_vendor-box-desktop__vendor-properties__price__KAMSG.d-flex.justify-content-end.align-items-center")\
                                        .find_element(By.TAG_NAME, 'span').text
                                    second_price = re.sub(
                                        r'\D', '', second_price)

                                else:
                                    second_seller = ''
                                    second_price = ''

                                if full_title not in unique_titles:
                                    # Add the new Title to the set
                                    unique_titles.add(full_title)
                                    # Append to data list as a tuple
                                    data.append((href, mahsool_code, full_title, span_text,
                                                seller_text, second_seller, second_price))
                                else:
                                    print('already exists')
                    except:
                        color = ' '
                        # Wait for the <h1> element to be present, then get the text
                        h1_text = WebDriverWait(driver, 10).until(
                            EC.presence_of_element_located(
                                (By.CSS_SELECTOR, '.d-flex.flex-column > h1.text-gray-900.body-1.text-bold.text-iransans-en-digits'))
                        ).text

                        # Construct the full Title (with color and predefined text if applicable)
                        full_title = h1_text + ' ' + color + ' ' + predefined_text

                        # Wait for the <span> element to be present, then get the text

                        span_text = WebDriverWait(driver, 10).until(
                            EC.presence_of_element_located(
                                (By.CSS_SELECTOR, '.d-flex.align-items-center > span.h5.text-bold'))
                        ).text

                        seller_text = WebDriverWait(driver, 10).until(
                            EC.presence_of_element_located(
                                (By.CSS_SELECTOR, '.SellerItem_pdp-seller-item__info__1Uljc.d-flex.flex-column.mr-s > span.body-2.md\\:caption.text-gray-800'))
                        ).text

                        vendor_box_div = driver.find_element(
                            By.CLASS_NAME, "VendorBox_vendor-box-desktop__3HwfD")

                        sections = vendor_box_div.find_elements(
                            By.TAG_NAME, "section")

                        if (len(sections) >= 2 and seller_text == 'چادوک'):
                            # Index 1 for the second
                            second_section = sections[1]
                            second_seller = second_section.find_element(
                                By.TAG_NAME, 'a').get_attribute("title")
                            second_price = second_section.find_element(By.CSS_SELECTOR, ".VendorBox_vendor-box-desktop__vendor-properties__price__KAMSG.d-flex.justify-content-end.align-items-center")\
                                .find_element(By.TAG_NAME, 'span').text
                            second_price = re.sub(r'\D', '', second_price)

                        else:
                            second_seller = ''
                            second_price = ''

                        if full_title not in unique_titles:
                            # Add the new Title to the set
                            unique_titles.add(full_title)
                            # Append to data list as a tuple
                            data.append((href, mahsool_code, full_title, span_text,
                                        seller_text, second_seller, second_price))
                        else:
                            print('already exists')

                    finally:
                        ...

                except Exception as e:
                    print(f"Failed to retrieve data from {href}: {e}")
                    data.append((href, None, None, None, None, None, None))

        # Convert the list to a DataFrame
        df = pd.DataFrame(data, columns=[
                          'URL', 'mahsool_code', 'Title', 'Price', 'Seller', 'second_seller', 'second_price'])
        df.to_excel(os.path.join(pathsave, 'examine.xlsx'))


def scrape_it(pathsave, url, phone_num, password, skip_buybox):

    with init_driver(pathsave=pathsave, driver_type='firefox', headless=False) as driver:

        def get_excel(driver):
            # Navigating to the URL
            driver, info = go_to_url(driver=driver, info={}, url=url)
            # Define the WebDriverWait
            wait = WebDriverWait(driver, 1200)  # Wait up to 10 seconds
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "phone-number-input"))
            ).send_keys(phone_num)

            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, "//button[contains(text(), 'تایید و ادامه')]"))).click()

            if password is None:

                while True:
                    try:

                        if (WebDriverWait(driver, 5).until(
                                EC.presence_of_element_located((By.CSS_SELECTOR, "h1.h6.text-bold.text-center.text-ellipsis.mt-m.Authentication_layout_page-title-description__jYrw_"))).text == 'عضویت'):
                            print('waiting for entering the code...')
                            continue
                    except:
                        time.sleep(2)
                        break
            else:

                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.NAME, "password"))).send_keys(password)

                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, "//button[contains(text(), 'ورود به حساب کاربری')]"))).click()

            time.sleep(7)

            try:
                driver.get('https://seller.snappshop.ir/inventory/bulk-update')
            except:
                ...

            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.CLASS_NAME, "BulkUpdateHeader_card__button__1AEYW"))).click()

            time.sleep(4)

            WebDriverWait(driver, 1000).until(
                EC.invisibility_of_element_located((
                    By.CLASS_NAME, "Spinner_module_indeterminate__44b85ff5")))

            WebDriverWait(driver, 12).until(
                EC.presence_of_element_located((
                    By.CLASS_NAME, "BulkUpdateHeader_card__download__f_r_n"))).click()

            # ##############################################################################
            wait_for_dir_changes(pathsave)

            time.sleep(20)

        get_excel(driver)

        # Step 2: Find all Excel files in the Downloads

        excel_files = glob.glob(os.path.join(pathsave, '*.xlsx'))
        latest_file = max(excel_files, key=os.path.getmtime)

        # Step 3: Get the most recent Excel file based on the modification time
        latest_file = max(excel_files, key=os.path.getmtime)

        # Step 4: Read the latest Excel file
        df = pd.read_excel(latest_file)

        df = df[df['فعال'] != 0]
        df = df[df['تخفیف دارد'] != 0]

        # Step 1: Get the current date in the Persian calendar
        current_persian_date = jdatetime.date.today()

        # Step 2: Replace the values in 'تاریخ شروع تخفیف' column with the current Persian date
        df['تاریخ شروع تخفیف'] = current_persian_date.strftime('%Y/%m/%d')

        # Step 1: Get the current time in the Tehran (Persian) timezone
        tehran_tz = pytz.timezone('Asia/Tehran')
        current_time = datetime.now(tehran_tz)

        # Step 2: Format the current time as HH:MM:SS
        current_time_str = current_time.strftime('%H:%M')

        # Step 3: Replace the values in 'زمان شروع تخفیف' column with the current time
        df['زمان شروع تخفیف'] = current_time_str

        # Step 1: Extract the file name with extension
        # file_name_with_ext = os.path.basename(latest_file)

        # Step 2: Remove the '.xlsx' extension
        # file_name, file_ext = os.path.splitext(file_name_with_ext)

        # Step 3: Append the current time string to the file name
        # new_file_name = f"{file_name}_{current_time_str}{file_ext}"

        # df.to_excel(os.path.join(pathsave, new_file_name))

        df['Result'] = np.where(
            # Condition: O2 <= J2
            df['قیمت بعد از تخفیف به تومان'] <= df['قیمت بای باکس'],
            np.where(df['قیمت بعد از تخفیف به تومان'] < df['کد فروشنده'], df['کد فروشنده'],
                     df['قیمت بعد از تخفیف به تومان']),  # If true, nested condition for O2 < D2
            np.where(0.99 * df['قیمت بای باکس'] > df['کد فروشنده'],  # If false, condition for (0.99 * J2) > D2
                     np.where(df['قیمت بای باکس'] > 500000, df['قیمت بای باکس'] - 5000,
                              df['قیمت بای باکس'] - (0.011 * df['قیمت بای باکس'])),  # J2 > 500000 check
                     df['کد فروشنده'])  # If (0.99 * J2) <= D2
        )

        # df['Result'] = np.round(df['Result'], -1).astype(np.int64)

        df['قیمت بعد از تخفیف به تومان'] = df['Result']

        df.drop(labels=['Result'], inplace=True, axis=1)

        output_file = os.path.join(pathsave, '01.xlsx')

        if not skip_buybox:

            df_examine = pd.read_excel(os.path.join(pathsave, 'examine.xlsx'))

            df_examine = df_examine[df_examine['second_price'].notna()]
            # Merge the DataFrames, keeping all rows from df1 and only columns from df1
            merged_df = df.merge(df_examine[['Title', 'second_price']],
                                 how='left',
                                 left_on='عنوان کالا',
                                 right_on='Title')
            # Convert to numeric as bigint (int64), handling errors with NaN
            merged_df['second_price'] = pd.to_numeric(
                merged_df['second_price'], errors='coerce'
            ).round().fillna(0).astype('Int64')
            # Convert to numeric, handle errors, round floats, fill NaNs, then cast to Int64
            merged_df['قیمت بعد از تخفیف به تومان'] = pd.to_numeric(
                merged_df['قیمت بعد از تخفیف به تومان'], errors='coerce'
            ).round().fillna(0).astype('Int64')
            merged_df['قیمت بعد از تخفیف به تومان'] = np.where(
                (merged_df['second_price'] != 0) & (
                    merged_df['second_price'] <= 500000),
                # Apply discount and round down
                np.floor(merged_df['second_price'] * 0.989),
                np.where(
                    (merged_df['second_price'] != 0) & (
                        merged_df['second_price'] > 500000),
                    # Subtract 5100 and round down
                    np.floor(merged_df['second_price'] - 5100),
                    # Keep original value if 0
                    merged_df['قیمت بعد از تخفیف به تومان']
                )
            )

            # Drop the temporary 'second_price' and 'mahsool_code' columns
            df = merged_df.drop(columns=['second_price', 'Title'])

        sheet_name = 'فهرست محصولات'

        df.to_excel(output_file, index=False, sheet_name=sheet_name)

        wb = load_workbook(output_file)
        ws = wb.active
        ws.sheet_view.rightToLeft = True  # Set the sheet to right-to-left
        wb.save(output_file)

        file_input = driver.find_element("xpath", "//input[@type='file']")

        file_input.send_keys(output_file)

        print('Done')

        time.sleep(60)


def extract_year(text):
    # Define a mapping from Persian to Georgian digits
    persian_to_georgian = str.maketrans('۰۱۲۳۴۵۶۷۸۹', '0123456789')

    # Normalize the text to convert Persian numerals to Georgian numerals
    normalized_text = text.translate(persian_to_georgian)

    # Regular expression to find a four-digit year
    match = re.search(r'\b(19|20)\d{2}\b', normalized_text)

    if match:
        return match.group()
    return None

# Function to remove non-printable characters


def remove_control_characters(s):
    if isinstance(s, str):  # Only process strings
        return re.sub(r'[\x00-\x1f\x7f-\x9f]', '', s)
    return s


def merge_excel_files(input_directory, output_file='merged_output.xlsx'):
    # Initialize an empty DataFrame to hold the merged data
    merged_df = pd.DataFrame()

    # Loop through all Excel files in the directory
    for file_name in os.listdir(input_directory):
        # Check for Excel files
        if file_name.endswith('.xlsx') or file_name.endswith('.xls'):
            file_path = os.path.join(input_directory, file_name)
            # Read the Excel file
            df = pd.read_excel(file_path)
            # Append its data to the merged DataFrame
            merged_df = pd.concat([merged_df, df], ignore_index=True)

    # Save the merged DataFrame to a new Excel file
    merged_df.to_excel(output_file, index=False)
    print(f"Merged file saved as {output_file}")


if __name__ == '__main__':
    merge_excel_files(input_directory=r'D:\projects\google_search\downloads')

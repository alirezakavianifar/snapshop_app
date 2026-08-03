import sys
import os

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import time
import threading
import schedule
import logging
from tkinter import messagebox
import customtkinter as ctk
from src.helpers import scrape_it, scrape_buybox

log_file = "scraper_log.txt"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(log_file), logging.StreamHandler()],
)

COLORS = {
    "bg": "#EEF3F1",
    "surface": "#FFFFFF",
    "header": "#0C3B2E",
    "header_soft": "#145A43",
    "accent": "#16A34A",
    "accent_hover": "#15803D",
    "accent_soft": "#DCFCE7",
    "text": "#0F172A",
    "muted": "#64748B",
    "border": "#D6E2DC",
    "log_bg": "#0B1F18",
    "log_fg": "#BBF7D0",
}


class TextHandler(logging.Handler):
    def __init__(self, text_widget):
        super().__init__()
        self.text_widget = text_widget

    def emit(self, record):
        msg = self.format(record)

        def append():
            self.text_widget.configure(state="normal")
            self.text_widget.insert("end", msg + "\n")
            self.text_widget.see("end")
            self.text_widget.configure(state="disabled")

        try:
            self.text_widget.after(0, append)
        except Exception:
            pass


def run_scraper(phone_num, password=None, url="https://snappshop.ir/seller/g3aPbQ", company_name="چادوک"):
    if scrape:
        logging.info(f"Running scraper with phone: {phone_num}")
        try:
            if not skip_buybox:
                scrape_buybox(pathsave=pathsave, url=url, company_name=company_name)
            scrape_it(
                pathsave=pathsave,
                url=URL,
                phone_num=phone_num,
                password=password,
                skip_buybox=skip_buybox,
            )
            logging.info("Scraping completed successfully.")
        except Exception as e:
            logging.error(f"Error during scraping: {e}")


def start_scheduler(phone_num, password, minutes, url, company_name):
    global scrape
    scrape = True
    schedule.clear()

    threading.Thread(
        target=run_scraper, args=(phone_num, password, url, company_name), daemon=True
    ).start()

    schedule.every(int(minutes)).minutes.do(
        run_scraper, phone_num=phone_num, password=password, url=url, company_name=company_name
    )
    logging.info(f"Scraping scheduled every {minutes} minutes")

    def run_schedule():
        while scrape:
            schedule.run_pending()
            time.sleep(1)

    threading.Thread(target=run_schedule, daemon=True).start()


def create_gui():
    ctk.set_appearance_mode("light")
    ctk.set_default_color_theme("green")
    # Keep layout predictable on high-DPI / scaled Windows displays
    ctk.set_widget_scaling(1.0)
    ctk.set_window_scaling(1.0)

    root = ctk.CTk()
    root.title("SnapShop Scheduler")
    root.configure(fg_color=COLORS["bg"])

    font_brand = ctk.CTkFont(family="Segoe UI", size=22, weight="bold")
    font_sub = ctk.CTkFont(family="Segoe UI", size=12)
    font_section = ctk.CTkFont(family="Segoe UI", size=13, weight="bold")
    font_label = ctk.CTkFont(family="Segoe UI", size=10, weight="bold")
    font_body = ctk.CTkFont(family="Segoe UI", size=12)
    font_btn = ctk.CTkFont(family="Segoe UI", size=14, weight="bold")
    font_mono = ctk.CTkFont(family="Consolas", size=11)

    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    ww, wh = 680, 760
    root.geometry(f"{ww}x{wh}+{(sw - ww) // 2}+{max(4, (sh - wh) // 2)}")
    root.resizable(False, False)

    # —— Header ——
    header = ctk.CTkFrame(root, fg_color=COLORS["header"], corner_radius=0, height=70)
    header.pack(fill="x")
    header.pack_propagate(False)
    hi = ctk.CTkFrame(header, fg_color="transparent")
    hi.pack(fill="both", expand=True, padx=20, pady=8)
    ctk.CTkLabel(hi, text="SNAPSHOP", font=font_brand, text_color="#FFFFFF", anchor="w").pack(anchor="w")
    ctk.CTkLabel(
        hi, text="زمان‌بند هوشمند قیمت و موجودی فروشنده", font=font_sub, text_color="#86EFAC", anchor="w"
    ).pack(anchor="w")
    ctk.CTkFrame(root, fg_color=COLORS["accent"], height=3, corner_radius=0).pack(fill="x")

    pad = ctk.CTkFrame(root, fg_color="transparent")
    pad.pack(fill="x", padx=18, pady=10)

    status_row = ctk.CTkFrame(pad, fg_color="transparent")
    status_row.pack(fill="x", pady=(0, 6))
    status_dot = ctk.CTkLabel(status_row, text="●", font=font_body, text_color=COLORS["muted"], width=16)
    status_dot.pack(side="left")
    status_label = ctk.CTkLabel(status_row, text="آماده اجرا", font=font_body, text_color=COLORS["muted"])
    status_label.pack(side="left", padx=(4, 0))

    # Fixed-height scrollable form so CTA + log always sit below it
    form = ctk.CTkScrollableFrame(
        pad,
        height=220,
        fg_color=COLORS["surface"],
        border_color=COLORS["border"],
        border_width=1,
        corner_radius=12,
    )
    form.pack(fill="x", expand=False)

    ctk.CTkLabel(form, text="تنظیمات اتصال", font=font_section, text_color=COLORS["text"], anchor="w").pack(
        anchor="w", padx=4, pady=(2, 0)
    )
    ctk.CTkLabel(
        form,
        text="اطلاعات ورود به پنل فروشنده اسنپ‌شاپ را وارد کنید.",
        font=font_body,
        text_color=COLORS["muted"],
        anchor="w",
    ).pack(anchor="w", padx=4, pady=(2, 8))

    def field_label(parent, text):
        ctk.CTkLabel(parent, text=text.upper(), font=font_label, text_color=COLORS["muted"], anchor="w").pack(
            anchor="w", padx=4, pady=(0, 2)
        )

    def make_entry(parent, default="", show=None):
        entry = ctk.CTkEntry(
            parent,
            height=32,
            corner_radius=8,
            border_color=COLORS["border"],
            fg_color="#F8FAFC",
            text_color=COLORS["text"],
            font=font_body,
            show=show or "",
        )
        entry.pack(fill="x", padx=4)
        if default:
            entry.insert(0, default)
        return entry

    field_label(form, "Phone Number")
    phone_entry = make_entry(form, "09120000000")

    pass_header = ctk.CTkFrame(form, fg_color="transparent")
    pass_header.pack(fill="x", padx=4, pady=(8, 2))
    ctk.CTkLabel(pass_header, text="PASSWORD", font=font_label, text_color=COLORS["muted"]).pack(side="left")
    use_password_var = ctk.BooleanVar(value=True)

    def toggle_password():
        if use_password_var.get():
            password_entry.configure(state="normal")
        else:
            password_entry.delete(0, "end")
            password_entry.configure(state="disabled")

    ctk.CTkCheckBox(
        pass_header,
        text="Use password",
        variable=use_password_var,
        font=font_body,
        text_color=COLORS["text"],
        fg_color=COLORS["accent"],
        hover_color=COLORS["accent_hover"],
        border_color=COLORS["border"],
        command=toggle_password,
        checkbox_width=18,
        checkbox_height=18,
    ).pack(side="right")
    password_entry = make_entry(form, "Reza0000000", show="*")

    two = ctk.CTkFrame(form, fg_color="transparent")
    two.pack(fill="x", padx=4, pady=(8, 0))
    two.grid_columnconfigure((0, 1), weight=1)
    left = ctk.CTkFrame(two, fg_color="transparent")
    left.grid(row=0, column=0, sticky="ew", padx=(0, 6))
    right = ctk.CTkFrame(two, fg_color="transparent")
    right.grid(row=0, column=1, sticky="ew", padx=(6, 0))
    field_label(left, "Minutes Interval")
    minutes_entry = make_entry(left, "20")
    field_label(right, "Company Name")
    company_entry = make_entry(right, "چادوک")

    url_box = ctk.CTkFrame(form, fg_color="transparent")
    url_box.pack(fill="x", pady=(8, 0))
    field_label(url_box, "Seller Store URL")
    url_entry = make_entry(url_box, "https://snappshop.ir/seller/g3aPbQ")

    opts = ctk.CTkFrame(form, fg_color=COLORS["accent_soft"], corner_radius=8)
    opts.pack(fill="x", padx=4, pady=(10, 6))
    skip_buybox_var = ctk.BooleanVar(value=False)

    def toggle_scrape_buybox():
        global skip_buybox
        skip_buybox = skip_buybox_var.get()

    ctk.CTkCheckBox(
        opts,
        text="Skip Buybox scraping",
        variable=skip_buybox_var,
        font=font_body,
        text_color=COLORS["text"],
        fg_color=COLORS["accent"],
        hover_color=COLORS["accent_hover"],
        border_color=COLORS["border"],
        command=toggle_scrape_buybox,
        checkbox_width=18,
        checkbox_height=18,
    ).pack(anchor="w", padx=10, pady=8)

    start_button = ctk.CTkButton(
        pad,
        text="Start Scraping",
        font=font_btn,
        height=40,
        corner_radius=10,
        fg_color=COLORS["accent"],
        hover_color=COLORS["accent_hover"],
        text_color="#FFFFFF",
    )
    start_button.pack(fill="x", pady=(12, 8))

    log_header = ctk.CTkFrame(pad, fg_color="transparent")
    log_header.pack(fill="x")
    ctk.CTkLabel(log_header, text="Activity Log", font=font_section, text_color=COLORS["text"]).pack(side="left")
    ctk.CTkLabel(
        log_header, text="رویدادهای اجرا به‌صورت زنده", font=font_body, text_color=COLORS["muted"]
    ).pack(side="right")

    log_text = ctk.CTkTextbox(
        pad,
        height=80,
        corner_radius=10,
        fg_color=COLORS["log_bg"],
        text_color=COLORS["log_fg"],
        font=font_mono,
        border_width=0,
        state="disabled",
        wrap="word",
    )
    log_text.pack(fill="x", pady=(4, 4))

    ctk.CTkLabel(
        pad,
        text=f"Downloads  ·  {pathsave}",
        font=ctk.CTkFont(family="Segoe UI", size=10),
        text_color=COLORS["muted"],
        anchor="w",
    ).pack(fill="x")

    text_handler = TextHandler(log_text)
    text_handler.setFormatter(logging.Formatter("%(asctime)s  %(levelname)s  %(message)s", "%H:%M:%S"))
    logging.getLogger().addHandler(text_handler)

    def on_start():
        phone_num = phone_entry.get().strip()
        password = password_entry.get() if use_password_var.get() else None
        minutes = minutes_entry.get().strip()
        url = url_entry.get().strip()
        company_name = company_entry.get().strip()

        if not phone_num or not minutes:
            messagebox.showwarning("Input Error", "Please fill out all required fields.")
            return

        status_dot.configure(text_color=COLORS["accent"])
        status_label.configure(text="در حال اجرا — زمان‌بندی فعال است", text_color=COLORS["accent"])
        start_button.configure(text="Scheduler Running", fg_color=COLORS["header_soft"], state="disabled")

        logging.info("Scheduler started by user")
        threading.Thread(
            target=start_scheduler,
            args=(phone_num, password, minutes, url, company_name),
            daemon=True,
        ).start()

    start_button.configure(command=on_start)
    root.mainloop()


scrape = True
skip_buybox = False
URL = "https://seller.snappshop.ir/"
script_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(script_dir)
pathsave = os.path.join(os.path.dirname(sys.executable), "downloads")

if not os.path.exists(pathsave):
    os.makedirs(pathsave)

create_gui()

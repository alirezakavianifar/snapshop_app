import sys
import os
import threading
import asyncio
import logging
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

# Ensure project root & frozen modules are in sys.path
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
    meipass_dir = Path(getattr(sys, "_MEIPASS", sys.executable)).resolve()
    if meipass_dir.exists() and str(meipass_dir) not in sys.path:
        sys.path.insert(0, str(meipass_dir))
    internal_dir = BASE_DIR / "_internal"
    if internal_dir.exists() and str(internal_dir) not in sys.path:
        sys.path.insert(0, str(internal_dir))
else:
    BASE_DIR = Path(__file__).resolve().parent

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Ensure Playwright uses global ms-playwright browsers directory
if "PLAYWRIGHT_BROWSERS_PATH" not in os.environ:
    ms_playwright = Path.home() / "AppData" / "Local" / "ms-playwright"
    if ms_playwright.exists():
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(ms_playwright)

# Configure Logging to File & Stdout
log_dir = BASE_DIR / "downloads"
log_dir.mkdir(parents=True, exist_ok=True)
log_file = log_dir / "bot_activity.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
    force=True,
)

from src.config.settings import settings
from src.core.database import DatabaseManager
from src.scheduler.job_runner import run_sync_cycle


class SnappShopAppGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("SnappShop Bot Control Panel")
        self.root.geometry("850x620")
        self.root.minsize(800, 550)

        # Style configuration
        self.style = ttk.Style()
        self.style.theme_use("clam")

        # Color Palette
        self.BG_COLOR = "#1e1e2e"
        self.CARD_BG = "#2b2b3b"
        self.TEXT_COLOR = "#cdd6f4"
        self.ACCENT_COLOR = "#89b4fa"
        self.SUCCESS_COLOR = "#a6e3a1"
        self.WARN_COLOR = "#f9e2af"
        self.DANGER_COLOR = "#f38ba8"

        self.root.configure(bg=self.BG_COLOR)

        self.is_running = False
        self.sync_thread = None

        self._build_ui()
        self._load_current_settings()
        self._start_log_polling()

    def _build_ui(self):
        # Header Bar
        header_frame = tk.Frame(self.root, bg=self.CARD_BG, pady=12, padx=15)
        header_frame.pack(fill="x", padx=15, pady=10)

        title_label = tk.Label(
            header_frame,
            text="🛍️ SnappShop Price Bot - Desktop Control Panel",
            font=("Segoe UI", 16, "bold"),
            fg=self.ACCENT_COLOR,
            bg=self.CARD_BG,
        )
        title_label.pack(side="left")

        self.status_label = tk.Label(
            header_frame,
            text="● Status: Idle",
            font=("Segoe UI", 11, "bold"),
            fg=self.SUCCESS_COLOR,
            bg=self.CARD_BG,
        )
        self.status_label.pack(side="right")

        self.session_label = tk.Label(
            header_frame,
            text=self._get_session_expiration_info(),
            font=("Segoe UI", 9, "italic"),
            fg="#a6adc8",
            bg=self.CARD_BG,
        )
        self.session_label.pack(side="right", padx=15)

        # Main Layout (Notebook Tabs)
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=15, pady=5)

        # Tab 1: Control Center & Activity Log
        self.tab_control = tk.Frame(self.notebook, bg=self.BG_COLOR)
        self.notebook.add(self.tab_control, text=" 🎮 Control Center ")

        # Tab 2: Application Settings
        self.tab_settings = tk.Frame(self.notebook, bg=self.BG_COLOR)
        self.notebook.add(self.tab_settings, text=" ⚙️ Settings ")

        self._build_control_tab()
        self._build_settings_tab()

    def _build_control_tab(self):
        # Action Buttons Frame
        btn_frame = tk.Frame(self.tab_control, bg=self.CARD_BG, pady=10, padx=10)
        btn_frame.pack(fill="x", padx=10, pady=10)

        self.btn_run_now = tk.Button(
            btn_frame,
            text="▶ Run Sync Cycle Now",
            font=("Segoe UI", 10, "bold"),
            bg="#313244",
            fg=self.TEXT_COLOR,
            activebackground=self.ACCENT_COLOR,
            activeforeground="#000000",
            relief="flat",
            padx=12,
            pady=6,
            command=self.run_sync_now,
        )
        self.btn_run_now.pack(side="left", padx=5)

        self.btn_import_rules = tk.Button(
            btn_frame,
            text="📁 Import Excel/CSV Rules",
            font=("Segoe UI", 10, "bold"),
            bg="#313244",
            fg=self.TEXT_COLOR,
            activebackground=self.ACCENT_COLOR,
            activeforeground="#000000",
            relief="flat",
            padx=12,
            pady=6,
            command=self.import_excel_rules,
        )
        self.btn_import_rules.pack(side="left", padx=5)

        self.headless_var = tk.BooleanVar(value=os.environ.get("HEADLESS", "true").lower() in ("true", "1", "yes"))
        self.chk_headless = tk.Checkbutton(
            btn_frame,
            text="🕶️ Headless Mode (Hide Browser)",
            variable=self.headless_var,
            font=("Segoe UI", 10, "bold"),
            fg=self.TEXT_COLOR,
            bg=self.CARD_BG,
            selectcolor="#11111b",
            activebackground=self.CARD_BG,
            activeforeground=self.TEXT_COLOR,
        )
        self.chk_headless.pack(side="left", padx=15)

        self.btn_toggle_scheduler = tk.Button(
            btn_frame,
            text="🔄 Start Continuous Monitor (Every 20m)",
            font=("Segoe UI", 10, "bold"),
            bg="#a6e3a1",
            fg="#11111b",
            activebackground=self.SUCCESS_COLOR,
            relief="flat",
            padx=12,
            pady=6,
            command=self.toggle_scheduler,
        )
        self.btn_toggle_scheduler.pack(side="right", padx=5)

        # Log Output Viewer
        log_frame = tk.LabelFrame(
            self.tab_control,
            text=" Live Activity Log ",
            font=("Segoe UI", 10, "bold"),
            fg=self.ACCENT_COLOR,
            bg=self.BG_COLOR,
            padx=10,
            pady=10,
        )
        log_frame.pack(fill="both", expand=True, padx=10, pady=5)

        # Log Toolbar (Copy / Clear buttons)
        log_toolbar = tk.Frame(log_frame, bg=self.BG_COLOR, pady=2)
        log_toolbar.pack(fill="x", pady=(0, 5))

        btn_copy = tk.Button(
            log_toolbar,
            text="📋 Copy All Logs",
            font=("Segoe UI", 9, "bold"),
            bg="#313244",
            fg=self.TEXT_COLOR,
            activebackground=self.ACCENT_COLOR,
            activeforeground="#000000",
            relief="flat",
            padx=8,
            pady=3,
            command=self.copy_all_logs,
        )
        btn_copy.pack(side="left", padx=(0, 5))

        btn_copy_sel = tk.Button(
            log_toolbar,
            text="✂️ Copy Selected",
            font=("Segoe UI", 9),
            bg="#313244",
            fg=self.TEXT_COLOR,
            activebackground=self.ACCENT_COLOR,
            activeforeground="#000000",
            relief="flat",
            padx=8,
            pady=3,
            command=self.copy_selected_log,
        )
        btn_copy_sel.pack(side="left", padx=5)

        btn_clear = tk.Button(
            log_toolbar,
            text="🗑️ Clear Logs",
            font=("Segoe UI", 9, "bold"),
            bg="#313244",
            fg=self.DANGER_COLOR,
            activebackground=self.DANGER_COLOR,
            activeforeground="#11111b",
            relief="flat",
            padx=8,
            pady=3,
            command=self.clear_activity_logs,
        )
        btn_clear.pack(side="right", padx=(5, 0))

        self.log_area = scrolledtext.ScrolledText(
            log_frame,
            font=("Consolas", 9),
            bg="#11111b",
            fg="#a6adc8",
            insertbackground="#cdd6f4",
            wrap="word",
        )
        self.log_area.pack(fill="both", expand=True)

        self._attach_log_context_menu()

    def _build_settings_tab(self):
        settings_card = tk.Frame(self.tab_settings, bg=self.CARD_BG, pady=15, padx=15)
        settings_card.pack(fill="both", expand=True, padx=15, pady=15)

        fields = [
            ("Telegram Bot Token:", "token_var"),
            ("Telegram Admin Chat ID:", "chat_id_var"),
            ("Telegram Proxy URL (Optional):", "proxy_var"),
            ("SnappShop Phone Number:", "phone_var"),
            ("SnappShop Password:", "password_var"),
            ("Target Seller Store URL:", "url_var"),
            ("Company Name (Persian):", "company_var"),
            ("Check Interval (Minutes):", "interval_var"),
        ]

        self.vars = {}
        for label_text, var_name in fields:
            row = tk.Frame(settings_card, bg=self.CARD_BG, pady=6)
            row.pack(fill="x")

            lbl = tk.Label(
                row,
                text=label_text,
                width=24,
                anchor="w",
                font=("Segoe UI", 10),
                fg=self.TEXT_COLOR,
                bg=self.CARD_BG,
            )
            lbl.pack(side="left")

            var = tk.StringVar()
            self.vars[var_name] = var
            entry = tk.Entry(
                row,
                textvariable=var,
                font=("Segoe UI", 10),
                bg="#1e1e2e",
                fg=self.TEXT_COLOR,
                insertbackground=self.TEXT_COLOR,
                relief="flat",
            )
            entry.pack(side="right", fill="x", expand=True, padx=5)

        btn_save = tk.Button(
            settings_card,
            text="💾 Save Settings to .env",
            font=("Segoe UI", 10, "bold"),
            bg=self.ACCENT_COLOR,
            fg="#11111b",
            relief="flat",
            pady=6,
            command=self.save_settings,
        )
        btn_save.pack(pady=15)

    def _load_current_settings(self):
        self.vars["token_var"].set(settings.TELEGRAM_BOT_TOKEN or "")
        self.vars["chat_id_var"].set(settings.TELEGRAM_ADMIN_CHAT_ID or "")
        self.vars["proxy_var"].set(getattr(settings, "TELEGRAM_PROXY_URL", "") or "")
        self.vars["phone_var"].set(settings.SNAPSHOP_PHONE_NUMBER or "")
        self.vars["password_var"].set(settings.SNAPSHOP_PASSWORD or "")
        self.vars["url_var"].set(settings.SNAPSHOP_STORE_URL or "")
        self.vars["company_var"].set(settings.SNAPSHOP_COMPANY_NAME or "")
        self.vars["interval_var"].set(str(settings.CHECK_INTERVAL_MINUTES))

    def save_settings(self):
        try:
            env_path = BASE_DIR / ".env"
            is_h = "true" if self.headless_var.get() else "false"
            env_content = f"""TELEGRAM_BOT_TOKEN="{self.vars['token_var'].get()}"
TELEGRAM_ADMIN_CHAT_ID="{self.vars['chat_id_var'].get()}"
TELEGRAM_PROXY_URL="{self.vars['proxy_var'].get()}"
SNAPSHOP_PHONE_NUMBER="{self.vars['phone_var'].get()}"
SNAPSHOP_PASSWORD="{self.vars['password_var'].get()}"
SNAPSHOP_STORE_URL="{self.vars['url_var'].get()}"
SNAPSHOP_COMPANY_NAME="{self.vars['company_var'].get()}"
CHECK_INTERVAL_MINUTES="{self.vars['interval_var'].get()}"
HEADLESS="{is_h}"
"""
            with open(env_path, "w", encoding="utf-8") as f:
                f.write(env_content)

            # Instantly update runtime settings in memory
            settings.TELEGRAM_BOT_TOKEN = self.vars['token_var'].get()
            settings.TELEGRAM_ADMIN_CHAT_ID = self.vars['chat_id_var'].get()
            settings.TELEGRAM_PROXY_URL = self.vars['proxy_var'].get()
            settings.SNAPSHOP_PHONE_NUMBER = self.vars['phone_var'].get()
            settings.SNAPSHOP_PASSWORD = self.vars['password_var'].get()
            settings.SNAPSHOP_STORE_URL = self.vars['url_var'].get()
            settings.SNAPSHOP_COMPANY_NAME = self.vars['company_var'].get()
            try:
                settings.CHECK_INTERVAL_MINUTES = int(self.vars['interval_var'].get())
            except ValueError:
                pass
            os.environ["HEADLESS"] = is_h

            messagebox.showinfo("Success", "Settings saved successfully to .env file & reloaded!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save settings: {e}")

    def run_sync_now(self):
        if self.is_running:
            messagebox.showwarning("Busy", "A sync task is already running!")
            return

        self.is_running = True
        self.status_label.config(text="● Status: Syncing...", fg=self.WARN_COLOR)
        self.btn_run_now.config(state="disabled")

        def task():
            try:
                os.environ["HEADLESS"] = "true" if self.headless_var.get() else "false"
                asyncio.run(run_sync_cycle())
            except Exception as err:
                logging.error(f"Sync error: {err}")
            finally:
                self.is_running = False
                self.root.after(0, lambda: self.status_label.config(text="● Status: Idle", fg=self.SUCCESS_COLOR))
                self.root.after(0, lambda: self.btn_run_now.config(state="normal"))

        threading.Thread(target=task, daemon=True).start()

    def toggle_scheduler(self):
        if not self.is_running:
            self.is_running = True
            self.status_label.config(text="● Status: Continuous Monitoring Active", fg=self.SUCCESS_COLOR)
            self.btn_toggle_scheduler.config(text="⏹ Stop Continuous Monitor", bg=self.DANGER_COLOR)
            
            def loop():
                import time
                while self.is_running:
                    os.environ["HEADLESS"] = "true" if self.headless_var.get() else "false"
                    asyncio.run(run_sync_cycle())
                    interval = int(self.vars["interval_var"].get() or 20) * 60
                    for _ in range(interval):
                        if not self.is_running:
                            break
                        time.sleep(1)

            self.sync_thread = threading.Thread(target=loop, daemon=True)
            self.sync_thread.start()
        else:
            self.is_running = False
            self.status_label.config(text="● Status: Stopped", fg=self.DANGER_COLOR)
            self.btn_toggle_scheduler.config(text="🔄 Start Continuous Monitor", bg=self.SUCCESS_COLOR)

    def _start_log_polling(self):
        log_file = BASE_DIR / "downloads" / "bot_activity.log"
        self.last_log_size = 0

        def update_logs():
            if log_file.exists():
                try:
                    size = log_file.stat().st_size
                    if size > self.last_log_size:
                        with open(log_file, "r", encoding="utf-8") as f:
                            f.seek(self.last_log_size)
                            new_text = f.read()
                            self.log_area.insert("end", new_text)
                            self.log_area.see("end")
                            self.last_log_size = size
                except Exception:
                    pass
            self.root.after(2000, update_logs)

        update_logs()

    def import_excel_rules(self):
        from tkinter import filedialog
        file_path = filedialog.askopenfilename(
            title="Select Excel or CSV Product Rules File",
            filetypes=[("Excel / CSV Files", "*.xlsx *.xls *.csv"), ("All Files", "*.*")]
        )
        if not file_path:
            return

        try:
            import pandas as pd
            from src.core.scraper import normalize_persian_text
            if file_path.endswith(".csv"):
                df = pd.read_csv(file_path)
            else:
                df = pd.read_excel(file_path)

            title_col, min_col, max_col, inc_col, dec_col, price_col = None, None, None, None, None, None
            for col in df.columns:
                clean_c = str(col).strip()
                norm_c = normalize_persian_text(clean_c).lower()
                if any(k in norm_c for k in ["عنوان", "title", "product", "کالا", "نام"]):
                    if not title_col: title_col = col
                elif any(k in norm_c for k in ["حداقل", "min"]): min_col = col
                elif any(k in norm_c for k in ["حداکثر", "max"]): max_col = col
                elif "افزایش" in norm_c or "increase" in norm_c: inc_col = col
                elif "کاهش" in norm_c or "decrease" in norm_c: dec_col = col
                elif any(k in norm_c for k in ["قیمت", "price"]):
                    if not price_col: price_col = col

            if not title_col:
                title_col = df.columns[0]

            products_list = []
            for idx, row in df.iterrows():
                title = str(row[title_col]).strip() if pd.notna(row[title_col]) else ""
                if not title: continue
                min_p = int(row[min_col]) if min_col and pd.notna(row[min_col]) else None
                max_p = int(row[max_col]) if max_col and pd.notna(row[max_col]) else None
                inc_s = int(row[inc_col]) if inc_col and pd.notna(row[inc_col]) else None
                dec_s = int(row[dec_col]) if dec_col and pd.notna(row[dec_col]) else None
                last_p = int(row[price_col]) if price_col and pd.notna(row[price_col]) else None

                products_list.append({
                    "product_title": title,
                    "min_price": min_p,
                    "max_price": max_p,
                    "increase_step": inc_s,
                    "decrease_step": dec_s,
                    "last_price": last_p,
                })

            db_mgr = DatabaseManager(settings.DATABASE_PATH)
            count = db_mgr.bulk_import_product_rules(products_list)
            messagebox.showinfo("Success", f"Successfully imported pricing rules for {count} products into database!")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to import product rules: {e}")

    def copy_all_logs(self):
        text = self.log_area.get("1.0", "end-1c")
        if text.strip():
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            messagebox.showinfo("Copied", "All activity logs copied to clipboard!")

    def copy_selected_log(self):
        try:
            selected_text = self.log_area.get("sel.first", "sel.last")
            if selected_text:
                self.root.clipboard_clear()
                self.root.clipboard_append(selected_text)
                messagebox.showinfo("Copied", "Selected text copied to clipboard!")
        except tk.TclError:
            messagebox.showwarning("No Selection", "Please select text in the log area to copy.")

    def clear_activity_logs(self):
        if messagebox.askyesno("Confirm Clear", "Clear activity log view and log file?"):
            self.log_area.delete("1.0", "end")
            log_file = BASE_DIR / "downloads" / "bot_activity.log"
            if log_file.exists():
                try:
                    with open(log_file, "w", encoding="utf-8") as f:
                        f.write("")
                    self.last_log_size = 0
                except Exception as e:
                    logging.warning(f"Could not clear log file: {e}")

    def _attach_log_context_menu(self):
        self.log_menu = tk.Menu(
            self.log_area,
            tearoff=0,
            bg="#2b2b3b",
            fg=self.TEXT_COLOR,
            activebackground=self.ACCENT_COLOR,
            activeforeground="#11111b"
        )
        self.log_menu.add_command(label="📋 Copy All Logs", command=self.copy_all_logs)
        self.log_menu.add_command(label="✂️ Copy Selected Text", command=self.copy_selected_log)
        self.log_menu.add_separator()
        self.log_menu.add_command(label="Select All", command=lambda: self.log_area.tag_add("sel", "1.0", "end"))
        self.log_menu.add_separator()
        self.log_menu.add_command(label="🗑️ Clear Activity Logs", command=self.clear_activity_logs)

        def popup(event):
            self.log_menu.tk_popup(event.x_root, event.y_root)

        self.log_area.bind("<Button-3>", popup)

    def _get_session_expiration_info(self) -> str:
        session_file = BASE_DIR / "downloads" / "storage_state.json"
        if not session_file.exists():
            return "🔑 Session: Not Set"
        try:
            import json, base64
            from datetime import datetime, timezone
            with open(session_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            cookies = data.get("cookies", [])
            if not cookies:
                return "🔑 Session: Not Set"

            for c in cookies:
                if c.get("name") == "access-token":
                    exp = c.get("expires", 0)
                    val = c.get("value", "")
                    scopes = []
                    if val.count(".") == 2:
                        payload_b64 = val.split(".")[1]
                        payload_b64 += "=" * ((4 - len(payload_b64) % 4) % 4)
                        payload = json.loads(base64.b64decode(payload_b64).decode("utf-8"))
                        exp = payload.get("exp", exp)
                        scopes = payload.get("scopes", [])

                    # Check if token is a temporary pre-login OTP token
                    if "role:pre_login" in scopes or "pre_login" in str(scopes):
                        return "⚠️ Session: Pending OTP Login"

                    if exp > 0:
                        dt = datetime.fromtimestamp(exp, tz=timezone.utc)
                        now = datetime.now(timezone.utc)
                        days = (dt - now).days
                        if days >= 0:
                            return f"🔑 Session Valid: {dt.strftime('%Y-%m-%d %H:%M UTC')} ({days}d left)"
                        else:
                            return f"⚠️ Session Expired on {dt.strftime('%Y-%m-%d')}"
        except Exception:
            pass
        return "🔑 Session: Not Set"


def main():
    root = tk.Tk()
    app = SnappShopAppGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()

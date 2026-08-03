import sys
import os
import threading
import asyncio
import logging
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

# Ensure project root is in sys.path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

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

        self.btn_init_session = tk.Button(
            btn_frame,
            text="🔑 Login & Setup Session (OTP)",
            font=("Segoe UI", 10, "bold"),
            bg="#313244",
            fg=self.TEXT_COLOR,
            activebackground=self.WARN_COLOR,
            activeforeground="#000000",
            relief="flat",
            padx=12,
            pady=6,
            command=self.run_session_setup,
        )
        self.btn_init_session.pack(side="left", padx=5)

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
        self.vars["phone_var"].set(settings.SNAPSHOP_PHONE_NUMBER or "")
        self.vars["password_var"].set(settings.SNAPSHOP_PASSWORD or "")
        self.vars["url_var"].set(settings.SNAPSHOP_STORE_URL or "")
        self.vars["company_var"].set(settings.SNAPSHOP_COMPANY_NAME or "")
        self.vars["interval_var"].set(str(settings.CHECK_INTERVAL_MINUTES))

    def save_settings(self):
        try:
            env_path = BASE_DIR / ".env"
            env_content = f"""TELEGRAM_BOT_TOKEN="{settings.TELEGRAM_BOT_TOKEN}"
TELEGRAM_ADMIN_CHAT_ID="{settings.TELEGRAM_ADMIN_CHAT_ID or ''}"
SNAPSHOP_PHONE_NUMBER="{self.vars['phone_var'].get()}"
SNAPSHOP_PASSWORD="{self.vars['password_var'].get()}"
SNAPSHOP_STORE_URL="{self.vars['url_var'].get()}"
SNAPSHOP_COMPANY_NAME="{self.vars['company_var'].get()}"
CHECK_INTERVAL_MINUTES="{self.vars['interval_var'].get()}"
"""
            with open(env_path, "w", encoding="utf-8") as f:
                f.write(env_content)
            messagebox.showinfo("Success", "Settings saved successfully to .env file!")
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
                os.environ["HEADLESS"] = "false"
                asyncio.run(run_sync_cycle())
            except Exception as err:
                logging.error(f"Sync error: {err}")
            finally:
                self.is_running = False
                self.root.after(0, lambda: self.status_label.config(text="● Status: Idle", fg=self.SUCCESS_COLOR))
                self.root.after(0, lambda: self.btn_run_now.config(state="normal"))

        threading.Thread(target=task, daemon=True).start()

    def run_session_setup(self):
        if self.is_running:
            messagebox.showwarning("Busy", "A task is already running!")
            return

        self.is_running = True
        self.status_label.config(text="● Status: Session Setup...", fg=self.WARN_COLOR)

        def task():
            try:
                os.environ["HEADLESS"] = "false"
                from scripts.init_session import run_interactive_login
                asyncio.run(run_interactive_login())
            except Exception as err:
                logging.error(f"Session setup error: {err}")
            finally:
                self.is_running = False
                self.root.after(0, lambda: self.status_label.config(text="● Status: Idle", fg=self.SUCCESS_COLOR))

        threading.Thread(target=task, daemon=True).start()

    def toggle_scheduler(self):
        if not self.is_running:
            self.is_running = True
            self.status_label.config(text="● Status: Continuous Monitoring Active", fg=self.SUCCESS_COLOR)
            self.btn_toggle_scheduler.config(text="⏹ Stop Continuous Monitor", bg=self.DANGER_COLOR)
            
            def loop():
                import time
                while self.is_running:
                    os.environ["HEADLESS"] = "true"
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


def main():
    root = tk.Tk()
    app = SnappShopAppGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()

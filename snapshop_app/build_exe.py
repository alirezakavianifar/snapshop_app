import os
import sys
import shutil
import subprocess
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

def build():
    base_dir = Path(__file__).resolve().parent
    print(f"Building Standalone Windows Executable from {base_dir}...")

    # PyInstaller Arguments
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--onedir",
        "--windowed",
        "--name=SnappShopControlPanel",
        f"--paths={base_dir}",
        "--hidden-import=playwright",
        "--hidden-import=playwright.async_api",
        "--hidden-import=pandas",
        "--hidden-import=openpyxl",
        "--hidden-import=telegram",
        "--hidden-import=telegram.ext",
        "--hidden-import=jdatetime",
        "--hidden-import=pydantic",
        "--hidden-import=sqlite3",
        "--hidden-import=src.core.auth",
        "--hidden-import=src.core.browser",
        "--hidden-import=src.core.database",
        "--hidden-import=src.core.pricing",
        "--hidden-import=src.core.scraper",
        "--hidden-import=src.config.settings",
        "--hidden-import=src.telegram.bot",
        "--hidden-import=src.telegram.handlers",
        "--hidden-import=src.telegram.notifier",
        "--hidden-import=src.scheduler.job_runner",
        f"--add-data={base_dir / '.env.example'};.",
        f"--add-data={base_dir / 'README_FA.md'};.",
        f"--add-data={base_dir / 'src'};src",
    ]

    try:
        import playwright
        pw_driver = Path(playwright.__file__).parent / "driver"
        if pw_driver.exists():
            cmd.append(f"--add-data={pw_driver};playwright/driver")
            print(f"Bundling Playwright driver binary from {pw_driver}")
    except ImportError:
        pass

    cmd.append(str(base_dir / "gui.py"))

    print(f"Executing command: {' '.join(cmd)}")
    res = subprocess.run(cmd, cwd=str(base_dir))

    if res.returncode != 0:
        print("[ERROR] PyInstaller build failed!")
        sys.exit(1)

    dist_dir = base_dir / "dist" / "SnappShopControlPanel"
    downloads_dir = dist_dir / "downloads"
    downloads_dir.mkdir(parents=True, exist_ok=True)

    env_dest = dist_dir / ".env"
    env_src = base_dir / ".env"
    if env_src.exists():
        shutil.copy(env_src, env_dest)
        print(f"Copied local .env -> {env_dest}")
    elif (base_dir / ".env.example").exists():
        shutil.copy(base_dir / ".env.example", env_dest)
        print(f"Copied .env.example -> {env_dest}")

    state_src = base_dir / "downloads" / "storage_state.json"
    state_dest = downloads_dir / "storage_state.json"
    if state_src.exists():
        shutil.copy(state_src, state_dest)
        print(f"Copied storage_state.json -> {state_dest}")

    exe_path = dist_dir / "SnappShopControlPanel.exe"
    print("\n==================================================")
    print("✅ WINDOWS EXECUTABLE BUILD SUCCESSFUL!")
    print(f"• Executable Path: {exe_path}")
    print("==================================================\n")

if __name__ == "__main__":
    build()

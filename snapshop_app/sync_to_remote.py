import os
import sys
import time
import subprocess
from datetime import datetime
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# Configuration
LOCAL_ROOT = os.path.abspath(os.path.dirname(__file__))
REMOTE_HOST = "94.184.36.117"
REMOTE_USER = "Administrator"
REMOTE_PASS = "Ggn0bE/le71j&Eln"
REMOTE_ROOT = r"C:\Users\Administrator\projects\snapshop_app\snapshop_app\snapshop_app"

# Directories/Files to ignore
IGNORED_PATTERNS = [
    r"\.git",
    r"\.venv",
    r"__pycache__",
    r"\.idea",
    r"\.pytest_cache",
    r"\.DS_Store",
    r"sync_to_remote\.py",
    r"sync_test\.txt",
    r"\.log$",
    r"\.pyc$",
    r"\.tmp$",
    r"~\$",
]

import re
IGNORED_REGEX = [re.compile(p, re.IGNORECASE) for p in IGNORED_PATTERNS]

def is_ignored(path):
    rel_path = os.path.relpath(path, LOCAL_ROOT)
    for pattern in IGNORED_REGEX:
        if pattern.search(rel_path) or pattern.search(path):
            return True
    return False

def run_powershell_script(ps_code):
    """Executes inline PowerShell script safely."""
    # Write temporary powershell script
    temp_ps1 = os.path.join(os.environ.get("TEMP", LOCAL_ROOT), "_remote_sync_tmp.ps1")
    with open(temp_ps1, "w", encoding="utf-8") as f:
        f.write(ps_code)
    
    cmd = ["powershell", "-ExecutionPolicy", "Bypass", "-File", temp_ps1]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    
    try:
        os.remove(temp_ps1)
    except Exception:
        pass
        
    return res

def upload_file_remote(local_path):
    if is_ignored(local_path) or not os.path.isfile(local_path):
        return

    rel_path = os.path.relpath(local_path, LOCAL_ROOT)
    remote_dest = os.path.join(REMOTE_ROOT, rel_path)

    ps_code = f"""
$pass = '{REMOTE_PASS}'
$secpasswd = ConvertTo-SecureString $pass -AsPlainText -Force
$mycreds = New-Object System.Management.Automation.PSCredential ('{REMOTE_USER}', $secpasswd)
$so = New-PSSessionOption -SkipCACheck -SkipCNCheck -SkipRevocationCheck

try {{
    $session = New-PSSession -ComputerName '{REMOTE_HOST}' -Credential $mycreds -UseSSL -SessionOption $so -ErrorAction Stop
    $destDir = Split-Path '{remote_dest}' -Parent
    Invoke-Command -Session $session -ScriptBlock {{ param($d) New-Item -ItemType Directory -Force -Path $d | Out-Null }} -ArgumentList $destDir
    Copy-Item -Path '{local_path}' -Destination '{remote_dest}' -ToSession $session -Force
    Remove-PSSession $session
    Write-Host "SYNCED"
}} catch {{
    Write-Host "ERROR: $_"
}}
"""
    res = run_powershell_script(ps_code)
    timestamp = datetime.now().strftime("%H:%M:%S")
    if "SYNCED" in res.stdout:
        print(f"[{timestamp}] [SYNCED] {rel_path} -> Remote", flush=True)
    else:
        print(f"[{timestamp}] [FAILED] {rel_path}: {res.stdout.strip() or res.stderr.strip()}", flush=True)

def remove_file_remote(local_path):
    if is_ignored(local_path):
        return

    rel_path = os.path.relpath(local_path, LOCAL_ROOT)
    remote_dest = os.path.join(REMOTE_ROOT, rel_path)

    ps_code = f"""
$pass = '{REMOTE_PASS}'
$secpasswd = ConvertTo-SecureString $pass -AsPlainText -Force
$mycreds = New-Object System.Management.Automation.PSCredential ('{REMOTE_USER}', $secpasswd)
$so = New-PSSessionOption -SkipCACheck -SkipCNCheck -SkipRevocationCheck

try {{
    $session = New-PSSession -ComputerName '{REMOTE_HOST}' -Credential $mycreds -UseSSL -SessionOption $so -ErrorAction Stop
    Invoke-Command -Session $session -ScriptBlock {{ param($f) Remove-Item -Path $f -Force -Recurse -ErrorAction SilentlyContinue }} -ArgumentList '{remote_dest}'
    Remove-PSSession $session
    Write-Host "DELETED"
}} catch {{
    Write-Host "ERROR: $_"
}}
"""
    res = run_powershell_script(ps_code)
    timestamp = datetime.now().strftime("%H:%M:%S")
    if "DELETED" in res.stdout:
        print(f"[{timestamp}] [DELETED] {rel_path} from Remote", flush=True)
    else:
        print(f"[{timestamp}] [DELETE FAILED] {rel_path}: {res.stdout.strip() or res.stderr.strip()}", flush=True)

def full_sync():
    print("Performing initial full sync scan...", flush=True)
    count = 0
    for root, dirs, files in os.walk(LOCAL_ROOT):
        # Filter dirs in-place
        dirs[:] = [d for d in dirs if not is_ignored(os.path.join(root, d))]
        for file in files:
            full_path = os.path.join(root, file)
            if not is_ignored(full_path):
                upload_file_remote(full_path)
                count += 1
    print(f"Full sync complete ({count} files verified/uploaded).", flush=True)

class SyncHandler(FileSystemEventHandler):
    def __init__(self):
        self.last_sync = {}

    def on_modified(self, event):
        if not event.is_directory:
            now = time.time()
            if event.src_path in self.last_sync and (now - self.last_sync[event.src_path]) < 0.5:
                return
            self.last_sync[event.src_path] = now
            upload_file_remote(event.src_path)

    def on_created(self, event):
        if not event.is_directory:
            upload_file_remote(event.src_path)

    def on_deleted(self, event):
        if not event.is_directory:
            remove_file_remote(event.src_path)

if __name__ == "__main__":
    print("=" * 60, flush=True)
    print(f"  SnapShop App - Remote Live Sync Service", flush=True)
    print(f"  Local Path : {LOCAL_ROOT}", flush=True)
    print(f"  Remote Server : {REMOTE_HOST}", flush=True)
    print(f"  Remote Path : {REMOTE_ROOT}", flush=True)
    print("=" * 60, flush=True)

    if "--full-sync" in sys.argv:
        full_sync()

    event_handler = SyncHandler()
    observer = Observer()
    observer.schedule(event_handler, LOCAL_ROOT, recursive=True)
    observer.start()

    print("\n[ACTIVE] Live file watcher started. Watching for changes... (Press Ctrl+C to stop)", flush=True)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

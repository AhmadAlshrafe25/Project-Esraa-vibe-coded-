import os
import json
import shutil
from pathlib import Path
import requests
from config.settings import PROJECT_ROOT

DB_PATH = PROJECT_ROOT / "data" / "memory.db"
DEFAULT_DRIVE_DIR = Path.home() / "GoogleDrive" / "ProjectEzra_Memory"

POSSIBLE_GDRIVE_ROOTS = [
    Path.home() / "GoogleDrive",
    Path.home() / "Google Drive",
    Path.home() / "gdrive",
    Path.home() / "google-drive",
    Path.home() / "Drive",
    Path.home() / ".local" / "share" / "google-drive"
]

class GDriveSync:
    """Two-way Google Drive synchronization: Loads memory FROM Google Drive and saves updates TO Google Drive."""

    @staticmethod
    def get_drive_target_dir() -> Path:
        """Finds or prepares the Google Drive memory directory."""
        # 1. Custom configured path in environment
        custom_env = os.getenv("GDRIVE_PATH", "").strip()
        if custom_env:
            p = Path(custom_env)
            p.mkdir(parents=True, exist_ok=True)
            return p

        # 2. Check GVFS GNOME Online Accounts mounts (dynamic UID for Arch/Debian/Fedora)
        uid = os.getuid() if hasattr(os, "getuid") else 1000
        gvfs_dir = Path(f"/run/user/{uid}/gvfs")
        if gvfs_dir.exists():
            for entry in gvfs_dir.iterdir():
                if "google-drive" in entry.name.lower():
                    target = entry / "ProjectEzra_Memory"
                    target.mkdir(parents=True, exist_ok=True)
                    return target

        # 3. Check standard filesystem Google Drive locations
        for root in POSSIBLE_GDRIVE_ROOTS:
            if root.exists() and root.is_dir():
                target = root / "ProjectEzra_Memory"
                target.mkdir(parents=True, exist_ok=True)
                return target

        # 4. Default GoogleDrive directory in user home
        DEFAULT_DRIVE_DIR.mkdir(parents=True, exist_ok=True)
        return DEFAULT_DRIVE_DIR

    @staticmethod
    def pull_from_drive() -> bool:
        """Loads and restores memory FROM Google Drive on startup."""
        target_dir = GDriveSync.get_drive_target_dir()
        drive_db = target_dir / "memory.db"
        drive_json = target_dir / "ezra_gdrive_sync.json"

        # If a newer database exists on Google Drive, take it!
        if drive_db.exists() and drive_db.stat().st_size > 0:
            local_mtime = DB_PATH.stat().st_mtime if DB_PATH.exists() else 0
            drive_mtime = drive_db.stat().st_mtime
            
            # If Google Drive has database or local is missing/older
            if not DB_PATH.exists() or drive_mtime >= local_mtime:
                DB_PATH.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(drive_db, DB_PATH)
                print(f"\033[1;32m[☁️ Google Drive Sync]: Restored latest memory.db from {drive_db}!\033[0m")
                return True

        drive_dna = target_dir / "voice_genetic_code.json"
        local_dna = PROJECT_ROOT / "data" / "voice_genetic_code.json"
        if drive_dna.exists():
            local_dna_mtime = local_dna.stat().st_mtime if local_dna.exists() else 0
            if not local_dna.exists() or drive_dna.stat().st_mtime > local_dna_mtime:
                local_dna.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(drive_dna, local_dna)
                print(f"\033[1;32m[☁️ Google Drive Sync]: Restored latest voice genetic code from Google Drive!\033[0m")

        if drive_json.exists():
            print(f"\033[1;32m[☁️ Google Drive Sync]: Found backup JSON in Google Drive: {drive_json}\033[0m")
            return True

        return False

    @staticmethod
    def push_to_drive() -> dict:
        """Saves all current memory, conversations, and learned facts TO Google Drive."""
        from jarvis.memory import memory_service
        target_dir = GDriveSync.get_drive_target_dir()
        
        # 1. Export clean JSON backup
        backup_json = memory_service.export_backup_json()
        dest_json = target_dir / "ezra_gdrive_sync.json"
        shutil.copy2(backup_json, dest_json)

        # 2. Copy the actual SQLite database file directly
        dest_db = target_dir / "memory.db"
        if DB_PATH.exists():
            shutil.copy2(DB_PATH, dest_db)

        # 3. Copy voice genetic code profile
        dna_file = PROJECT_ROOT / "data" / "voice_genetic_code.json"
        if dna_file.exists():
            shutil.copy2(dna_file, target_dir / "voice_genetic_code.json")

        # 3. Optional: Direct Cloud Google Drive API sync if OAuth token is provided
        access_token = os.getenv("GDRIVE_ACCESS_TOKEN", "").strip()
        cloud_status = "local_drive_synced"
        if access_token:
            try:
                headers = {"Authorization": f"Bearer {access_token}"}
                files = {
                    'data': ('metadata', json.dumps({'name': 'ezra_memory.json'}), 'application/json'),
                    'file': open(dest_json, 'rb')
                }
                r = requests.post(
                    "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart",
                    headers=headers,
                    files=files,
                    timeout=5.0
                )
                if r.status_code in (200, 201):
                    cloud_status = "cloud_api_synced"
            except Exception:
                pass

        return {
            "status": "success",
            "cloud_status": cloud_status,
            "target_dir": str(target_dir),
            "files_synced": ["memory.db", "ezra_gdrive_sync.json"]
        }

gdrive_sync = GDriveSync()

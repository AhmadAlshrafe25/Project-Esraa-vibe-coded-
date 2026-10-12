import os
import json
import shutil
from pathlib import Path
from config.settings import PROJECT_ROOT
from jarvis.memory import memory_service

# Google Drive sync directories:
# On Linux, users often mount or sync Google Drive using GNOME Online Accounts / Google-Drive-OCamlFuse / rclone / Insync:
# Check standard mount locations:
POSSIBLE_GDRIVE_DIRS = [
    Path.home() / "GoogleDrive",
    Path.home() / "Google Drive",
    Path.home() / "gdrive",
    Path.home() / ".local" / "share" / "google-drive"
]

class GDriveSync:
    """Handles Google Drive sync and export for Project Ezra chats and learned facts."""

    @staticmethod
    def sync_to_drive() -> dict:
        backup_file = memory_service.export_backup_json()
        
        # Look for existing mounted Google Drive folder
        target_dir = None
        for p in POSSIBLE_GDRIVE_DIRS:
            if p.exists() and p.is_dir():
                target_dir = p / "ProjectEzra_Backups"
                break
        
        # If no local Google Drive mount folder found yet, save in data/exports and prepare it for easy upload
        if not target_dir:
            export_dir = PROJECT_ROOT / "data" / "gdrive_sync"
            export_dir.mkdir(parents=True, exist_ok=True)
            target_path = export_dir / backup_file.name
            shutil.copy2(backup_file, target_path)
            return {
                "status": "ready_for_upload",
                "message": f"Memory backup created at {target_path}. Connect Google Drive via rclone or GNOME Online Accounts for automatic live background sync.",
                "backup_file": str(target_path)
            }

        target_dir.mkdir(parents=True, exist_ok=True)
        dest = target_dir / backup_file.name
        shutil.copy2(backup_file, dest)
        return {
            "status": "synced",
            "message": f"Successfully backed up all chats and learned memory to Google Drive at {dest}."
        }

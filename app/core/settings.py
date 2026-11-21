from PySide6.QtCore import QStandardPaths
from pathlib import Path
import json

APP_DIR = Path(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation))
APP_DIR.mkdir(parents=True, exist_ok=True)
SETTINGS_FILE = APP_DIR / "settings.json"

DEFAULTS = {
    "output_dir": str(Path.home() / "Movies" / "AI CAR CLIP SORTER PRO"),
    "last_source": "",
    "detector": "Content",
    "threshold": 12.0,
    "min_scene": 0.15,
    "auto_export": True,
    "auto_upload": False,
    "youtube_client_secrets": "",
    "privacy": "private",
    "upload_title_prefix": "Car Clip",
    "upload_description": "",
    "upload_tags": ["cars", "car edits"],
}

def load_settings():
    data = DEFAULTS.copy()
    try:
        if SETTINGS_FILE.exists():
            data.update(json.loads(SETTINGS_FILE.read_text(encoding="utf-8")))
    except Exception:
        pass
    return data

def save_settings(data):
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

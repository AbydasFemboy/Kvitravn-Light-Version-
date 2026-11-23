"""Einfacher JSON-Speicher fuer die Bot-Daten (users.json, xp.json, modlog.json, ...)."""
import json
from datetime import datetime
from pathlib import Path

DATA_DIR = Path("data")
try:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
except OSError:
    pass  # Falls kein Schreibzugriff: Daten werden beim Fehlen nur nicht persistiert.


def load(name, default=None):
    """Laedt data/<name>.json; bei Fehlern/fehlendem File wird default zurueckgegeben."""
    if default is None:
        default = {}
    path = DATA_DIR / f"{name}.json"
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


def save(name, data):
    path = DATA_DIR / f"{name}.json"
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except (OSError, TypeError):
        pass


def fmt_time(ts):
    try:
        return datetime.fromtimestamp(ts).strftime("%d.%m. %H:%M")
    except (TypeError, ValueError, OSError):
        return str(ts)

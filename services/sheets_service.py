"""
Sheets / Data Service — handles reading and writing pilot, drone, and mission data.
Primary source: CSV files in data/ directory.
Optional: Google Sheets 2-way sync via gspread OAuth2 user login.

Auth flow:
  1. Create an OAuth 2.0 Client ID (Desktop) at console.cloud.google.com
  2. Download the client_secret JSON → save as credentials.json in project root
  3. Set GOOGLE_SHEET_ID in .env
  4. On first run, a browser opens for Google login → token is saved locally
  5. No service-account key needed!
"""
from __future__ import annotations
import csv
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Path configuration
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
PILOT_CSV = DATA_DIR / "pilot_roster.csv"
DRONE_CSV = DATA_DIR / "drone_fleet.csv"
MISSION_CSV = DATA_DIR / "missions.csv"

# OAuth2 credentials paths
OAUTH_CREDS_FILE = PROJECT_ROOT / "credentials.json"          # client secret
OAUTH_TOKEN_FILE = PROJECT_ROOT / "authorized_user.json"      # saved token

# ---------------------------------------------------------------------------
# Google Sheets integration (OAuth2 user login — no service-account key)
# ---------------------------------------------------------------------------
_sheets_client = None
_spreadsheet = None


def _init_google_sheets() -> bool:
    """
    Attempt to initialise gspread with OAuth2 user credentials.
    Falls back to CSV-only mode if credentials are missing or auth fails.
    """
    global _sheets_client, _spreadsheet
    try:
        from dotenv import load_dotenv
        load_dotenv()

        sheet_id = os.getenv("GOOGLE_SHEET_ID", "")
        if not sheet_id:
            logger.info("GOOGLE_SHEET_ID not set in .env — using CSV only.")
            return False

        if not OAUTH_CREDS_FILE.exists():
            logger.info(
                f"OAuth credentials file not found at {OAUTH_CREDS_FILE}. "
                "Download 'Desktop' OAuth client JSON from Google Cloud Console "
                "and save it as credentials.json in the project root."
            )
            return False

        import gspread

        # gspread.oauth() handles the full OAuth2 flow:
        # - First run: opens browser for Google login
        # - Subsequent runs: uses saved token from authorized_user.json
        _sheets_client = gspread.oauth(
            credentials_filename=str(OAUTH_CREDS_FILE),
            authorized_user_filename=str(OAUTH_TOKEN_FILE),
        )
        _spreadsheet = _sheets_client.open_by_key(sheet_id)
        logger.info(f"✅ Google Sheets connected: {_spreadsheet.title}")
        return True

    except ImportError:
        logger.warning("gspread not installed — using CSV only. Run: pip install gspread")
        return False
    except Exception as e:
        logger.warning(f"Google Sheets init failed: {e}. Falling back to CSV.")
        return False


def _retry(func, retries: int = 3):
    """Simple retry wrapper with exponential backoff."""
    import time
    for attempt in range(retries):
        try:
            return func()
        except Exception as e:
            wait = 2 ** attempt
            logger.warning(f"Retry {attempt + 1}/{retries} after {wait}s: {e}")
            time.sleep(wait)
    raise RuntimeError(f"All {retries} retries failed for {func.__name__}")


def is_sheets_connected() -> bool:
    """Check if Google Sheets is currently connected."""
    return _spreadsheet is not None


# ---------------------------------------------------------------------------
# READ operations
# ---------------------------------------------------------------------------

def load_pilots_df() -> pd.DataFrame:
    """Load pilot roster as a DataFrame."""
    if _spreadsheet:
        try:
            ws = _retry(lambda: _spreadsheet.worksheet("Pilots"))
            records = ws.get_all_records()
            if records:
                logger.info(f"Loaded {len(records)} pilots from Google Sheets.")
                return pd.DataFrame(records)
        except Exception as e:
            logger.warning(f"Sheets read failed, falling back to CSV: {e}")
    return pd.read_csv(PILOT_CSV)


def load_drones_df() -> pd.DataFrame:
    """Load drone fleet as a DataFrame."""
    if _spreadsheet:
        try:
            ws = _retry(lambda: _spreadsheet.worksheet("Drones"))
            records = ws.get_all_records()
            if records:
                logger.info(f"Loaded {len(records)} drones from Google Sheets.")
                return pd.DataFrame(records)
        except Exception as e:
            logger.warning(f"Sheets read failed, falling back to CSV: {e}")
    return pd.read_csv(DRONE_CSV)


def load_missions_df() -> pd.DataFrame:
    """Load missions as a DataFrame."""
    if _spreadsheet:
        try:
            ws = _retry(lambda: _spreadsheet.worksheet("Missions"))
            records = ws.get_all_records()
            if records:
                logger.info(f"Loaded {len(records)} missions from Google Sheets.")
                return pd.DataFrame(records)
        except Exception as e:
            logger.warning(f"Sheets read failed, falling back to CSV: {e}")
    return pd.read_csv(MISSION_CSV)


# ---------------------------------------------------------------------------
#  Model-level loaders (returns list of dataclass instances)
# ---------------------------------------------------------------------------
from models.pilot import Pilot
from models.drone import Drone
from models.mission import Mission


def load_pilots() -> List[Pilot]:
    df = load_pilots_df()
    return [Pilot.from_dict(row) for _, row in df.iterrows()]


def load_drones() -> List[Drone]:
    df = load_drones_df()
    return [Drone.from_dict(row) for _, row in df.iterrows()]


def load_missions() -> List[Mission]:
    df = load_missions_df()
    return [Mission.from_dict(row) for _, row in df.iterrows()]


# ---------------------------------------------------------------------------
# WRITE operations
# ---------------------------------------------------------------------------

def _save_df_to_csv(df: pd.DataFrame, path: Path) -> None:
    """Persist a DataFrame to its CSV file."""
    df.to_csv(path, index=False)
    logger.info(f"Saved {len(df)} rows to {path.name}")


def _sync_df_to_sheet(df: pd.DataFrame, worksheet_name: str) -> None:
    """Write a DataFrame back to a Google Sheet worksheet (full replace)."""
    if not _spreadsheet:
        return
    try:
        ws = _retry(lambda: _spreadsheet.worksheet(worksheet_name))
        ws.clear()
        # Convert all values to strings to avoid serialization issues
        header = df.columns.values.tolist()
        rows = df.astype(str).values.tolist()
        ws.update([header] + rows)
        logger.info(f"✅ Synced {worksheet_name} to Google Sheets ({len(rows)} rows).")
    except Exception as e:
        logger.error(f"Failed to sync {worksheet_name} to Sheets: {e}")


def save_pilots(pilots: List[Pilot]) -> None:
    """Save pilots list to CSV + optionally Google Sheets."""
    df = pd.DataFrame([p.to_dict() for p in pilots])
    _save_df_to_csv(df, PILOT_CSV)
    _sync_df_to_sheet(df, "Pilots")


def save_drones(drones: List[Drone]) -> None:
    df = pd.DataFrame([d.to_dict() for d in drones])
    _save_df_to_csv(df, DRONE_CSV)
    _sync_df_to_sheet(df, "Drones")


def save_missions(missions: List[Mission]) -> None:
    df = pd.DataFrame([m.to_dict() for m in missions])
    _save_df_to_csv(df, MISSION_CSV)
    _sync_df_to_sheet(df, "Missions")


# ---------------------------------------------------------------------------
# Decision log append
# ---------------------------------------------------------------------------
DECISION_LOG_PATH = DATA_DIR / "decision_log.txt"


def append_decision_log(entry: str) -> None:
    """Append a decision entry to the running decision log."""
    from datetime import datetime
    with open(DECISION_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"\n[{datetime.now().isoformat()}] {entry}\n")
    logger.info(f"Decision logged: {entry[:80]}...")


# ---------------------------------------------------------------------------
# Initialise Sheets on module load (non-blocking)
# ---------------------------------------------------------------------------
_init_google_sheets()

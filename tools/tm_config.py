"""
CapyMorph — central configuration.

All paths are resolved relative to the installed TurtleWoW client.
The project lives in <client>/CapyMorph/ to avoid colliding with the
client's own case-insensitive `Data` folder on Windows.

Nothing here modifies the client. Read-only by default.
"""
from __future__ import annotations

import os
import sys


def _is_client_dir(d: str) -> bool:
    """A client root has a Data/ folder containing MPQ archives."""
    data = os.path.join(d, "Data")
    if not os.path.isdir(data):
        return False
    try:
        return any(f.lower().endswith(".mpq") for f in os.listdir(data))
    except OSError:
        return False


def _find_client_root(start: str) -> str:
    """Walk up from `start` to find the TurtleWoW client root (has Data/*.mpq)."""
    d = os.path.abspath(start)
    for _ in range(8):
        if _is_client_dir(d):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return ""


# PROJECT_ROOT = the CapyMorph folder holding data/output/backups.
# - frozen (onedir): exe sits at <PROJECT_ROOT>/app/CapyMorph.exe, so the
#   project root is the exe dir's parent — independent of the folder's NAME, so
#   a friend can rename/relocate the whole folder and it still finds its data/.
# - source: <repo>/tools/tm_config.py -> project root is tools/'s parent.
if getattr(sys, "frozen", False):
    _BASE = os.path.dirname(os.path.abspath(sys.executable))   # app/
    PROJECT_ROOT = os.path.dirname(_BASE)                      # folder holding app/ + data/
else:
    _BASE = os.path.dirname(os.path.abspath(__file__))         # tools/
    PROJECT_ROOT = os.path.dirname(_BASE)                      # CapyMorph

# Client root = nearest ancestor with Data/*.mpq, so the app can live anywhere
# inside the client tree. Falls back to the project's parent.
CLIENT_ROOT = _find_client_root(_BASE) or os.path.dirname(PROJECT_ROOT)
# Client Data dir holds all MPQ archives
CLIENT_DATA = os.path.join(CLIENT_ROOT, "Data")

# --- CapyMorph working dirs ----------------------------------------------
TOOLS_DIR = os.path.join(PROJECT_ROOT, "tools")
GUI_DIR = os.path.join(PROJECT_ROOT, "gui")
DATA_DIR = os.path.join(PROJECT_ROOT, "data")        # generated DB / extracted DBCs
REPORTS_DIR = os.path.join(PROJECT_ROOT, "reports")  # markdown reports
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")    # generated patch-Z.mpq staging
BACKUPS_DIR = os.path.join(PROJECT_ROOT, "backups")  # backups of anything we touch

# --- DBC paths inside MPQ ----------------------------------------------------
DBC_INTERNAL_DIR = "DBFilesClient"

# DBCs the project depends on (internal MPQ path uses backslash like the client)
TARGET_DBCS = {
    "ItemDisplayInfo": r"DBFilesClient\ItemDisplayInfo.dbc",
    "CreatureDisplayInfo": r"DBFilesClient\CreatureDisplayInfo.dbc",
    "CreatureModelData": r"DBFilesClient\CreatureModelData.dbc",
    "SpellShapeshiftForm": r"DBFilesClient\SpellShapeshiftForm.dbc",
    # supporting DBCs used later for item-name -> displayid resolution
    "ItemDisplayInfo_extra": r"DBFilesClient\ItemDisplayInfo.dbc",
}

# Final patch name. MPQs load alphabetically, so patch-Z loads LAST = wins.
OUTPUT_PATCH_NAME = "patch-Z.mpq"


def ensure_dirs() -> None:
    """Create CapyMorph working dirs (never touches the client)."""
    for d in (DATA_DIR, REPORTS_DIR, OUTPUT_DIR, BACKUPS_DIR, TOOLS_DIR, GUI_DIR):
        os.makedirs(d, exist_ok=True)


if __name__ == "__main__":
    ensure_dirs()
    print("PROJECT_ROOT:", PROJECT_ROOT)
    print("CLIENT_ROOT :", CLIENT_ROOT)
    print("CLIENT_DATA :", CLIENT_DATA)
    print("Data dir exists:", os.path.isdir(CLIENT_DATA))

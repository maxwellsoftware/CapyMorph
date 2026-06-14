r"""
CapyMorph — itemcache.wdb reader (real item names).

The 1.12 client caches every item it receives from the server into
<client>\WDB\itemcache.wdb. Each record gives the item's name AND its
ItemDisplayInfo DisplayID — the link that is otherwise server-side and absent
from the client's MPQs.

Structure (verified on a real TurtleWoW cache, build 5875, locale 'BGne'):

    header: char magic[4]='BDIW', uint32 build, char locale[4], uint32, uint32   (20 bytes)
    records (until itemID==0):
        uint32 itemID
        uint32 blockSize           (0 => item does not exist; ends the file)
        <blockSize bytes>:
            uint32 class           (2 = weapon)
            uint32 subClass        (weapon: 10 = staff, ...)
            cstring name[4]        (4 NUL-terminated names; [0] is the real one)
            uint32 displayID       <-- ItemDisplayInfo ID
            uint32 quality
            ... (more fields, not needed)

Only items the player has actually encountered are cached; the file grows over
time. This is read-only and optional — absence just means no name search.
"""
from __future__ import annotations

import os
import struct
from typing import Dict, Optional

import tm_config as cfg

WDB_PATH = os.path.join(cfg.CLIENT_ROOT, "WDB", "itemcache.wdb")
# Snapshot kept inside the project so name search still works after the WDB
# blocker file is restored (the live cache then no longer exists).
SNAPSHOT_PATH = os.path.join(cfg.DATA_DIR, "itemcache.wdb")
HEADER_SIZE = 20


def active_path() -> Optional[str]:
    """Prefer the live client cache; fall back to our project snapshot."""
    if os.path.exists(WDB_PATH):
        return WDB_PATH
    if os.path.exists(SNAPSHOT_PATH):
        return SNAPSHOT_PATH
    return None


def snapshot() -> Optional[str]:
    """Copy the live itemcache.wdb into the project (data/). Returns dest or None."""
    if not os.path.exists(WDB_PATH):
        return None
    import shutil
    cfg.ensure_dirs()
    shutil.copy2(WDB_PATH, SNAPSHOT_PATH)
    return SNAPSHOT_PATH


class ItemCacheEntry:
    __slots__ = ("item_id", "name", "display_id", "item_class", "subclass", "quality")

    def __init__(self, item_id, name, display_id, item_class, subclass, quality):
        self.item_id = item_id
        self.name = name
        self.display_id = display_id
        self.item_class = item_class
        self.subclass = subclass
        self.quality = quality


def _parse_record(item_id: int, data: bytes) -> Optional[ItemCacheEntry]:
    try:
        item_class, subclass = struct.unpack_from("<II", data, 0)
        p = 8
        names = []
        for _ in range(4):
            end = data.find(b"\x00", p)
            if end < 0:
                return None
            names.append(data[p:end].decode("latin-1"))
            p = end + 1
        display_id, quality = struct.unpack_from("<II", data, p)
        return ItemCacheEntry(item_id, names[0], display_id, item_class, subclass, quality)
    except Exception:
        return None


def load(path: Optional[str] = None) -> Dict[int, ItemCacheEntry]:
    """Parse itemcache.wdb -> {itemID: ItemCacheEntry}. Empty dict if absent."""
    path = path or active_path()
    if not path or not os.path.exists(path):
        return {}
    with open(path, "rb") as f:
        raw = f.read()
    if len(raw) < HEADER_SIZE or raw[:4] != b"BDIW":
        return {}
    out: Dict[int, ItemCacheEntry] = {}
    off = HEADER_SIZE
    while off + 8 <= len(raw):
        item_id, size = struct.unpack_from("<II", raw, off)
        if item_id == 0 or size == 0 or off + 8 + size > len(raw):
            break
        e = _parse_record(item_id, raw[off + 8:off + 8 + size])
        if e and e.name:
            out[item_id] = e
        off += 8 + size
    return out


def display_to_names(path: Optional[str] = None) -> Dict[int, list]:
    """Build {displayID: [item names]} from the cache (for name search)."""
    by_disp: Dict[int, list] = {}
    for e in load(path).values():
        if e.display_id:
            by_disp.setdefault(e.display_id, [])
            if e.name not in by_disp[e.display_id]:
                by_disp[e.display_id].append(e.name)
    return by_disp


def stats(path: Optional[str] = None) -> dict:
    path = path or active_path()
    items = load(path)
    weapons = sum(1 for e in items.values() if e.item_class == 2)
    return {"source": path, "items": len(items), "weapons": weapons}


if __name__ == "__main__":
    s = stats()
    print("itemcache.wdb:", s)
    cache = load()
    for iid in list(cache)[:10]:
        e = cache[iid]
        print(f"  {iid}: '{e.name}' -> display {e.display_id} (class {e.item_class})")

r"""
CapyMorph — weapon appearance database (Stage 3).

Built entirely from the client's effective ItemDisplayInfo.dbc. Each entry is
one DisplayID = one selectable weapon appearance:

    display_id   f0  (the ItemDisplayInfo row ID)
    model        f1  main/left model (.mdx)
    model_off    f2  secondary/right model
    texture      f3  main model texture
    texture_off  f4  secondary model texture
    icon         f5  inventory icon
    category     derived from the model-name prefix (sword/axe/.../other)
    is_weapon    whether category is a known weapon type
    name         human-readable label derived from the model name

Real item names ("Doomhammer") are NOT present in a vanilla client — they live
in server data / ItemCache.wdb (populated only after login). `item_name` is left
empty here and can be filled later by an optional WDB importer.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from typing import List, Optional

import tm_config as cfg
import tm_dbc

# ItemDisplayInfo field map — established empirically in Stage 2.
F_ID, F_MODEL, F_MODEL_OFF, F_TEX, F_TEX_OFF, F_ICON = 0, 1, 2, 3, 4, 5

# Weapon model-name prefixes, derived from the real prefix distribution.
WEAPON_PREFIXES = {
    "sword", "axe", "knife", "dagger", "stave", "staff", "hammer", "mace",
    "shield", "bow", "wand", "firearm", "gun", "crossbow", "polearm", "spear",
    "thrown", "buckler", "offhand", "glave", "glaive", "club", "hand", "totem",
    "quiver", "fishingpole", "fishpole",
}

DB_PATH = os.path.join(cfg.DATA_DIR, "weapon_db.json")


# inventory_type -> human slot name (the equipment slots that have a visible look)
SLOT_NAMES = {
    1: "Head", 3: "Shoulder", 5: "Chest", 20: "Chest", 6: "Waist", 7: "Legs",
    8: "Feet", 9: "Wrist", 10: "Hands", 16: "Back", 19: "Tabard", 4: "Shirt",
    14: "Shield", 23: "Held (off-hand)", 28: "Relic",
    13: "One-Hand", 21: "Main Hand", 22: "Off Hand", 17: "Two-Hand",
    15: "Bow", 26: "Gun/Wand", 25: "Thrown",
}


@dataclass
class DisplayEntry:
    display_id: int
    model: str
    model_off: str
    texture: str
    texture_off: str
    icon: str
    category: str
    is_weapon: bool
    name: str
    item_name: str = ""  # filled later from ItemCache.wdb / world DB
    slot: int = 0         # inventory_type, filled from the item DB at load
    item_id: int = 0      # a representative itemID with this look (per-char transmog)

    @property
    def slot_name(self) -> str:
        return SLOT_NAMES.get(self.slot, "")


def _prefix(model: str) -> str:
    base = model.rsplit(".", 1)[0]
    return base.split("_", 1)[0].lower() if base else ""


def _derive_name(model: str) -> str:
    """'Sword_2H_Claymore_A_01.mdx' -> 'Sword 2H Claymore A 01'."""
    base = model.rsplit(".", 1)[0]
    return base.replace("_", " ").strip()


def build_from_dbc(dbc: tm_dbc.DBC) -> List[DisplayEntry]:
    # Body armor (chest/legs/…) has no model — its look is texture components.
    # Include such display rows too, but only when an item actually uses them
    # (known from the world-DB slot map), so the list stays meaningful.
    try:
        import tm_itemdb
        item_slots = tm_itemdb.load_display_slots()
    except Exception:
        item_slots = {}
    entries: List[DisplayEntry] = []
    for r in range(dbc.record_count):
        did = dbc.field_uint(r, F_ID)
        model = dbc.get_string(dbc.field_uint(r, F_MODEL))
        if not model and did not in item_slots:
            continue  # no model and not used by any item = nothing useful
        cat = _prefix(model) if model else "armor"
        is_weapon = cat in WEAPON_PREFIXES
        entries.append(DisplayEntry(
            display_id=did,
            model=model,
            model_off=dbc.get_string(dbc.field_uint(r, F_MODEL_OFF)),
            texture=dbc.get_string(dbc.field_uint(r, F_TEX)),
            texture_off=dbc.get_string(dbc.field_uint(r, F_TEX_OFF)),
            icon=dbc.get_string(dbc.field_uint(r, F_ICON)),
            category=cat,
            is_weapon=is_weapon,
            name=_derive_name(model) if model else "",
        ))
    return entries


def client_signature() -> dict:
    """Cheap fingerprint of the current client's effective ItemDisplayInfo.
    Compared by archive name + size (NOT path), so an identical client on a
    friend's PC reuses the prebuilt DB, while a different/updated client triggers
    a rebuild. Makes the .exe drop-in standalone on any 1.18 client."""
    from stage2_dbc_explorer import find_effective_archive
    internal = cfg.TARGET_DBCS["ItemDisplayInfo"]
    try:
        arc = find_effective_archive(internal)
        return {"archive": os.path.basename(arc), "archive_size": os.path.getsize(arc)}
    except Exception:
        return {"archive": "", "archive_size": 0}


def build_and_save(dbc: Optional[tm_dbc.DBC] = None) -> dict:
    cfg.ensure_dirs()
    if dbc is None:
        from stage2_dbc_explorer import find_effective_archive
        internal = cfg.TARGET_DBCS["ItemDisplayInfo"]
        arc = find_effective_archive(internal)
        dbc = tm_dbc.load_dbc_from_mpq(arc, internal, "ItemDisplayInfo")
        source_archive = os.path.basename(arc)
    else:
        source_archive = dbc.name
    entries = build_from_dbc(dbc)
    payload = {
        "source_dbc": "ItemDisplayInfo.dbc",
        "source_archive": source_archive,
        "signature": client_signature(),
        "total_entries": len(entries),
        "weapon_entries": sum(1 for e in entries if e.is_weapon),
        "entries": [asdict(e) for e in entries],
    }
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    return payload


# --- query layer ------------------------------------------------------------
class WeaponDB:
    def __init__(self, payload: dict):
        self.meta = {k: v for k, v in payload.items() if k != "entries"}
        self.entries = [DisplayEntry(**e) for e in payload["entries"]]
        self._by_id = {e.display_id: e for e in self.entries}

    @classmethod
    def load(cls) -> "WeaponDB":
        # Auto-rebuild if missing or built for a different/updated client.
        payload = None
        if os.path.exists(DB_PATH):
            with open(DB_PATH, "r", encoding="utf-8") as f:
                payload = json.load(f)
            if payload.get("signature") != client_signature():
                payload = None  # stale -> rebuild from the current client
        if payload is None:
            payload = build_and_save()
        db = cls(payload)
        db.apply_itemcache()
        return db

    def apply_itemcache(self):
        """
        Overlay real item names onto entries by DisplayID, from two sources:
          * the bulk world-DB dump (data/item_names.json) — ~11.5k display IDs,
          * the live client cache (WDB/itemcache.wdb) — items seen in-game,
            including custom items not in the dump.
        Fills `item_name` so search matches the actual in-game name. No-op if
        neither source is present.
        """
        by_disp: dict = {}
        slots: dict = {}
        item_ids: dict = {}
        try:
            import tm_itemdb
            by_disp.update(tm_itemdb.load_display_names())
            slots = tm_itemdb.load_display_slots()
            item_ids = tm_itemdb.load_display_items()
        except Exception:
            pass
        try:
            import tm_itemcache
            for did, names in tm_itemcache.display_to_names().items():
                merged = by_disp.setdefault(did, [])
                for nm in names:
                    if nm not in merged:
                        merged.append(nm)
        except Exception:
            pass
        self.cache_named = 0
        for e in self.entries:
            names = by_disp.get(e.display_id)
            if names:
                e.item_name = "; ".join(names)
                self.cache_named += 1
            if not e.slot and e.display_id in slots:
                e.slot = slots[e.display_id]
            if not e.item_id and e.display_id in item_ids:
                e.item_id = item_ids[e.display_id]
        self._by_slot = None  # invalidate slot index

    def get(self, display_id: int) -> Optional[DisplayEntry]:
        return self._by_id.get(display_id)

    # --- slots ---
    def slots_present(self) -> List[str]:
        """Distinct equipment-slot names that exist in the DB, in a sensible order."""
        present = {e.slot_name for e in self.entries if e.slot_name}
        order = ["Head", "Shoulder", "Chest", "Waist", "Legs", "Feet", "Wrist",
                 "Hands", "Back", "Tabard", "Shirt", "Shield", "Held (off-hand)",
                 "Relic", "One-Hand", "Main Hand", "Off Hand", "Two-Hand",
                 "Bow", "Gun/Wand", "Thrown"]
        return [s for s in order if s in present]

    def search(self, query: str, weapons_only: bool = True, limit: int = 100,
               slot: Optional[str] = None) -> List[DisplayEntry]:
        q = query.strip().lower()
        if slot:
            pool_list = [e for e in self.entries if e.slot_name == slot]
        elif weapons_only:
            pool_list = [e for e in self.entries if e.is_weapon]
        else:
            pool_list = self.entries
        if not q:
            return pool_list[:limit]
        if q.isdigit():
            e = self._by_id.get(int(q))
            if e and e in pool_list:
                return [e]
            return []
        tokens = q.split()
        out = []
        for e in pool_list:
            hay = f"{e.name} {e.model} {e.icon} {e.item_name}".lower()
            if all(t in hay for t in tokens):
                out.append(e)
                if len(out) >= limit:
                    break
        return out

    def categories(self) -> dict:
        c = {}
        for e in self.entries:
            c[e.category] = c.get(e.category, 0) + 1
        return dict(sorted(c.items(), key=lambda kv: -kv[1]))

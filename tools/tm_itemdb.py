r"""
CapyMorph — bulk item-name database from a TurtleWoW world DB dump.

The server's `item_template` table is the authoritative itemID -> name ->
display_id mapping. A public TurtleWoW world dump (e.g. tw_world.sql) contains
~20k items — far more than the local itemcache.wdb (only items the player has
seen). Verified: item 6215 'Balanced Fighting Stick' -> display_id 10654,
matching the live client cache.

This parses the dump ONCE into a compact JSON (data/item_names.json):
    { "by_display": { "<displayID>": ["Name", ...] }, "items": <count> }
which the weapon DB overlays for name search. The huge .sql is then disposable.

item_template column order (verified): entry, class, subclass, name,
description, display_id, quality, ...
"""
from __future__ import annotations

import json
import os
from typing import Iterator, Tuple

import tm_config as cfg

NAME_DB_PATH = os.path.join(cfg.DATA_DIR, "item_names.json")
_INSERT = "INSERT INTO `item_template` VALUES ("


def _parse_values(s: str, start: int):
    """
    Parse the first 6 values of a tuple beginning at s[start] == '(' :
    entry(int), class(int), subclass(int), name(str), description(str),
    display_id(int). Returns (entry, klass, subclass, name, display_id) or None.
    Handles backslash-escaped quotes inside strings.
    """
    i = start + 1
    n = len(s)

    def read_int():
        nonlocal i
        j = i
        while i < n and (s[i].isdigit() or s[i] in "+-"):
            i += 1
        val = s[j:i]
        return int(val) if val.strip("+-") else 0

    def skip_comma():
        nonlocal i
        while i < n and s[i] in ", \t":
            i += 1

    def read_str():
        nonlocal i
        # s[i] should be a quote
        if i >= n or s[i] != "'":
            return ""
        i += 1
        out = []
        while i < n:
            c = s[i]
            if c == "\\" and i + 1 < n:
                out.append(s[i + 1]); i += 2; continue
            if c == "'":
                i += 1
                break
            out.append(c); i += 1
        return "".join(out)

    try:
        entry = read_int(); skip_comma()
        klass = read_int(); skip_comma()
        subclass = read_int(); skip_comma()
        name = read_str(); skip_comma()
        _desc = read_str(); skip_comma()
        display_id = read_int(); skip_comma()
        # columns 7..11: quality, flags, buy_count, buy_price, sell_price
        for _ in range(5):
            read_int(); skip_comma()
        inventory_type = read_int()  # column 12 = equipment slot
        return entry, klass, subclass, name, display_id, inventory_type
    except Exception:
        return None


def parse_dump(sql_path: str) -> Iterator[Tuple[int, int, int, str, int, int]]:
    """Yield (entry, class, subclass, name, display_id, inventory_type) per row."""
    with open(sql_path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            idx = line.find(_INSERT)
            if idx < 0:
                continue
            paren = idx + len(_INSERT) - 1  # position of '('
            rec = _parse_values(line, paren)
            if rec:
                yield rec


def build(sql_path: str, weapons_only: bool = False) -> dict:
    """
    Parse the dump into data/item_names.json:
        { "by_display": { "<displayID>": {"names": [...], "slot": <invType>,
                                          "class": <itemClass>} }, ... }
    `slot` is the item's inventory_type (equipment slot) — used to restrict
    morphs to same-slot items. When several items share a displayID, the most
    common slot/class wins.
    """
    cfg.ensure_dirs()
    raw: dict[str, dict] = {}
    items = 0
    for entry, klass, subclass, name, display_id, inv in parse_dump(sql_path):
        if not name or not display_id:
            continue
        if weapons_only and klass != 2:
            continue
        items += 1
        key = str(display_id)
        d = raw.setdefault(key, {"names": [], "slots": {}, "classes": {}, "item_id": entry})
        if name not in d["names"]:
            d["names"].append(name)
        d["slots"][inv] = d["slots"].get(inv, 0) + 1
        d["classes"][klass] = d["classes"].get(klass, 0) + 1
        if entry < d["item_id"]:
            d["item_id"] = entry  # lowest itemID as the representative for this look

    by_display = {}
    for key, d in raw.items():
        slot = max(d["slots"].items(), key=lambda kv: kv[1])[0] if d["slots"] else 0
        klass = max(d["classes"].items(), key=lambda kv: kv[1])[0] if d["classes"] else 0
        by_display[key] = {"names": d["names"], "slot": slot, "class": klass,
                           "item_id": d["item_id"]}

    payload = {"by_display": by_display, "items": items,
               "displays": len(by_display), "source": os.path.basename(sql_path)}
    with open(NAME_DB_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    return payload


def _loaded() -> dict:
    if not os.path.exists(NAME_DB_PATH):
        return {}
    with open(NAME_DB_PATH, "r", encoding="utf-8") as f:
        return json.load(f).get("by_display", {})


def load_display_names() -> dict:
    """Return {displayID(int): [names]}. Tolerates old (list) and new (dict) JSON."""
    out = {}
    for k, v in _loaded().items():
        out[int(k)] = v["names"] if isinstance(v, dict) else v
    return out


def load_display_slots() -> dict:
    """Return {displayID(int): inventory_type}. Empty if old-format JSON."""
    out = {}
    for k, v in _loaded().items():
        if isinstance(v, dict):
            out[int(k)] = v.get("slot", 0)
    return out


def load_display_items() -> dict:
    """Return {displayID(int): representative itemID} (for per-character transmog)."""
    out = {}
    for k, v in _loaded().items():
        if isinstance(v, dict) and v.get("item_id"):
            out[int(k)] = v["item_id"]
    return out


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("usage: python tm_itemdb.py <tw_world.sql>")
        raise SystemExit(1)
    s = build(sys.argv[1])
    print(f"Parsed {s['items']} items -> {s['displays']} display IDs")
    print(f"Saved {NAME_DB_PATH}")

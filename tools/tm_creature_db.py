r"""
CapyMorph — creature display database + druid form registry (v1.5).

CreatureDisplayInfo (field map established empirically in Stage 7):
    f0  DisplayID
    f1  ModelID          -> CreatureModelData.ID  (-> .mdx path)
    f6  skin texture 1
    f7  skin texture 2
    f8  skin texture 3

A druid form's on-screen model is chosen by the client per race/form and
resolves to specific CreatureDisplayInfo rows. We morph a form by copying a
target display's ModelID + skins into the form's display row(s).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional

import tm_config as cfg
import tm_dbc

# CreatureDisplayInfo columns
CDI_ID, CDI_MODELID = 0, 1
CDI_SKINS = [6, 7, 8]
# CreatureModelData columns
CMD_ID, CMD_PATH = 0, 2

CDI_INTERNAL = r"DBFilesClient\CreatureDisplayInfo.dbc"
CMD_INTERNAL = r"DBFilesClient\CreatureModelData.dbc"

CREATURE_DB_PATH = os.path.join(cfg.DATA_DIR, "creature_display_db.json")

# Druid form -> the CreatureModelData model IDs that represent that form.
# Verified from CreatureModelData paths on this client.
FORM_MODEL_IDS = {
    "Bear Form": [213, 214],          # DruidBear / DruidBearTauren
    "Cat Form": [1231, 1232],         # DruidCat / DruidCatTauren
    "Moonkin Form": [2199, 2200, 2537],  # DruidOwlBear / Tauren / BabyMoonkin
    "Tree Form": [],                  # no druid tree-of-life model present in this client
}


@dataclass
class CreatureEntry:
    display_id: int
    model_id: int
    model_path: str
    skin1: str
    skin2: str
    skin3: str
    name: str  # derived from model path


def _variant_label(skin: str, model_path: str) -> str:
    """Human label for a form skin variant, e.g. 'DruidBearSkinEmerald' -> 'Emerald (NE)'."""
    race = "Tauren" if "tauren" in (skin + model_path).lower() else "NE"
    s = skin or ""
    low = s.lower()
    if "baby" in low:
        return f"Baby Moonkin ({race})"
    color = s
    for pre in ("DruidOwlBearNE", "DruidOwlBearTA", "DruidOwlBear",
                "DruidBearTauren", "DruidTaurenBear", "DruidBear",
                "DruidCatTauren", "DruidCat", "OwlBear", "Lynx", "Druid"):
        if color.startswith(pre):
            color = color[len(pre):]
            break
    color = color.replace("Skin", "").replace("EM", " Emerald")
    import re as _re
    color = _re.sub(r"(?<=[a-zA-Z])(?=[A-Z0-9])", " ", color).replace("_", " ").strip()
    if "Lynx" in (skin or ""):
        color = "Lynx " + color
    if not color or color.isdigit() or color in ("Tauren", "TA", "NE"):
        color = "Default"
    return f"{color} ({race})"


def _model_name(path: str) -> str:
    """'Creature\\DruidBear\\DruidBear.mdx' -> 'DruidBear'."""
    if not path:
        return ""
    base = path.replace("/", "\\").split("\\")[-1]
    return base.rsplit(".", 1)[0]


def _load(label, internal):
    from stage2_dbc_explorer import find_effective_archive
    arc = find_effective_archive(internal)
    return tm_dbc.load_dbc_from_mpq(arc, internal, label)


def client_signature() -> dict:
    """Fingerprint of the client's effective CreatureDisplayInfo (archive+size),
    so an identical client reuses the prebuilt DB and a changed one rebuilds."""
    from stage2_dbc_explorer import find_effective_archive
    try:
        arc = find_effective_archive(CDI_INTERNAL)
        return {"archive": os.path.basename(arc), "archive_size": os.path.getsize(arc)}
    except Exception:
        return {"archive": "", "archive_size": 0}


def build_and_save() -> dict:
    cfg.ensure_dirs()
    cdi = _load("CreatureDisplayInfo", CDI_INTERNAL)
    cmd = _load("CreatureModelData", CMD_INTERNAL)
    path_by_model = {cmd.field_uint(r, CMD_ID): cmd.get_string(cmd.field_uint(r, CMD_PATH))
                     for r in range(cmd.record_count)}

    entries: List[CreatureEntry] = []
    for r in range(cdi.record_count):
        did = cdi.field_uint(r, CDI_ID)
        mid = cdi.field_uint(r, CDI_MODELID)
        mpath = path_by_model.get(mid, "")
        if not mpath:
            continue  # skip displays with no resolvable model
        entries.append(CreatureEntry(
            display_id=did,
            model_id=mid,
            model_path=mpath,
            skin1=cdi.get_string(cdi.field_uint(r, CDI_SKINS[0])),
            skin2=cdi.get_string(cdi.field_uint(r, CDI_SKINS[1])),
            skin3=cdi.get_string(cdi.field_uint(r, CDI_SKINS[2])),
            name=_model_name(mpath),
        ))

    # resolve form -> player display ids (evidence-based)
    forms: Dict[str, List[int]] = {}
    for form, model_ids in FORM_MODEL_IDS.items():
        ids = [e.display_id for e in entries if e.model_id in model_ids]
        forms[form] = sorted(set(ids))

    payload = {
        "source": "CreatureDisplayInfo.dbc + CreatureModelData.dbc",
        "signature": client_signature(),
        "total_entries": len(entries),
        "forms": forms,
        "entries": [asdict(e) for e in entries],
    }
    with open(CREATURE_DB_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    return payload


class CreatureDB:
    def __init__(self, payload: dict):
        self.meta = {k: v for k, v in payload.items() if k != "entries"}
        self.forms: Dict[str, List[int]] = payload["forms"]
        self.entries = [CreatureEntry(**e) for e in payload["entries"]]
        self._by_id = {e.display_id: e for e in self.entries}

    @classmethod
    def load(cls) -> "CreatureDB":
        payload = None
        if os.path.exists(CREATURE_DB_PATH):
            with open(CREATURE_DB_PATH, "r", encoding="utf-8") as f:
                payload = json.load(f)
            if payload.get("signature") != client_signature():
                payload = None  # different/updated client -> rebuild
        if payload is None:
            payload = build_and_save()
        return cls(payload)

    def get(self, display_id: int) -> Optional[CreatureEntry]:
        return self._by_id.get(display_id)

    def form_display_ids(self, form: str) -> List[int]:
        return self.forms.get(form, [])

    def form_variants(self, form: str) -> List[dict]:
        """
        The built-in cosmetic variants for a form: every CreatureDisplayInfo
        entry whose model is one of the form's models (each a different skin —
        e.g. Bear: Default/Ice/Emerald). These are the same options the server's
        donate form-cosmetics used; here they're applied locally. Returns
        [{display_id, skin, model_id, model_path, label}], default skin first.
        """
        model_ids = set(FORM_MODEL_IDS.get(form, []))
        if not model_ids:
            return []
        out = []
        for e in self.entries:
            if e.model_id in model_ids:
                out.append({
                    "display_id": e.display_id,
                    "skin": e.skin1,
                    "model_id": e.model_id,
                    "model_path": e.model_path,
                    "label": _variant_label(e.skin1, e.model_path),
                })
        # stable order: lowest display id (the default) first
        out.sort(key=lambda v: v["display_id"])
        return out

    def available_forms(self) -> List[str]:
        return [f for f, ids in self.forms.items() if ids]

    def search(self, query: str, limit: int = 200) -> List[CreatureEntry]:
        q = query.strip().lower()
        if q.isdigit():
            e = self._by_id.get(int(q))
            return [e] if e else []
        toks = q.split()
        out = []
        seen = set()
        for e in self.entries:
            hay = f"{e.name} {e.model_path} {e.skin1}".lower()
            if all(t in hay for t in toks):
                key = (e.model_id, e.skin1)  # de-dup near-identical displays
                if key in seen:
                    continue
                seen.add(key)
                out.append(e)
                if len(out) >= limit:
                    break
        return out

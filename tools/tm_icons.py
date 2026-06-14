r"""
CapyMorph — icon preview provider.

Resolves an inventory-icon name (e.g. 'INV_Sword_08') to a decoded PNG image by
extracting `Interface\Icons\<name>.blp` from the client MPQ chain and decoding
the BLP (BLP2/DXT on this client) with Pillow.

Qt-free on purpose: returns PNG bytes; the GUI turns them into a QPixmap.
Keeps MPQ handles open and caches decoded icons for snappy previews.
"""
from __future__ import annotations

import io
import os
from functools import lru_cache
from typing import List, Optional

import pympq
from PIL import Image

import tm_config as cfg
from tm_archive import load_order_key

ICON_DIR = "Interface\\Icons"


class IconProvider:
    def __init__(self):
        data = cfg.CLIENT_DATA
        # Never open our own output patch — keeping a read handle on it would
        # block re-installing (overwriting) Data\patch-Z.mpq (WinError 32).
        # It contains no icons anyway.
        skip = cfg.OUTPUT_PATCH_NAME.lower()
        mpqs = [f for f in os.listdir(data)
                if f.lower().endswith(".mpq") and f.lower() != skip]
        # highest priority first (so the first archive that has the icon wins)
        mpqs.sort(key=load_order_key, reverse=True)
        self._handles = []
        for f in mpqs:
            try:
                h = pympq.open_archive(os.path.join(data, f), [pympq.MPQ_OPEN_READ_ONLY])
                self._handles.append((f, h))
            except Exception:
                continue

    def close(self):
        for _f, h in self._handles:
            try:
                h.close()
            except Exception:
                pass
        self._handles = []

    def _extract_blp(self, icon_name: str) -> Optional[bytes]:
        internal = f"{ICON_DIR}\\{icon_name}.blp"
        for _f, h in self._handles:
            try:
                if not h.has_file(internal):
                    continue
            except Exception:
                continue
            import tempfile
            tmp = os.path.join(tempfile.gettempdir(), "_tm_icon.blp")
            try:
                h.extract_file(internal, tmp)
                with open(tmp, "rb") as fp:
                    return fp.read()
            except Exception:
                continue
            finally:
                if os.path.exists(tmp):
                    os.remove(tmp)
        return None

    @lru_cache(maxsize=512)
    def get_png(self, icon_name: str, size: int = 64) -> Optional[bytes]:
        if not icon_name:
            return None
        blp = self._extract_blp(icon_name)
        if blp is None:
            return None
        try:
            img = Image.open(io.BytesIO(blp)).convert("RGBA")
            if size and img.size != (size, size):
                img = img.resize((size, size), Image.NEAREST)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return buf.getvalue()
        except Exception:
            return None

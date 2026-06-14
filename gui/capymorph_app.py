r"""
CapyMorph — PySide6 GUI.

ALL transmog is PER-CHARACTER (only you, locally) via the VanillaHelpers addon
CapyMorph. Three tabs:
  * Armory       — make items look different only on you.
  * Druid Forms  — change your own druid form look (others' forms unaffected).
  * My Character — turn your character into a creature.

Nothing here touches the server or other players. Changes are applied live and
can also be changed in-game with /cm.
"""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_TOOLS = os.path.join(os.path.dirname(_HERE), "tools")
if _TOOLS not in sys.path:
    sys.path.insert(0, _TOOLS)

from PySide6 import QtCore, QtGui, QtWidgets  # noqa: E402

import tm_config as cfg                 # noqa: E402
import tm_weapon_db as wdb              # noqa: E402
import tm_creature_db as cdb            # noqa: E402
import tm_icons                          # noqa: E402
import tm_char                           # noqa: E402


def _warn(parent, msg):
    QtWidgets.QMessageBox.warning(parent, "CapyMorph", msg)


def _info(parent, title, msg):
    QtWidgets.QMessageBox.information(parent, title, msg)


ADDON_HINT = ("Enable the <b>CapyMorph</b> addon at character-select (AddOns "
              "button), then /cm in game to re-apply after mount/shapeshift.")


# --------------------------------------------------------------------------- #
class SearchList(QtWidgets.QWidget):
    def __init__(self, search_fn, label_fn, preview_fn, placeholder,
                 icon_provider=None, icon_name_fn=None):
        super().__init__()
        self._search_fn = search_fn
        self._label_fn = label_fn
        self._preview_fn = preview_fn
        self._icons = icon_provider
        self._icon_name_fn = icon_name_fn
        self._current = None

        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText(placeholder)
        self.search.textChanged.connect(self._refresh)
        self.results = QtWidgets.QListWidget()
        self.results.currentItemChanged.connect(self._pick)

        self.icon_label = QtWidgets.QLabel()
        self.icon_label.setFixedSize(84, 84)
        self.icon_label.setScaledContents(True)
        self.icon_label.setAlignment(QtCore.Qt.AlignCenter)
        self.icon_label.setStyleSheet("QLabel{background:#222;border:1px solid #666;border-radius:4px;color:#999;}")
        self.preview = QtWidgets.QLabel("No selection.")
        self.preview.setWordWrap(True)
        self.preview.setStyleSheet("QLabel{background:#1e1e1e;color:#e6e6e6;padding:6px;border:1px solid #444;border-radius:4px;}")

        prow = QtWidgets.QHBoxLayout()
        prow.addWidget(self.icon_label, 0, QtCore.Qt.AlignTop)
        prow.addWidget(self.preview, 1)

        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.search)
        lay.addWidget(self.results, 1)
        lay.addLayout(prow)
        self.icon_label.setVisible(bool(icon_provider and icon_name_fn))
        self._refresh("")

    def refresh(self):
        self._refresh(self.search.text())

    def _refresh(self, text):
        self.results.clear()
        for e in self._search_fn(text):
            it = QtWidgets.QListWidgetItem(self._label_fn(e))
            it.setData(QtCore.Qt.UserRole, e)
            self.results.addItem(it)

    def _pick(self, cur, _prev):
        e = cur.data(QtCore.Qt.UserRole) if cur else None
        self._current = e
        self.preview.setText(self._preview_fn(e) if e else "No selection.")
        if self._icons and self._icon_name_fn:
            name = self._icon_name_fn(e) if e else None
            png = self._icons.get_png(name) if name else None
            if png:
                pm = QtGui.QPixmap(); pm.loadFromData(png, "PNG"); self.icon_label.setPixmap(pm)
            else:
                self.icon_label.clear(); self.icon_label.setText("no icon")

    def current(self):
        return self._current


# --------------------------------------------------------------------------- #
#  Armory — per-character item transmog
# --------------------------------------------------------------------------- #
class ArmoryTab(QtWidgets.QWidget):
    def __init__(self, weapon_db, char_cfg, icon_provider=None):
        super().__init__()
        self.db = weapon_db
        self.cfg = char_cfg

        info = QtWidgets.QLabel(
            "Make an item look different <b>only on your character</b> (others see "
            "the real item). " + ADDON_HINT)
        info.setWordWrap(True)

        self.slot = QtWidgets.QComboBox()
        for s in weapon_db.slots_present():
            self.slot.addItem(s, s)
        self.slot.currentIndexChanged.connect(lambda *_: (self.pick.refresh(), self._upd_btn()))

        self.pick = SearchList(
            lambda t: weapon_db.search(t, weapons_only=False, slot=self.slot.currentData(), limit=400),
            lambda e: f"[{e.display_id}] {(e.item_name.split(';')[0] if e.item_name else e.name)}",
            self._fmt, "search the look you want (by item name) …",
            icon_provider=icon_provider, icon_name_fn=lambda e: e.icon)

        self.apply_btn = QtWidgets.QPushButton("Show this look on me")
        self.apply_btn.setMinimumHeight(40)
        self.apply_btn.clicked.connect(self._apply)

        self.list = QtWidgets.QListWidget()
        rm = QtWidgets.QPushButton("Remove selected"); rm.clicked.connect(self._remove)
        rm_all = QtWidgets.QPushButton("Remove all"); rm_all.clicked.connect(self._remove_all)

        top = QtWidgets.QHBoxLayout()
        top.addWidget(QtWidgets.QLabel("Slot:")); top.addWidget(self.slot); top.addStretch(1); top.addWidget(self.apply_btn)
        cur = QtWidgets.QGroupBox("Active on my character (saved)")
        cl = QtWidgets.QVBoxLayout(cur); cl.addWidget(self.list, 1)
        crow = QtWidgets.QHBoxLayout(); crow.addWidget(rm); crow.addStretch(1); crow.addWidget(rm_all); cl.addLayout(crow)

        root = QtWidgets.QVBoxLayout(self)
        root.addWidget(info)
        root.addLayout(top)
        root.addWidget(self.pick, 1)
        root.addWidget(cur, 1)
        self._upd_btn()
        self._refresh_list()

    def _upd_btn(self):
        self.apply_btn.setText(f"Show this look on my {self.slot.currentData() or 'slot'}")

    @staticmethod
    def _fmt(e):
        if not e:
            return "No selection."
        item = (f"<b>Item:</b> {e.item_name.split(';')[0]}<br>" if e.item_name else "")
        return (f"{item}<b>Slot:</b> {e.slot_name or '—'}<br><b>DisplayID:</b> {e.display_id}<br>"
                + (f"<b>Model:</b> {e.model}" if e.model else "<i>body armor (texture look)</i>"))

    def _apply(self):
        if not tm_char.helper_present():
            return _warn(self, "VanillaHelpers.dll not found.")
        e = self.pick.current()
        if not e:
            return _warn(self, "Pick the look you want.")
        if not e.item_id:
            return _warn(self, "This look has no usable itemID.")
        invslot = tm_char.INVTYPE_TO_SLOT.get(e.slot)
        if not invslot:
            return _warn(self, "Not a visible equipment slot.")
        nm = e.item_name.split(";")[0] if e.item_name else e.name
        self.cfg["items"] = [it for it in self.cfg["items"] if it["slot"] != invslot]
        self.cfg["items"].append({"slot": invslot, "item_id": e.item_id, "label": f"{e.slot_name}: {nm}"})
        tm_char.apply_config(self.cfg)
        self._refresh_list()
        _info(self, "Applied", f"Your {e.slot_name} will look like '{nm}' — only on you.\n\n"
              "Enable 'CapyMorph' addon, then /cm in game.")

    def _refresh_list(self):
        self.list.clear()
        for it in self.cfg["items"]:
            row = QtWidgets.QListWidgetItem(it["label"]); row.setData(QtCore.Qt.UserRole, it["slot"]); self.list.addItem(row)
        if not self.cfg["items"]:
            self.list.addItem("(nothing yet)")

    def _remove(self):
        it = self.list.currentItem()
        slot = it.data(QtCore.Qt.UserRole) if it else None
        if slot is None:
            return
        self.cfg["items"] = [x for x in self.cfg["items"] if x["slot"] != slot]
        tm_char.apply_config(self.cfg); self._refresh_list()

    def _remove_all(self):
        self.cfg["items"] = []
        tm_char.apply_config(self.cfg); self._refresh_list()


# --------------------------------------------------------------------------- #
#  Druid Forms — per-character form override
# --------------------------------------------------------------------------- #
class DruidFormsTab(QtWidgets.QWidget):
    def __init__(self, creature_db, char_cfg):
        super().__init__()
        self.db = creature_db
        self.cfg = char_cfg
        # embed form display IDs so /cm form works in-game
        self.cfg["_form_displays"] = {f: creature_db.form_display_ids(f)
                                      for f in cdb.FORM_MODEL_IDS if creature_db.form_display_ids(f)}

        info = QtWidgets.QLabel(
            "Change how <b>your own</b> druid form looks (other druids' forms are "
            "unaffected). " + ADDON_HINT)
        info.setWordWrap(True)

        self.form = QtWidgets.QComboBox()
        for f in cdb.FORM_MODEL_IDS:
            ids = creature_db.form_display_ids(f)
            self.form.addItem(f if ids else f"{f} (unavailable)", f)
            if not ids:
                self.form.model().item(self.form.count() - 1).setEnabled(False)
        self.form.currentIndexChanged.connect(self._fill_variants)

        self.variant = QtWidgets.QComboBox()
        var_btn = QtWidgets.QPushButton("Use this skin on my form")
        var_btn.clicked.connect(self._apply_variant)
        self_btn = QtWidgets.QPushButton("Show my character (no form model)")
        self_btn.clicked.connect(self._apply_self)

        self.tgt = SearchList(
            lambda t: creature_db.search(t, limit=300),
            lambda e: f"[{e.display_id}] {e.name}",
            lambda e: (f"<b>{e.name}</b><br>DisplayID {e.display_id}<br>{e.model_path}" if e else "No selection."),
            "or search any creature for your form to become …")
        any_btn = QtWidgets.QPushButton("Use this creature on my form")
        any_btn.clicked.connect(self._apply_any)

        self.list = QtWidgets.QListWidget()
        rm = QtWidgets.QPushButton("Remove selected"); rm.clicked.connect(self._remove)

        formrow = QtWidgets.QHBoxLayout()
        formrow.addWidget(QtWidgets.QLabel("Form:")); formrow.addWidget(self.form, 1)

        cosbox = QtWidgets.QGroupBox("Ready-made skins (Ice / Emerald / Lynx …)")
        cl = QtWidgets.QVBoxLayout(cosbox)
        cl.addWidget(self.variant)
        crow = QtWidgets.QHBoxLayout(); crow.addWidget(self_btn); crow.addStretch(1); crow.addWidget(var_btn)
        cl.addLayout(crow)

        anybox = QtWidgets.QGroupBox("Or become any creature")
        av = QtWidgets.QVBoxLayout(anybox); av.addWidget(self.tgt)
        arow = QtWidgets.QHBoxLayout(); arow.addStretch(1); arow.addWidget(any_btn); av.addLayout(arow)

        cur = QtWidgets.QGroupBox("Active on my character (saved)")
        ul = QtWidgets.QVBoxLayout(cur); ul.addWidget(self.list, 1); ul.addWidget(rm)

        root = QtWidgets.QVBoxLayout(self)
        root.addWidget(info)
        root.addLayout(formrow)
        root.addWidget(cosbox)
        root.addWidget(anybox, 1)
        root.addWidget(cur, 1)
        self._fill_variants()
        self._refresh_list()

    def _fill_variants(self):
        self.variant.clear()
        for v in self.db.form_variants(self.form.currentData() or ""):
            self.variant.addItem(f"{v['label']} [{v['display_id']}]", v)

    def _set_form(self, target, label):
        if not tm_char.helper_present():
            return _warn(self, "VanillaHelpers.dll not found.")
        form = self.form.currentData()
        displays = self.db.form_display_ids(form)
        if not displays:
            return _warn(self, f"{form} unavailable on this client.")
        self.cfg["forms"] = [x for x in self.cfg["forms"] if x["form"] != form]
        self.cfg["unform"] = [x for x in self.cfg["unform"] if x["form"] != form]
        if target == "self":
            self.cfg["unform"].append({"form": form, "displays": displays, "label": f"{form}: my character"})
        else:
            self.cfg["forms"].append({"form": form, "displays": displays, "target": target, "label": f"{form}: {label}"})
        tm_char.apply_config(self.cfg)
        self._refresh_list()
        _info(self, "Applied", f"Your {form} will look like '{label}' — only on you.\n\n"
              "Enable 'CapyMorph' addon, then shapeshift (or /cm).")

    def _apply_variant(self):
        v = self.variant.currentData()
        if not v:
            return _warn(self, "No skin for this form.")
        self._set_form(v["display_id"], v["label"])

    def _apply_any(self):
        t = self.tgt.current()
        if not t:
            return _warn(self, "Pick a creature.")
        self._set_form(t.display_id, t.name)

    def _apply_self(self):
        self._set_form("self", "my character (experimental)")

    def _refresh_list(self):
        self.list.clear()
        for x in self.cfg["forms"]:
            r = QtWidgets.QListWidgetItem(x["label"]); r.setData(QtCore.Qt.UserRole, x["form"]); self.list.addItem(r)
        for x in self.cfg["unform"]:
            r = QtWidgets.QListWidgetItem(x["label"] + " (no form)"); r.setData(QtCore.Qt.UserRole, x["form"]); self.list.addItem(r)
        if not self.cfg["forms"] and not self.cfg["unform"]:
            self.list.addItem("(nothing yet)")

    def _remove(self):
        it = self.list.currentItem()
        form = it.data(QtCore.Qt.UserRole) if it else None
        if not form:
            return
        self.cfg["forms"] = [x for x in self.cfg["forms"] if x["form"] != form]
        self.cfg["unform"] = [x for x in self.cfg["unform"] if x["form"] != form]
        tm_char.apply_config(self.cfg); self._refresh_list()


# --------------------------------------------------------------------------- #
#  My Character — whole-body
# --------------------------------------------------------------------------- #
class MyCharacterTab(QtWidgets.QWidget):
    def __init__(self, creature_db, char_cfg):
        super().__init__()
        self.db = creature_db
        self.cfg = char_cfg

        info = QtWidgets.QLabel(
            "Turn <b>your own character</b> into a creature, locally. E.g. "
            "<i>skeleton naked</i>. " + ADDON_HINT)
        info.setWordWrap(True)

        self.pick = SearchList(
            lambda t: creature_db.search(t, limit=400),
            lambda e: f"[{e.display_id}] {e.name}",
            lambda e: (f"<b>{e.name}</b><br>DisplayID {e.display_id}<br>{e.model_path}" if e else "No selection."),
            "search a look: skeleton naked, murloc, gnoll …")

        apply_btn = QtWidgets.QPushButton("Become this"); apply_btn.setMinimumHeight(40)
        apply_btn.clicked.connect(self._apply)
        reset_btn = QtWidgets.QPushButton("Back to normal"); reset_btn.clicked.connect(self._reset)
        self.status = QtWidgets.QLabel()

        row = QtWidgets.QHBoxLayout()
        row.addWidget(self.status, 1); row.addWidget(reset_btn); row.addWidget(apply_btn)

        root = QtWidgets.QVBoxLayout(self)
        root.addWidget(info); root.addWidget(self.pick, 1); root.addLayout(row)
        self._refresh()

    def _refresh(self):
        m = self.cfg.get("model")
        self.status.setText(f"Currently: display {m}" if m else "Currently: normal")

    def _apply(self):
        if not tm_char.helper_present():
            return _warn(self, "VanillaHelpers.dll not found.")
        e = self.pick.current()
        if not e:
            return _warn(self, "Pick a look.")
        self.cfg["model"] = e.display_id
        self.cfg["_model_label"] = e.name
        tm_char.apply_config(self.cfg); self._refresh()
        _info(self, "Applied", f"Your character will look like '{e.name}'.\n\n"
              "Enable 'CapyMorph' addon, then /cm in game.")

    def _reset(self):
        self.cfg["model"] = None
        self.cfg.pop("_model_label", None)
        tm_char.apply_config(self.cfg); self._refresh()


# --------------------------------------------------------------------------- #
class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, weapon_db, creature_db):
        super().__init__()
        self.setWindowTitle("CapyMorph")
        self.resize(960, 820)
        try:
            self.icons = tm_icons.IconProvider()
        except Exception:
            self.icons = None

        self.charcfg = tm_char.load_config()  # one shared per-character config
        # build/refresh the in-game addon (data + UI) so the /cm window works
        if tm_char.helper_present():
            try:
                self._build_addon(weapon_db, creature_db)
            except Exception:
                pass
        tabs = QtWidgets.QTabWidget()
        tabs.addTab(ArmoryTab(weapon_db, self.charcfg, self.icons), "⚔  Armory")
        tabs.addTab(DruidFormsTab(creature_db, self.charcfg), "🐾  Druid Forms")
        tabs.addTab(MyCharacterTab(creature_db, self.charcfg), "💀  My Character")
        self.setCentralWidget(tabs)

        warn = "" if tm_char.helper_present() else "  ⚠ VanillaHelpers.dll NOT found!"
        self.statusBar().showMessage(
            "Per-character (only you). In game: /cm opens the transmog window. "
            "Enable the 'CapyMorph' addon at character-select." + warn)

    def _build_addon(self, weapon_db, creature_db, force_data=False):
        """Install/refresh the addon. The big search-data file is only (re)built
        when missing (or forced); the small UI/logic is always refreshed."""
        # form display IDs must be embedded so /cm form + the Druid UI work
        self.charcfg["_form_displays"] = {
            f: creature_db.form_display_ids(f)
            for f in cdb.FORM_MODEL_IDS if creature_db.form_display_ids(f)}
        data_path = os.path.join(tm_char.ADDON_DIR, tm_char.ADDON_NAME + "Data.lua")
        if force_data or not os.path.exists(data_path) or os.path.getsize(data_path) < 2000:
            items_by_slot = {}
            for e in weapon_db.entries:
                if not e.item_id or not e.slot:
                    continue
                nm = (e.item_name.split(";")[0] if e.item_name else e.name) or e.name
                if not nm:
                    continue
                for inv in tm_char.slots_for(e.slot):   # 1H weapons -> both hands
                    items_by_slot.setdefault(inv, []).append((nm, e.item_id))
            for inv in items_by_slot:
                seen, out = set(), []
                for nm, iid in sorted(items_by_slot[inv]):
                    if iid not in seen:
                        seen.add(iid); out.append((nm, iid))
                items_by_slot[inv] = out[:2000]
            creatures = [(e.name, e.display_id, e.model_path)
                         for e in creature_db.entries if e.model_path][:14000]
            tm_char.write_data(items_by_slot, creatures)
        tm_char.write_addon(self.charcfg)  # always refresh UI/logic (small, fast)


APP_STYLE = """
* { font-size: 13px; }
QTabBar::tab { min-width: 150px; min-height: 32px; padding: 8px 18px; font-size: 14px; font-weight: bold; }
QGroupBox { font-weight: bold; margin-top: 12px; border: 1px solid #5a5a5a; border-radius: 6px; padding-top: 16px; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; }
QPushButton { min-height: 30px; padding: 6px 16px; border-radius: 4px; }
QComboBox, QLineEdit { min-height: 28px; padding: 4px 6px; }
"""


def main():
    cfg.ensure_dirs()
    app = QtWidgets.QApplication(sys.argv)
    app.setStyleSheet(APP_STYLE)
    try:
        weapon_db = wdb.WeaponDB.load()
        creature_db = cdb.CreatureDB.load()
    except Exception as e:  # noqa: BLE001
        QtWidgets.QMessageBox.critical(None, "CapyMorph", f"Failed to load databases:\n{e}")
        return 1
    MainWindow(weapon_db, creature_db).show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

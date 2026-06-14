# CapyMorph

Per-character, **client-side** appearance changer for **TurtleWoW 1.18.x** (1.12-based).
It changes how **your own** character looks — locally. Other players see you and
your real items normally; the server is never touched.

Everything is done in-game in the `/cm` window: transmog any equipment slot,
hide slots, turn your whole body into a creature, reskin your druid forms, and
save/load presets.

> The repo folder is the **dev toolkit** (`CapyMorph/`) that *generates* the
> addon. End users only need the addon in [`addon/CapyMorph/`](addon/CapyMorph)
> plus VanillaHelpers — see below. **No build, no database steps for users.**

---

## For users — install (TurtleWoW 1.18.x)

You need three things; all are in this repo.

1. **The addon.** Copy [`addon/CapyMorph/`](addon/CapyMorph) into your client's
   `Interface\AddOns\` so you have `Interface\AddOns\CapyMorph\CapyMorph.toc`.
2. **VanillaHelpers.dll** (the per-character morph API). Copy
   [`deps/VanillaHelpers.dll`](deps) next to `WoW.exe` (the Game folder).
   *TurtleWoW usually already ships it — you can keep yours.*
3. **Enable the DLL.** Add the line `VanillaHelpers.dll` to `dlls.txt` (next to
   `WoW.exe`); see [`deps/dlls.txt.example`](deps/dlls.txt.example). Delete
   `dlls.txt.cache` if present. The loader (VanillaFixes / your launcher) injects it.

Then: at character-select press **AddOns** and enable **CapyMorph**, log in, type **`/cm`**.

That's it. **The addon is fully self-contained** — its search database
(`CapyMorphData.lua`) is baked in, so users do **not** run any tool, dump, or
database/model step. The morph itself uses item/display IDs that the client
resolves locally from its own files.

### Using it
| Tab | What |
|---|---|
| **Armory** | make any slot look like another item, or **Hide** the slot (eye button) |
| **My Character** | turn your whole body into a creature |
| **Druid Forms** | reskin cat / bear / moonkin (model, or "show my character") |
| **Presets** | save / load / delete full looks |

Slash: `/cm` (window), `/cm diag` (check the API), `/cm clear` (remove all),
`/cm off` / `on`. Config is **per-character** (saved separately for each toon).

### Requirements / notes
- TurtleWoW 1.18.x client with **VanillaHelpers** loaded (`/cm diag` verifies it).
- The bundled database matches **this** 1.18.x content. On an identical client it
  is correct as-is; a substantially different client may need a rebuild (dev tool).
- Removing the addon or `/cm clear` fully reverts; original client files are never changed.

---

## For developers — the toolkit

The desktop tool (PySide6) reads the client's DBC/MPQ + item data and **generates**
the addon: the logic/UI (from the Lua templates in `tools/`) and the search
database `CapyMorphData.lua`. Users never need this; it's only for (re)building
the addon for a different client/content set.

```
addon/      the built, self-contained CapyMorph addon (what users install)
deps/       VanillaHelpers.dll + dlls.txt.example (runtime dependency)
tools/      generator: tm_*.py (DBC/MPQ readers) + Lua templates (_addon_main.lua, _addon_ui.lua)
gui/        desktop GUI (capymorph_app.py) that runs the generator
data/       item_names.json — item-name source for regeneration (other DBs rebuild from the client)
```

Run from source:
```
pip install -r requirements.txt
python gui/capymorph_app.py
```

Rebuild the addon database for a different client: run the desktop app once; it
detects the client, extracts content, regenerates `CapyMorphData.lua` + the addon.

---

## How it works (short)
- Per-slot item look: `SetUnitVisibleItemID("player", slot, itemID)` (or `0` to hide).
- Whole-body / form model: `SetUnitDisplayID("player", displayID)`.
- Druid form is detected via the shapeshift bar's `isActive` flag (with a power-type
  fast path), so morphs don't fight the game's form state.
- All overrides are re-asserted on a light timer and reset cleanly on zone/clear.

License: personal/community use. VanillaHelpers is a third-party TurtleWoW extension,
included here only for convenience.

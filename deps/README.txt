CapyMorph — dependencies
=========================

CapyMorph is a per-character, client-side appearance addon for TurtleWoW 1.12.
It changes ONLY your own character, locally (no server effect, other players
see you normally). It needs the TurtleWoW client extension VanillaHelpers, which
exposes the per-unit Lua API the addon drives:

  SetUnitDisplayID("player" [, displayID])        whole-body / form model
  SetUnitVisibleItemID("player", slot [, itemID])  per-slot item appearance
  UnitDisplayInfo("player")                         read current display

Files here
----------
  VanillaHelpers.dll   -> copy into your Game folder (next to WoW.exe)
  dlls.txt.example     -> reference for the DLL injection list

Install
-------
1. Copy VanillaHelpers.dll into the Game folder (next to WoW.exe).
2. Add the line `VanillaHelpers.dll` to dlls.txt (next to WoW.exe). Delete
   dlls.txt.cache if it exists. The DLL is injected by your loader (VanillaFixes
   or the launcher that reads dlls.txt).
3. Copy the CapyMorph addon folder into Interface\AddOns\.
4. Enable "CapyMorph" at character select, log in, type /cm.

If VanillaHelpers is missing, /cm diag prints "VanillaHelpers functions NOT found".

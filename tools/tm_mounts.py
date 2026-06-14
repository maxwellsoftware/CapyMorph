r"""
CapyMorph — mount data: mount spell name -> mount creature display id.

Read from Spell.dbc. On the 1.12 layout (verified against this client):
  * field 120        = spell name
  * fields 91/92/93  = EffectApplyAuraName[1..3]; SPELL_AURA_MOUNTED == 78
  * fields 106/108   = EffectMiscValue[1..3]; the misc value of the mounted
                       aura is the mount's CreatureDisplayInfo id.

TurtleWoW stores mounts as spells in the "Companions" spellbook tab; the addon
scans that tab and looks each spell name up here to get the display to remap.
"""
from __future__ import annotations

import tm_archive
import tm_dbc

AURA_MOUNTED = 78
NAME_FIELD = 120
AURA_FIELDS = (91, 92, 93)
MISC_FIELDS = (106, 107, 108)
_SKIP = ("(OLD)", "(TEST)", "(PH)", "[PH]", "(Unused)", "Test ")


def build_mounts(spell_dbc: "tm_dbc.DBC | None" = None) -> dict:
    """Return {mount spell name: mount displayID} for every mounted-aura spell."""
    dbc = spell_dbc or tm_dbc.load_dbc_from_mpq(
        tm_archive.find_effective_archive(r"DBFilesClient\Spell.dbc"),
        r"DBFilesClient\Spell.dbc", "Spell")
    out = {}
    for r in range(dbc.record_count):
        for ai, af in enumerate(AURA_FIELDS):
            if dbc.field_uint(r, af) == AURA_MOUNTED:
                disp = dbc.field_uint(r, MISC_FIELDS[ai])
                name = dbc.get_string(dbc.field_uint(r, NAME_FIELD))
                if name and disp and disp > 1 and not any(s in name for s in _SKIP):
                    out.setdefault(name, disp)   # first (lowest spell id) wins
                break
    return out

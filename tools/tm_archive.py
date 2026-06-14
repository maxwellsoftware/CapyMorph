r"""
CapyMorph — client MPQ archive resolution.

Locates the effective (highest-priority) version of a file across the client's
MPQ chain, honouring WoW 1.12 load order. Used by the DBC and icon readers so
they always read the stock client data (not a previously generated patch).
"""
from __future__ import annotations

import os

import tm_config as cfg
import tm_mpq

# DBCs the generator depends on. {label: internal MPQ path}
CRITICAL_DBCS = {
    "ItemDisplayInfo": r"DBFilesClient\ItemDisplayInfo.dbc",
    "CreatureDisplayInfo": r"DBFilesClient\CreatureDisplayInfo.dbc",
    "CreatureModelData": r"DBFilesClient\CreatureModelData.dbc",
    "SpellShapeshiftForm": r"DBFilesClient\SpellShapeshiftForm.dbc",
}


def load_order_key(filename: str):
    """Sort key approximating WoW 1.12 MPQ load order (lowest priority first).

    Base archives first, then patch.MPQ, then patch-<X> (numeric suffixes before
    alphabetic ones, ascending). Higher key == loaded later == wins on conflict.
    """
    name = filename.lower()
    base, _ = os.path.splitext(name)          # e.g. 'patch-3', 'patch', 'dbc'
    if not base.startswith("patch"):
        return (0, 0, name)                   # base archive: loaded before any patch
    if base == "patch":
        return (1, 0, "")                     # plain patch.MPQ before suffixed patches
    suffix = base.split("-", 1)[1] if "-" in base else ""
    if suffix.isdigit():
        return (2, int(suffix), "")           # numeric patches before alphabetic, ascending
    return (3, 0, suffix)                      # alphabetic suffix, ascending


def find_effective_archive(internal_name: str, exclude_output: bool = True) -> str:
    """Path to the highest-priority MPQ containing ``internal_name``.

    Our own output patch is skipped by default, so reads are based on the stock
    client data (morphs/DB built from the original DBC, not stacked on a prior
    generated patch).
    """
    data_dir = cfg.CLIENT_DATA
    skip = cfg.OUTPUT_PATCH_NAME.lower() if (exclude_output and getattr(cfg, "OUTPUT_PATCH_NAME", None)) else None
    mpqs = [f for f in os.listdir(data_dir)
            if f.lower().endswith(".mpq") and f.lower() != skip]
    mpqs.sort(key=load_order_key)             # lowest priority first
    effective = None
    for f in mpqs:
        full = os.path.join(data_dir, f)
        try:
            if tm_mpq.has_file(full, internal_name):
                effective = full              # later in order == higher priority
        except Exception:
            continue
    if not effective:
        raise FileNotFoundError(f"{internal_name} not found in any MPQ")
    return effective

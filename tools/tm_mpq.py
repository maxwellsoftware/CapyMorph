"""
CapyMorph — MPQ access layer.

Thin wrapper around `pympq` (a StormLib binding). Read-only helpers used by
Stages 1-4; write helpers (patch creation) live in the Stage 5 generator.

We deliberately use StormLib (via pympq) rather than re-implementing the MPQ
format, per project constraints.
"""
from __future__ import annotations

import os
from typing import Iterable, Optional

import pympq

READ_ONLY = [pympq.MPQ_OPEN_READ_ONLY]


def open_ro(mpq_path: str):
    """Open an MPQ archive read-only. Returns a pympq.Mpq handle."""
    return pympq.open_archive(mpq_path, READ_ONLY)


def has_file(mpq_path: str, internal_name: str) -> bool:
    """True if `internal_name` exists inside the given MPQ."""
    m = open_ro(mpq_path)
    try:
        return bool(m.has_file(internal_name))
    finally:
        m.close()


def extract_to(mpq_path: str, internal_name: str, dest_path: str) -> str:
    """Extract a single file from an MPQ to dest_path on disk. Returns dest_path."""
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    m = open_ro(mpq_path)
    try:
        m.extract_file(internal_name, dest_path)
    finally:
        m.close()
    return dest_path


def read_bytes(mpq_path: str, internal_name: str) -> bytes:
    """Read a file from an MPQ fully into memory via a temp extraction."""
    import tempfile

    tmp = os.path.join(tempfile.gettempdir(), "_tm_" + os.path.basename(internal_name))
    try:
        extract_to(mpq_path, internal_name, tmp)
        with open(tmp, "rb") as f:
            return f.read()
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def find_first(mpq_paths: Iterable[str], internal_name: str) -> Optional[str]:
    """
    Return the path of the FIRST MPQ (in the given order) that contains
    `internal_name`. Pass MPQs in *load order* (lowest priority first) and the
    last hit wins; or pass them reversed to find the highest-priority source.
    """
    found = None
    for p in mpq_paths:
        try:
            if has_file(p, internal_name):
                found = p
        except pympq.MpqException:
            continue
    return found

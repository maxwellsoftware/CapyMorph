r"""
CapyMorph — WDBC (.dbc) reader/writer library.

WDBC is the WoW 1.x client DB format. Layout (all little-endian):

    char[4] magic      = 'WDBC'
    uint32  record_count
    uint32  field_count
    uint32  record_size      (== field_count * 4 for vanilla; all fields 4 bytes)
    uint32  string_block_size
    <record_count * record_size bytes>   records
    <string_block_size bytes>            string block (NUL-terminated, offset 0 = "")

We do NOT assume what each field *means* — every field is read as a raw 4-byte
value. Callers may interpret a field as int32, uint32, float, or a string
offset into the string block. Column semantics are determined empirically
(see detect_string_columns) and confirmed against real client data, never
invented.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import List, Optional

MAGIC = b"WDBC"
HEADER_SIZE = 20


@dataclass
class DBCHeader:
    record_count: int
    field_count: int
    record_size: int
    string_block_size: int

    @property
    def fields_are_4byte(self) -> bool:
        return self.record_size == self.field_count * 4


class DBC:
    """A parsed WDBC file held in memory."""

    def __init__(self, raw: bytes, name: str = "<dbc>"):
        if len(raw) < HEADER_SIZE or raw[:4] != MAGIC:
            raise ValueError(f"{name}: not a WDBC file (magic={raw[:4]!r})")
        rc, fc, rs, ss = struct.unpack_from("<4I", raw, 4)
        self.name = name
        self.header = DBCHeader(rc, fc, rs, ss)
        self._raw = raw

        rec_start = HEADER_SIZE
        rec_bytes = rc * rs
        self._rec_start = rec_start
        self._rec_bytes = rec_bytes
        self._str_start = rec_start + rec_bytes

        expected = self._str_start + ss
        if len(raw) < self._str_start:
            raise ValueError(
                f"{name}: truncated — need {self._str_start} bytes for records, have {len(raw)}"
            )
        # string block may be padded; tolerate >= expected
        self._string_block = raw[self._str_start:self._str_start + ss]

    # --- basic info ---------------------------------------------------------
    @property
    def record_count(self) -> int:
        return self.header.record_count

    @property
    def field_count(self) -> int:
        return self.header.field_count

    @property
    def record_size(self) -> int:
        return self.header.record_size

    @property
    def string_block_size(self) -> int:
        return self.header.string_block_size

    # --- record access ------------------------------------------------------
    def record_offset(self, row: int) -> int:
        return self._rec_start + row * self.header.record_size

    def row_ints(self, row: int) -> List[int]:
        """All fields of a row as unsigned 32-bit ints (raw view)."""
        off = self.record_offset(row)
        return list(struct.unpack_from(f"<{self.header.field_count}I", self._raw, off))

    def field_uint(self, row: int, field: int) -> int:
        off = self.record_offset(row) + field * 4
        return struct.unpack_from("<I", self._raw, off)[0]

    def field_int(self, row: int, field: int) -> int:
        off = self.record_offset(row) + field * 4
        return struct.unpack_from("<i", self._raw, off)[0]

    def field_float(self, row: int, field: int) -> float:
        off = self.record_offset(row) + field * 4
        return struct.unpack_from("<f", self._raw, off)[0]

    def iter_rows_ints(self):
        for r in range(self.header.record_count):
            yield self.row_ints(r)

    # --- string block -------------------------------------------------------
    def get_string(self, offset: int) -> str:
        """Read a NUL-terminated string from the string block at `offset`."""
        if offset <= 0 or offset >= len(self._string_block):
            return ""
        end = self._string_block.find(b"\x00", offset)
        if end < 0:
            end = len(self._string_block)
        return self._string_block[offset:end].decode("latin-1", errors="replace")

    def is_valid_string_offset(self, offset: int, require_start: bool = True) -> bool:
        """
        True if `offset` plausibly points to a non-empty printable string.

        With require_start=True (default) the offset must point to the START of a
        string — the preceding byte must be NUL. This rejects integer fields
        whose values coincidentally land in the middle of the string block.
        """
        if offset <= 0 or offset >= len(self._string_block):
            return False
        if require_start and self._string_block[offset - 1] != 0:
            return False
        s = self.get_string(offset)
        if not s:
            return False
        # printable-ish: allow common path chars
        return all(32 <= ord(c) < 127 for c in s)

    # --- empirical schema discovery ----------------------------------------
    def detect_string_columns(self, sample: int = 0):
        """
        Decide, from the data itself, which fields are string-offset columns.

        For each field we measure the fraction of NON-ZERO values that are valid
        string offsets. A field where (almost) every non-zero value resolves to
        a printable string is a string column. Returns dict:
            { field_index: {"nonzero": n, "stringish": k, "ratio": k/n, "samples": [...]} }
        for fields classified as strings (ratio >= 0.9).
        """
        fc = self.header.field_count
        rc = self.header.record_count if sample <= 0 else min(sample, self.header.record_count)
        stats = {f: {"nonzero": 0, "stringish": 0, "samples": []} for f in range(fc)}
        for r in range(rc):
            ints = self.row_ints(r)
            for f, v in enumerate(ints):
                if v == 0:
                    continue
                stats[f]["nonzero"] += 1
                if self.is_valid_string_offset(v):
                    stats[f]["stringish"] += 1
                    if len(stats[f]["samples"]) < 5:
                        s = self.get_string(v)
                        if s and s not in stats[f]["samples"]:
                            stats[f]["samples"].append(s)
        result = {}
        for f, st in stats.items():
            nz = st["nonzero"]
            ratio = (st["stringish"] / nz) if nz else 0.0
            st["ratio"] = ratio
            if nz >= 1 and ratio >= 0.9:
                result[f] = st
        return result


class DBCEditor:
    """
    In-memory editor for a WDBC file. Edits operate on a mutable copy of the
    raw bytes; the string block is never touched when only string-offset values
    are copied between rows (both rows share the same block).
    """

    def __init__(self, dbc: DBC):
        self.dbc = dbc
        self.buf = bytearray(dbc._raw)
        self._row_index = {}  # id-field(f0) -> row, lazily built

    def _build_index(self):
        if self._row_index:
            return
        for r in range(self.dbc.record_count):
            self._row_index[self.dbc.field_uint(r, 0)] = r

    def row_of_id(self, display_id: int) -> int:
        self._build_index()
        if display_id not in self._row_index:
            raise KeyError(f"DisplayID {display_id} not found in {self.dbc.name}")
        return self._row_index[display_id]

    def get_field_uint(self, row: int, field: int) -> int:
        off = self.dbc.record_offset(row) + field * 4
        return struct.unpack_from("<I", self.buf, off)[0]

    def set_field_uint(self, row: int, field: int, value: int):
        off = self.dbc.record_offset(row) + field * 4
        struct.pack_into("<I", self.buf, off, value & 0xFFFFFFFF)

    def copy_fields_by_id(self, src_id: int, dst_id: int, fields):
        """
        Copy raw 4-byte field values from the src_id row into the dst_id row for
        the given field indices. For string-offset fields this re-points dst at
        src's existing strings without altering the string block.
        Returns a list of (field, old_value, new_value).
        """
        src_row = self.row_of_id(src_id)
        dst_row = self.row_of_id(dst_id)
        changes = []
        for f in fields:
            old = self.get_field_uint(dst_row, f)
            new = self.get_field_uint(src_row, f)
            self.set_field_uint(dst_row, f, new)
            changes.append((f, old, new))
        return changes

    def to_bytes(self) -> bytes:
        return bytes(self.buf)

    def save(self, path: str):
        import os
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(self.buf)
        return path


def load_dbc_from_mpq(mpq_path: str, internal_name: str, name: Optional[str] = None) -> DBC:
    """Convenience: extract a DBC from an MPQ and parse it."""
    import tm_mpq

    raw = tm_mpq.read_bytes(mpq_path, internal_name)
    return DBC(raw, name or internal_name)


def load_dbc_file(path: str) -> DBC:
    with open(path, "rb") as f:
        return DBC(f.read(), path)

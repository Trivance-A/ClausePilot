"""HWP 5.x binary parser: olefile -> BodyText/Section* -> zlib raw-deflate -> records (HWPTAG_PARA_TEXT, HWPTAG_TABLE).

Record header (UINT32): tag_id = bits 0-9, level = bits 10-19, size = bits 20-31 (0xFFF -> next UINT32 is the size).
Only text and table cells are recovered; drawing objects / equations are skipped (05_OCR_Pipeline §3-①).
"""

import struct
import zlib

HWPTAG_PARA_HEADER = 0x42
HWPTAG_PARA_TEXT = 0x43
HWPTAG_CTRL_HEADER = 0x47
HWPTAG_LIST_HEADER = 0x48
HWPTAG_TABLE = 0x4D

# PARA_TEXT control chars that occupy one WCHAR; every other code < 32 is an inline/extended control of 8 WCHARs.
_CHAR_CONTROLS = {0, 10, 13, 24, 25, 26, 27, 28, 29, 30, 31}


def iter_records(data: bytes):
    pos = 0
    while pos + 4 <= len(data):
        (header,) = struct.unpack_from("<I", data, pos)
        pos += 4
        tag, level, size = header & 0x3FF, (header >> 10) & 0x3FF, header >> 20
        if size == 0xFFF:
            (size,) = struct.unpack_from("<I", data, pos)
            pos += 4
        yield tag, level, data[pos : pos + size]
        pos += size


def para_text(payload: bytes) -> str:
    out, i, n = [], 0, len(payload) // 2
    while i < n:
        (code,) = struct.unpack_from("<H", payload, i * 2)
        if code >= 32:
            out.append(chr(code))
            i += 1
        elif code in _CHAR_CONTROLS:
            if code in (10, 13):
                out.append("\n")
            elif code in (30, 31):
                out.append(" ")
            i += 1
        else:
            if code == 9:
                out.append("\t")
            i += 8
    return "".join(out).replace("\r", "")


def parse_section(data: bytes) -> list[dict]:
    """Section stream -> blocks. Paragraphs nested under a table control go into that table's current cell."""
    blocks: list[dict] = []
    table = None  # {"level": ctrl level, "cells": [...], "cur": cell}
    pending_tbl_level = None
    for tag, level, payload in iter_records(data):
        if table is not None and tag == HWPTAG_PARA_HEADER and level <= table["level"]:
            blocks.append({"type": "table", "cells": table["cells"]})
            table = None
        if tag == HWPTAG_CTRL_HEADER and payload[:4] == b" lbt" and table is None:  # ctrl id 'tbl ' stored little-endian
            pending_tbl_level = level
        elif tag == HWPTAG_TABLE and pending_tbl_level is not None:
            table, pending_tbl_level = {"level": pending_tbl_level, "cells": [], "cur": None}, None
        elif tag == HWPTAG_LIST_HEADER and table is not None and level == table["level"] + 1 and len(payload) >= 12:
            col, row = struct.unpack_from("<HH", payload, 8)  # cell addr follows paragraph count + list flags
            table["cur"] = [row + 1, col + 1, ""]
            table["cells"].append(table["cur"])
        elif tag == HWPTAG_PARA_TEXT:
            text = para_text(payload).strip("\n")
            if table is not None and table["cur"] is not None:
                table["cur"][2] = (table["cur"][2] + " " + text).strip()
            elif text.strip():
                blocks.append({"type": "p", "text": text})
    if table is not None:
        blocks.append({"type": "table", "cells": table["cells"]})
    return blocks


def parse_hwp(path: str) -> list[dict]:
    import olefile

    with open(path, "rb") as f:
        if f.read(32).startswith(b"HWP Document File V3"):
            raise ValueError("HWP 3.0(구형) 문서는 내장 파서 미지원 — LibreOffice hwp 필터로 변환")
    with olefile.OleFileIO(path) as ole:
        header = ole.openstream("FileHeader").read()
        if not header.startswith(b"HWP Document File"):
            raise ValueError("HWP 5.x 문서가 아닙니다")
        (flags,) = struct.unpack_from("<I", header, 36)
        compressed, encrypted, distributed = bool(flags & 1), bool(flags & 2), bool(flags & 4)
        if encrypted or distributed:
            raise ValueError("암호화/배포용 HWP는 파싱할 수 없습니다")
        sections = sorted(
            (e for e in ole.listdir() if len(e) == 2 and e[0] == "BodyText" and e[1].startswith("Section")),
            key=lambda e: int(e[1][len("Section") :]),
        )
        blocks: list[dict] = []
        for entry in sections:
            data = ole.openstream(entry).read()
            if compressed:
                data = zlib.decompress(data, -15)
            blocks.extend(parse_section(data))
    return blocks

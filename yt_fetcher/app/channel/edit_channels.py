"""
Batch / single edits for channel.category_id / status / priority.

File formats
------------
JSONL (preferred — one pasteable line from UI):
  {"channel_id":"UCxxx","category_id":null,"status":0,"priority":null}

JSON array:
  [{"channel_id":"UCxxx","status":0}, {"id":"@handle","category_id":19}]

CSV (header required):
  channel_id,category_id,status,priority
  UCxxx,,0,
  @somehandle,19,,

Identity: channel_id | id | handle | custom_url (UC… or @handle).
null / empty cell = leave field unchanged. At least one field must be set.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.channel.dao import ChannelDAO
from app.logger import logger

EDITABLE = ("category_id", "status", "priority")


@dataclass
class ChannelEdit:
    ref: str  # as given (UC… / @handle / custom_url)
    category_id: int | None = None
    status: int | None = None
    priority: int | None = None
    line: int | None = None

    def fields(self) -> dict[str, int]:
        out: dict[str, int] = {}
        if self.category_id is not None:
            out["category_id"] = self.category_id
        if self.status is not None:
            out["status"] = self.status
        if self.priority is not None:
            out["priority"] = self.priority
        return out


def _parse_int(val: Any, *, field: str, line: int | None) -> int | None:
    if val is None:
        return None
    if isinstance(val, str):
        val = val.strip()
        if val == "" or val.lower() in {"null", "none", "-"}:
            return None
    if val is None:
        return None
    try:
        return int(val)
    except (TypeError, ValueError) as e:
        where = f" line={line}" if line is not None else ""
        raise SystemExit(f"edit-channels: invalid {field}={val!r}{where}") from e


def _identity_from_obj(obj: dict, *, line: int | None) -> str:
    for key in ("channel_id", "id", "handle", "custom_url"):
        raw = obj.get(key)
        if raw is None:
            continue
        s = str(raw).strip()
        if s:
            return s
    where = f" line={line}" if line is not None else ""
    raise SystemExit(f"edit-channels: missing channel_id/id/handle{where}")


def edit_from_mapping(obj: dict, *, line: int | None = None) -> ChannelEdit:
    if not isinstance(obj, dict):
        raise SystemExit(f"edit-channels: expected object, got {type(obj).__name__}")
    edit = ChannelEdit(
        ref=_identity_from_obj(obj, line=line),
        category_id=_parse_int(obj.get("category_id"), field="category_id", line=line),
        status=_parse_int(obj.get("status"), field="status", line=line),
        priority=_parse_int(obj.get("priority"), field="priority", line=line),
        line=line,
    )
    if not edit.fields():
        where = f" line={line}" if line is not None else ""
        raise SystemExit(
            f"edit-channels: no changes for {edit.ref!r}{where} "
            "(set category_id and/or status and/or priority)"
        )
    return edit


def parse_edits_file(path: Path) -> list[ChannelEdit]:
    text = path.read_text(encoding="utf-8-sig").strip()
    if not text:
        raise SystemExit(f"edit-channels: empty file {path}")

    suffix = path.suffix.lower()
    if suffix == ".csv":
        return _parse_csv(text)
    if suffix in {".json", ".jsonl"}:
        return _parse_jsonish(text)
    # sniff
    if text.lstrip().startswith("[") or text.lstrip().startswith("{"):
        return _parse_jsonish(text)
    if "channel_id" in text.splitlines()[0] or "handle" in text.splitlines()[0]:
        return _parse_csv(text)
    raise SystemExit(
        f"edit-channels: unknown format for {path} (use .csv / .json / .jsonl)"
    )


def _parse_jsonish(text: str) -> list[ChannelEdit]:
    # Try whole-file JSON first (array or single object)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = None

    if isinstance(data, list):
        return [edit_from_mapping(obj, line=i + 1) for i, obj in enumerate(data)]
    if isinstance(data, dict):
        return [edit_from_mapping(data, line=1)]

    # JSONL
    edits: list[ChannelEdit] = []
    for i, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("//"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as e:
            raise SystemExit(f"edit-channels: bad JSONL line={i}: {e}") from e
        edits.append(edit_from_mapping(obj, line=i))
    if not edits:
        raise SystemExit("edit-channels: no rows in JSONL")
    return edits


def _parse_csv(text: str) -> list[ChannelEdit]:
    reader = csv.DictReader(text.splitlines())
    if not reader.fieldnames:
        raise SystemExit("edit-channels: CSV missing header")
    edits: list[ChannelEdit] = []
    for i, row in enumerate(reader, start=2):  # header = line 1
        # skip blank rows
        if not any((v or "").strip() for v in row.values()):
            continue
        # normalize keys
        norm = { (k or "").strip().lower(): v for k, v in row.items() }
        edits.append(edit_from_mapping(norm, line=i))
    if not edits:
        raise SystemExit("edit-channels: no data rows in CSV")
    return edits


def normalize_handle(ref: str) -> list[str]:
    """Candidates to match against channel.custom_url."""
    s = ref.strip()
    if s.startswith("http"):
        # youtube.com/@foo or /channel/UCxxx
        if "/channel/" in s:
            return [s.rstrip("/").rsplit("/", 1)[-1]]
        if "@" in s:
            s = "@" + s.rsplit("@", 1)[-1].split("/")[0].split("?")[0]
        else:
            return [s]
    out: list[str] = []
    for cand in (s, s if s.startswith("@") else f"@{s}", s.lstrip("@")):
        if cand and cand not in out:
            out.append(cand)
    return out


async def resolve_channel(ref: str) -> dict | None:
    ref = ref.strip()
    if ref.startswith("UC") and len(ref) >= 20 and " " not in ref:
        row = await ChannelDAO.find_one_or_none(channel_id=ref)
        if row:
            return dict(row)

    for cand in normalize_handle(ref):
        if cand.startswith("UC") and len(cand) >= 20:
            row = await ChannelDAO.find_one_or_none(channel_id=cand)
            if row:
                return dict(row)
        row = await ChannelDAO.find_one_or_none(custom_url=cand)
        if row:
            return dict(row)
    return None


async def apply_edits(
    edits: list[ChannelEdit],
    *,
    apply: bool = False,
) -> dict:
    """
    Resolve + update channel rows. Default is dry-run (apply=False).
    Returns summary counts.
    """
    stats = {
        "total": len(edits),
        "missing": 0,
        "noop": 0,
        "would_update": 0,
        "updated": 0,
        "errors": 0,
    }
    for edit in edits:
        fields = edit.fields()
        row = await resolve_channel(edit.ref)
        where = f" line={edit.line}" if edit.line is not None else ""
        if not row:
            stats["missing"] += 1
            logger.warning(f"edit-channels MISSING {edit.ref!r}{where} → {fields}")
            continue

        cid = row["channel_id"]
        before = {k: row.get(k) for k in EDITABLE}
        delta = {k: v for k, v in fields.items() if before.get(k) != v}
        if not delta:
            stats["noop"] += 1
            logger.info(
                f"edit-channels NOOP {cid} ({row.get('custom_url')}) "
                f"{before}{where}"
            )
            continue

        after = {**before, **delta}
        logger.info(
            f"edit-channels {'APPLY' if apply else 'DRY'} {cid} "
            f"({row.get('custom_url') or edit.ref}) {before} → {after}{where}"
        )
        if apply:
            updated = await ChannelDAO.update({"channel_id": cid}, delta)
            if not updated:
                stats["errors"] += 1
                logger.error(f"edit-channels UPDATE FAILED {cid} {delta}")
                continue
            stats["updated"] += 1
        else:
            stats["would_update"] += 1

    mode = "applied" if apply else "dry-run"
    logger.info(f"edit-channels {mode}: {stats}")
    print(f"edit-channels {mode}: {stats}")
    if not apply and stats["would_update"]:
        print("(pass --apply to write)")
    return stats

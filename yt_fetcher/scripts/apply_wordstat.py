"""Apply sql/wordstat.sql (split statements; commit each)."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import text

from app.database import async_engine

SQL_PATH = ROOT / "sql" / "wordstat.sql"


def split_sql(raw: str) -> list[str]:
    """Split on ';' outside $$ … $$ dollar quotes. Skip empty / comment-only."""
    parts: list[str] = []
    buf: list[str] = []
    in_dollar = False
    i = 0
    n = len(raw)
    while i < n:
        if raw.startswith("$$", i):
            in_dollar = not in_dollar
            buf.append("$$")
            i += 2
            continue
        ch = raw[i]
        if ch == ";" and not in_dollar:
            stmt = "".join(buf).strip()
            buf = []
            if stmt and not all(
                line.strip().startswith("--") or not line.strip()
                for line in stmt.splitlines()
            ):
                parts.append(stmt)
            i += 1
            continue
        buf.append(ch)
        i += 1
    tail = "".join(buf).strip()
    if tail and not all(
        line.strip().startswith("--") or not line.strip()
        for line in tail.splitlines()
    ):
        parts.append(tail)
    return parts


async def main() -> None:
    stmts = split_sql(SQL_PATH.read_text(encoding="utf-8"))
    for stmt in stmts:
        async with async_engine.begin() as conn:
            await conn.execute(text(stmt))
        first = next(
            (ln.strip() for ln in stmt.splitlines() if ln.strip() and not ln.strip().startswith("--")),
            stmt[:40],
        )
        print("ok:", first[:72])
    print(f"applied {len(stmts)} statements from {SQL_PATH.name}")


if __name__ == "__main__":
    asyncio.run(main())

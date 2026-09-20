#!/usr/bin/env python3
"""
Scrape LiveDune YouTube world ranking → local JSON.

Phase 1: listing pages → title + detail URL (+ rank)
Phase 2: detail pages → @handle

Public api.livedune.com is paid (403). Rating UI is Next.js SSR — parse HTML.

Examples:
  python scripts/scrape_livedune_youtube.py list --max-pages 4
  python scripts/scrape_livedune_youtube.py details --batch-size 25 --delay 1.5
  python scripts/scrape_livedune_youtube.py all --max-pages 4
"""

from __future__ import annotations

import argparse
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / "data" / "livedune_youtube_world.json"
BASE = "https://livedune.com"
LIST_URL = BASE + "/ru/ratings/youtube/?page={page}"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

DETAIL_RE = re.compile(
    r"/ru/ratings/single/youtube/([^/\"'?#]+)/?", re.I
)
HANDLE_RE = re.compile(r"ChannelProfileHeader_handle__[^\"']*\"[^>]*>\s*(@[^\s<]+)\s*<")
HANDLE_FALLBACK_RE = re.compile(
    r'class="[^"]*ChannelProfileHeader_handle[^"]*"[^>]*>\s*(@[^\s<]+)'
)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_state(path: Path) -> dict:
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return {
        "source": "https://livedune.com/ru/ratings/youtube/",
        "updated_at": None,
        "list_pages_done": [],
        "total_pages_hint": None,
        "channels": {},  # slug -> record
    }


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = utc_now()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    tmp.replace(path)


def http_get(url: str, *, timeout: float = 45.0, retries: int = 4) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ru,en;q=0.8",
            "Connection": "close",
        },
    )
    last: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", "replace")
        except Exception as e:
            last = e
            time.sleep(min(8.0, 1.5 * attempt))
    assert last is not None
    raise last


def parse_list_page(html: str, page: int) -> tuple[list[dict], int | None]:
    soup = BeautifulSoup(html, "html.parser")
    total_pages = None
    nav = soup.find("nav")
    if nav:
        m = re.search(r"из\s+(\d+)", nav.get_text(" ", strip=True))
        if m:
            total_pages = int(m.group(1))

    seen: set[str] = set()
    rows: list[dict] = []
    # Prefer anchors that point to single channel pages
    for a in soup.find_all("a", href=True):
        href = a["href"]
        m = DETAIL_RE.search(href)
        if not m:
            continue
        slug = urllib.parse.unquote(m.group(1)).strip()
        if not slug or slug in seen:
            continue
        # skip junk
        if slug.startswith("%"):
            slug = urllib.parse.unquote(slug)
        text = a.get_text(" ", strip=True)
        title = re.sub(r"\s*Подробнее\s*$", "", text, flags=re.I).strip()
        if not title:
            continue
        seen.add(slug)
        detail_path = f"/ru/ratings/single/youtube/{urllib.parse.quote(slug, safe='')}/"
        rows.append(
            {
                "rank": None,  # filled below if we can
                "title": title,
                "slug": slug,
                "detail_url": BASE + detail_path,
                "list_page": page,
            }
        )

    # ranks: page 1 → 1..n, page 2 → n+1... (25 per page observed)
    per_page = len(rows) or 25
    for i, row in enumerate(rows):
        row["rank"] = (page - 1) * per_page + i + 1

    return rows, total_pages


def parse_detail_handle(html: str) -> str | None:
    m = HANDLE_RE.search(html) or HANDLE_FALLBACK_RE.search(html)
    if m:
        return m.group(1).strip()
    soup = BeautifulSoup(html, "html.parser")
    # class contains ChannelProfileHeader_handle
    for p in soup.find_all(["p", "span", "div"]):
        cls = " ".join(p.get("class") or [])
        if "ChannelProfileHeader_handle" in cls:
            t = p.get_text(strip=True)
            if t.startswith("@"):
                return t
    # last resort: first @token near h1
    m = re.search(
        r"<h1[^>]*>.*?@(?:[A-Za-z0-9._-]{2,64})", html, re.I | re.S
    )
    if m:
        hm = re.search(r"@[A-Za-z0-9._-]{2,64}", m.group(0))
        if hm:
            return hm.group(0)
    return None


def cmd_list(args: argparse.Namespace) -> None:
    state = load_state(args.out)
    start = args.page_from
    end = args.page_to
    if args.max_pages:
        end = start + args.max_pages - 1

    for page in range(start, end + 1):
        if page in state["list_pages_done"] and not args.force:
            print(f"skip list page {page} (done)")
            continue
        url = LIST_URL.format(page=page)
        print(f"GET {url}")
        try:
            html = http_get(url)
        except urllib.error.HTTPError as e:
            print(f"HTTP {e.code} page={page}, stop")
            break
        rows, total = parse_list_page(html, page)
        if total:
            state["total_pages_hint"] = total
        if not rows:
            print(f"empty page {page}, stop")
            break
        for row in rows:
            slug = row["slug"]
            prev = state["channels"].get(slug, {})
            state["channels"][slug] = {
                **prev,
                **{k: row[k] for k in ("rank", "title", "slug", "detail_url", "list_page")},
                "custom_url": prev.get("custom_url"),
                "detail_fetched_at": prev.get("detail_fetched_at"),
                "error": prev.get("error"),
            }
        if page not in state["list_pages_done"]:
            state["list_pages_done"].append(page)
        state["list_pages_done"] = sorted(set(state["list_pages_done"]))
        save_state(args.out, state)
        print(
            f"page {page}: +{len(rows)} channels, "
            f"total={len(state['channels'])}, hint_pages={state['total_pages_hint']}"
        )
        time.sleep(args.delay)


def cmd_details(args: argparse.Namespace) -> None:
    state = load_state(args.out)
    pending = [
        ch
        for ch in sorted(state["channels"].values(), key=lambda c: c.get("rank") or 10**9)
        if not ch.get("custom_url") and not (ch.get("error") and args.skip_errors)
    ]
    if args.only_missing:
        pass
    batch = pending[: args.batch_size]
    print(f"details pending={len(pending)} this_batch={len(batch)}")
    for i, ch in enumerate(batch, 1):
        url = ch["detail_url"]
        print(f"[{i}/{len(batch)}] GET {url}")
        try:
            html = http_get(url)
            handle = parse_detail_handle(html)
            if not handle:
                ch["error"] = "handle_not_found"
                print("  FAIL handle_not_found")
            else:
                ch["custom_url"] = handle
                ch["detail_fetched_at"] = utc_now()
                ch.pop("error", None)
                print(f"  OK {handle}")
        except urllib.error.HTTPError as e:
            ch["error"] = f"http_{e.code}"
            print(f"  HTTP {e.code}")
        except Exception as e:
            ch["error"] = str(e)
            print(f"  ERR {e}")
        state["channels"][ch["slug"]] = ch
        if i % 5 == 0 or i == len(batch):
            save_state(args.out, state)
        time.sleep(args.delay)
    save_state(args.out, state)
    with_h = sum(1 for c in state["channels"].values() if c.get("custom_url"))
    print(f"done batch; with_handle={with_h}/{len(state['channels'])}")


def cmd_stats(args: argparse.Namespace) -> None:
    state = load_state(args.out)
    ch = list(state["channels"].values())
    with_h = sum(1 for c in ch if c.get("custom_url"))
    errs = sum(1 for c in ch if c.get("error"))
    print(
        json.dumps(
            {
                "file": str(args.out),
                "channels": len(ch),
                "with_handle": with_h,
                "errors": errs,
                "list_pages_done": state.get("list_pages_done"),
                "total_pages_hint": state.get("total_pages_hint"),
                "updated_at": state.get("updated_at"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Scrape LiveDune YouTube ratings")
    p.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help=f"JSON path (default {DEFAULT_OUT})",
    )
    p.add_argument("--delay", type=float, default=1.2, help="seconds between requests")
    sub = p.add_subparsers(dest="cmd", required=True)

    pl = sub.add_parser("list", help="scrape listing pages")
    pl.add_argument("--page-from", type=int, default=1)
    pl.add_argument("--page-to", type=int, default=1)
    pl.add_argument("--max-pages", type=int, default=None, help="override page-to = from+N-1")
    pl.add_argument("--force", action="store_true", help="re-fetch done pages")
    pl.set_defaults(func=cmd_list)

    pd = sub.add_parser("details", help="scrape detail pages for @handle")
    pd.add_argument("--batch-size", type=int, default=25)
    pd.add_argument("--skip-errors", action="store_true", help="don't retry errored")
    pd.add_argument("--only-missing", action="store_true", default=True)
    pd.set_defaults(func=cmd_details)

    pa = sub.add_parser("all", help="list then details for those pages")
    pa.add_argument("--page-from", type=int, default=1)
    pa.add_argument("--page-to", type=int, default=1)
    pa.add_argument("--max-pages", type=int, default=4, help="default top ~100 (4×25)")
    pa.add_argument("--batch-size", type=int, default=100)
    pa.add_argument("--force", action="store_true")
    pa.set_defaults(func=None)

    ps = sub.add_parser("stats", help="print JSON summary")
    ps.set_defaults(func=cmd_stats)
    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.cmd == "all":
        # list
        ns = argparse.Namespace(
            out=args.out,
            delay=args.delay,
            page_from=args.page_from,
            page_to=args.page_to,
            max_pages=args.max_pages,
            force=args.force,
        )
        cmd_list(ns)
        ns2 = argparse.Namespace(
            out=args.out,
            delay=args.delay,
            batch_size=args.batch_size,
            skip_errors=False,
            only_missing=True,
        )
        cmd_details(ns2)
        cmd_stats(args)
        return
    args.func(args)


if __name__ == "__main__":
    main()

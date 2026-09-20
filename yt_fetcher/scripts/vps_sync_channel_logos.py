#!/usr/bin/env python3
"""One-shot: list/download missing channel logos on VPS. Stdlib only + psql via docker."""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

REMOTE_DIR = Path("/var/www/o2t4/backend/YTRatings/frontend/dist/channel_logo")
MIN_BYTES = 100


def psql(sql: str) -> str:
    cmd = [
        "docker",
        "exec",
        "-i",
        "o2t4_db",
        "psql",
        "-U",
        "root",
        "-d",
        "ytr_db",
        "-t",
        "-A",
        "-c",
        sql,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if r.returncode != 0:
        raise SystemExit(f"psql failed: {r.stderr or r.stdout}")
    return r.stdout


def load_category(category_id: int) -> dict:
    line = psql(
        f"select id||E'\\t'||coalesce(name,'')||E'\\t'||coalesce(sort_order::text,'') "
        f"from category where id={int(category_id)};"
    ).strip()
    if not line:
        raise SystemExit(f"category {category_id} not found")
    cid, name, sort_order = line.split("\t")
    return {"id": int(cid), "name": name, "sort_order": int(sort_order or 999)}


def load_channels(category_id: int, priority: int) -> list[dict]:
    sql = f"""
select json_agg(row_to_json(t)) from (
  select channel_id, channel_title, custom_url, thumbnail_url, priority
  from channel
  where status=1 and category_id={int(category_id)} and priority<={int(priority)}
  order by priority, channel_id
) t;
"""
    raw = psql(sql).strip()
    if not raw or raw == "":
        return []
    data = json.loads(raw)
    return data or []


def filename_for(ch: dict) -> str:
    base = (ch.get("custom_url") or ch.get("channel_id") or "").strip()
    return f"{base}.jpg"


def download_one(job: dict) -> dict:
    dest = REMOTE_DIR / job["filename"]
    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        req = urllib.request.Request(
            job["url"], headers={"User-Agent": "YTRatingsLogoSync/1.0"}
        )
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = resp.read()
        if len(data) < MIN_BYTES:
            return {
                "ok": False,
                "filename": job["filename"],
                "error": f"too_small:{len(data)}",
            }
        tmp.write_bytes(data)
        tmp.replace(dest)
        return {"ok": True, "filename": job["filename"], "bytes": len(data)}
    except Exception as e:
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass
        return {"ok": False, "filename": job["filename"], "error": str(e)}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--cats", required=True, help="comma-separated category ids")
    p.add_argument("--priority", type=int, default=100)
    p.add_argument("--max-sort-order", type=int, default=3)
    p.add_argument("--workers", type=int, default=20)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--force", action="store_true")
    args = p.parse_args()

    cat_ids = [int(x) for x in args.cats.split(",") if x.strip()]
    REMOTE_DIR.mkdir(parents=True, exist_ok=True)
    existing = {f.name for f in REMOTE_DIR.iterdir() if f.is_file()}
    print(f"remote_dir={REMOTE_DIR} existing_files={len(existing)}", flush=True)

    summaries = []
    for cid in cat_ids:
        cat = load_category(cid)
        if not args.force and cat["sort_order"] > args.max_sort_order:
            raise SystemExit(
                f"cat {cid} sort_order={cat['sort_order']} > {args.max_sort_order}"
            )
        channels = load_channels(cid, args.priority)
        jobs = []
        no_url = 0
        for ch in channels:
            url = (ch.get("thumbnail_url") or "").strip()
            if not url:
                no_url += 1
                print(
                    f"SKIP_NO_URL\t{ch.get('channel_id')}\t{ch.get('custom_url')}",
                    flush=True,
                )
                continue
            fn = filename_for(ch)
            jobs.append(
                {
                    "filename": fn,
                    "url": url,
                    "channel_id": ch.get("channel_id"),
                    "custom_url": ch.get("custom_url"),
                    "title": ch.get("channel_title"),
                }
            )

        present = [j for j in jobs if j["filename"] in existing]
        missing = [j for j in jobs if j["filename"] not in existing]
        print(
            f"CAT\t{cid}\t{cat['name']}\tsort={cat['sort_order']}\t"
            f"total={len(channels)}\twith_url={len(jobs)}\ton_vps={len(present)}\t"
            f"missing={len(missing)}\tno_url={no_url}",
            flush=True,
        )
        for j in missing[:30]:
            print(f"MISSING\t{j['filename']}\t{j['url'][:100]}", flush=True)
        if len(missing) > 30:
            print(f"MISSING\t...and {len(missing)-30} more", flush=True)

        ok = fail = 0
        failures = []
        if not args.dry_run and missing:
            print(f"DOWNLOAD_START workers={args.workers} n={len(missing)}", flush=True)
            with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
                for r in pool.map(download_one, missing):
                    if r["ok"]:
                        ok += 1
                        print(f"OK\t{r['filename']}\t{r.get('bytes')}", flush=True)
                    else:
                        fail += 1
                        failures.append(r)
                        print(f"FAIL\t{r['filename']}\t{r.get('error')}", flush=True)

        if ok:
            existing = {f.name for f in REMOTE_DIR.iterdir() if f.is_file()}

        summary = {
            "category_id": cid,
            "name": cat["name"],
            "sort_order": cat["sort_order"],
            "total": len(channels),
            "on_vps_before": len(present),
            "missing": len(missing),
            "no_url": no_url,
            "downloaded_ok": ok,
            "downloaded_fail": fail,
            "complete": (
                fail == 0
                and no_url == 0
                and (args.dry_run or ok == len(missing))
            ),
            "failures": failures,
        }
        summaries.append(summary)
        print("SUMMARY\t" + json.dumps(summary, ensure_ascii=False), flush=True)

    print("===FINAL===")
    print(json.dumps(summaries, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

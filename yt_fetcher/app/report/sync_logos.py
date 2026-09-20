"""
Sync channel logos to VPS.

1) List channels from VPS postgres (docker psql)
2) Diff against remote channel_logo/
3) Download missing from YouTube on THIS machine (VPS often can't reach ggpht)
4) Stream a tar over SSH into the remote dir (no permanent local clutter)
"""

from __future__ import annotations

import json
import subprocess
import tarfile
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import urllib.request

from app.logger import logger

DEFAULT_SSH_HOST = "root@195.133.201.63"
DEFAULT_PRIORITY = 100
DEFAULT_WORKERS = 20
DEFAULT_MAX_SORT_ORDER = 5
REMOTE_DIR = "/var/www/o2t4/backend/YTRatings/frontend/dist/channel_logo"
MIN_BYTES = 100


def _run(cmd: list[str], *, timeout: int, input_bytes: bytes | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        input=input_bytes,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def _with_retries(label: str, fn, *, attempts: int = 5, pause_s: float = 3.0):
    last = None
    for i in range(1, attempts + 1):
        try:
            return fn()
        except Exception as e:
            last = e
            logger.warning(f"{label} attempt {i}/{attempts} failed: {e}")
            if i < attempts:
                time.sleep(pause_s * i)
    raise RuntimeError(f"{label} failed after {attempts} attempts: {last}")


def _ssh_text(host: str, remote_cmd: str, *, timeout: int = 300) -> str:
    def once():
        r = _run(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=60",
                "-o",
                "ServerAliveInterval=15",
                host,
                remote_cmd,
            ],
            timeout=timeout,
        )
        out = (r.stdout or b"").decode("utf-8", "replace")
        err = (r.stderr or b"").decode("utf-8", "replace")
        if r.returncode == 255 and "timed out" in (out + err).lower():
            raise RuntimeError(err.strip() or out.strip() or "ssh timed out")
        if r.returncode != 0:
            raise RuntimeError(f"ssh rc={r.returncode}: {err or out}")
        return out

    return _with_retries("ssh", once)


def _ssh_bytes(
    host: str, remote_cmd: str, *, data: bytes, timeout: int = 600
) -> subprocess.CompletedProcess:
    def once():
        r = _run(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=60",
                "-o",
                "ServerAliveInterval=15",
                host,
                remote_cmd,
            ],
            timeout=timeout,
            input_bytes=data,
        )
        err = (r.stderr or b"").decode("utf-8", "replace")
        out = (r.stdout or b"").decode("utf-8", "replace")
        if r.returncode == 255 and "timed out" in (out + err).lower():
            raise RuntimeError(err.strip() or "ssh timed out")
        if r.returncode != 0:
            raise RuntimeError(f"ssh rc={r.returncode}: {err or out}")
        return r

    return _with_retries("ssh-stdin", once)


def _remote_psql_json(host: str, sql: str) -> object:
    # single-quoted SQL for remote bash; escape single quotes
    esc = sql.replace("'", "'\\''")
    cmd = (
        "docker exec -i o2t4_db psql -U root -d ytr_db -t -A -c "
        f"'{esc}'"
    )
    out = _ssh_text(host, cmd, timeout=120).strip()
    if not out:
        return None
    return json.loads(out)


def _remote_existing(host: str) -> set[str]:
    cmd = (
        "python3 - <<'PY'\n"
        "import json\n"
        "from pathlib import Path\n"
        f"p=Path({REMOTE_DIR!r})\n"
        "print(json.dumps([f.name for f in p.iterdir() if f.is_file()] if p.is_dir() else []))\n"
        "PY"
    )
    return set(json.loads(_ssh_text(host, cmd, timeout=120).strip() or "[]"))


def _download_one(job: dict, dest_dir: Path) -> dict:
    dest = dest_dir / job["filename"]
    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        req = urllib.request.Request(
            job["url"],
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Referer": "https://www.youtube.com/",
                "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
            },
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


def _tar_bytes(files_dir: Path, filenames: list[str]) -> bytes:
    import io

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tar:
        for name in filenames:
            path = files_dir / name
            tar.add(path, arcname=name)
    return buf.getvalue()


def sync_category_logos(
    category_ids: list[int],
    *,
    priority: int = DEFAULT_PRIORITY,
    max_sort_order: int = DEFAULT_MAX_SORT_ORDER,
    workers: int = DEFAULT_WORKERS,
    ssh_host: str = DEFAULT_SSH_HOST,
    dry_run: bool = False,
    force: bool = False,
) -> list[dict]:
    summaries: list[dict] = []
    existing = _remote_existing(ssh_host)
    logger.info(f"remote {REMOTE_DIR}: {len(existing)} files")

    for cid in category_ids:
        cat_row = _remote_psql_json(
            ssh_host,
            f"select row_to_json(t) from ("
            f"select id, name, sort_order from category where id={int(cid)}"
            f") t;",
        )
        if not cat_row:
            raise ValueError(f"category_id={cid} not found")
        sort_order = int(cat_row.get("sort_order") or 999)
        name = cat_row.get("name") or ""
        if not force and sort_order > max_sort_order:
            raise ValueError(
                f"cat {cid} sort_order={sort_order} > max={max_sort_order}"
            )

        channels = _remote_psql_json(
            ssh_host,
            f"select json_agg(row_to_json(t)) from ("
            f"select channel_id, channel_title, custom_url, thumbnail_url, priority "
            f"from channel where status=1 and category_id={int(cid)} "
            f"and priority<={int(priority)} order by priority, channel_id"
            f") t;",
        ) or []

        jobs = []
        no_url = 0
        for ch in channels:
            url = (ch.get("thumbnail_url") or "").strip()
            if not url:
                no_url += 1
                logger.warning(
                    f"SKIP_NO_URL {ch.get('channel_id')} {ch.get('custom_url')}"
                )
                continue
            base = (ch.get("custom_url") or ch.get("channel_id") or "").strip()
            jobs.append(
                {
                    "filename": f"{base}.jpg",
                    "url": url,
                    "channel_id": ch.get("channel_id"),
                    "custom_url": ch.get("custom_url"),
                }
            )

        present = [j for j in jobs if j["filename"] in existing]
        missing = [j for j in jobs if j["filename"] not in existing]
        logger.info(
            f"CAT {cid} ({name}) sort={sort_order} total={len(channels)} "
            f"with_url={len(jobs)} on_vps={len(present)} missing={len(missing)} "
            f"no_url={no_url}"
        )
        for j in missing[:25]:
            logger.info(f"MISSING {j['filename']} {j['url'][:90]}")
        if len(missing) > 25:
            logger.info(f"MISSING ...and {len(missing)-25} more")

        ok = fail = 0
        failures: list[dict] = []

        if dry_run:
            summaries.append(
                {
                    "category_id": cid,
                    "name": name,
                    "sort_order": sort_order,
                    "total": len(channels),
                    "on_vps_before": len(present),
                    "missing": len(missing),
                    "no_url": no_url,
                    "downloaded_ok": 0,
                    "downloaded_fail": 0,
                    "uploaded": 0,
                    "complete": False,
                    "failures": [],
                }
            )
            continue

        if not missing:
            summaries.append(
                {
                    "category_id": cid,
                    "name": name,
                    "sort_order": sort_order,
                    "total": len(channels),
                    "on_vps_before": len(present),
                    "missing": 0,
                    "no_url": no_url,
                    "downloaded_ok": 0,
                    "downloaded_fail": 0,
                    "uploaded": 0,
                    "complete": no_url == 0,
                    "failures": [],
                }
            )
            continue

        with tempfile.TemporaryDirectory(prefix="ytr_logos_") as tmp:
            tmp_path = Path(tmp)
            logger.info(
                f"local download start: {len(missing)} files, workers={workers} → {tmp_path}"
            )
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futs = {
                    pool.submit(_download_one, j, tmp_path): j for j in missing
                }
                for fut in as_completed(futs):
                    r = fut.result()
                    if r["ok"]:
                        ok += 1
                        logger.info(f"OK {r['filename']} {r.get('bytes')}")
                    else:
                        fail += 1
                        failures.append(r)
                        logger.error(f"FAIL {r['filename']} {r.get('error')}")

            ok_names = [
                j["filename"]
                for j in missing
                if (tmp_path / j["filename"]).is_file()
            ]
            uploaded = 0
            if ok_names:
                logger.info(f"streaming tar of {len(ok_names)} files → VPS")
                blob = _tar_bytes(tmp_path, ok_names)
                remote = (
                    f"mkdir -p {REMOTE_DIR} && tar -x -C {REMOTE_DIR} && "
                    f"echo UPLOADED:{len(ok_names)}"
                )
                r = _ssh_bytes(ssh_host, remote, data=blob, timeout=600)
                out = (r.stdout or b"").decode("utf-8", "replace")
                logger.info(out.strip() or "upload done")
                uploaded = len(ok_names)
                existing |= set(ok_names)

        summary = {
            "category_id": cid,
            "name": name,
            "sort_order": sort_order,
            "total": len(channels),
            "on_vps_before": len(present),
            "missing": len(missing),
            "no_url": no_url,
            "downloaded_ok": ok,
            "downloaded_fail": fail,
            "uploaded": uploaded,
            "complete": fail == 0 and no_url == 0 and uploaded == len(missing),
            "failures": failures,
        }
        summaries.append(summary)
        if failures:
            from app.logger import save_errors

            save_errors(failures, f"logo_sync_cat{cid}")

    logger.info("=== sync-logos summary ===")
    for s in summaries:
        logger.info(
            f"cat={s['category_id']} ({s['name']}) sort={s['sort_order']} | "
            f"total={s['total']} on_vps_before={s['on_vps_before']} "
            f"missing={s['missing']} | dl_ok={s['downloaded_ok']} "
            f"dl_fail={s['downloaded_fail']} uploaded={s.get('uploaded', 0)} "
            f"no_url={s['no_url']} | complete={s['complete']}"
        )
    return summaries

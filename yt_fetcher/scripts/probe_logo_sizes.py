#!/usr/bin/env python3
"""Scan channel_logo JPEG dimensions without Pillow."""
from __future__ import annotations

import struct
from pathlib import Path

DIR = Path("/var/www/o2t4/backend/YTRatings/frontend/dist/channel_logo")


def jpeg_size(path: Path):
    with open(path, "rb") as f:
        data = f.read(256 * 1024)
    if data[:2] != b"\xff\xd8":
        return None
    i = 2
    while i + 9 < len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker in (0xC0, 0xC1, 0xC2):
            h, w = struct.unpack(">HH", data[i + 5 : i + 9])
            return w, h
        if marker in (0xD9, 0xDA):
            break
        if marker == 0xFF:
            i += 1
            continue
        seglen = struct.unpack(">H", data[i + 2 : i + 4])[0]
        i += 2 + seglen
    return None


def main():
    files = [f for f in DIR.iterdir() if f.suffix.lower() == ".jpg"]
    sq = nsq = bad = 0
    hist = {}
    examples = []
    for f in files:
        sz = jpeg_size(f)
        if not sz:
            bad += 1
            continue
        w, h = sz
        key = f"{w}x{h}"
        hist[key] = hist.get(key, 0) + 1
        if w == h:
            sq += 1
        else:
            nsq += 1
            if len(examples) < 50:
                examples.append((f.name, w, h, round(w / h, 3)))
    print(f"total={len(files)} square={sq} nonsquare={nsq} bad={bad}")
    print("top_sizes", sorted(hist.items(), key=lambda x: -x[1])[:15])
    print("nonsquare_examples:")
    for e in examples:
        print(e)


if __name__ == "__main__":
    main()

"""Render wordstat report → SVG word cloud (same palette as analysis/title_word_freq.ipynb)."""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

from app.logger import logger
from app.period import Period
from app.wordstat.dao import WordstatDAO, _as_date

# matplotlib tab10-style (title_word_freq.ipynb)
COLORS = {
    "new": "#1f77b4",
    "leaving": "#d62728",
    "both": "#9467bd",
    "core": "#7f7f7f",
}

DEFAULT_SIZE = (800, 420)


def default_out_dir() -> Path:
    """repo/frontend-nuxt/public/wordstat_img (svg.py → wordstat → app → yt_fetcher → repo)."""
    return (
        Path(__file__).resolve().parents[3]
        / "frontend-nuxt"
        / "public"
        / "wordstat_img"
    )


def svg_filename(category_id: int, period: date | Period | str) -> str:
    d = _as_date(period)
    return f"{category_id}_{d.year:04d}-{d.month:02d}.svg"


def public_url(category_id: int, period: date | Period | str) -> str:
    return f"/wordstat_img/{svg_filename(category_id, period)}"


def _cyrillic_font() -> str | None:
    """Prefer a Windows/Linux font with Cyrillic glyphs."""
    candidates = [
        os.environ.get("WORDSTAT_FONT"),
        r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\segoeui.ttf",
        r"C:\Windows\Fonts\calibri.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for c in candidates:
        if c and Path(c).is_file():
            return c
    return None


def _word(it: dict) -> str:
    return (it.get("word") or it.get("lexeme") or "").strip()


def _freqs_and_colors(report: dict) -> tuple[dict[str, float], dict[str, str]]:
    """Build freqs + colors for cloud of month M.

    Report already splits MoM:
      leaving — dropped after M−1 (show red, with their M−1 freq)
      new     — entered in M, incl. one-month spikes type=2 (blue)
      core    — stable in M (grey)

    Same word cannot be both leaving and new in one report (different months).
    """
    freqs: dict[str, float] = {}
    colors: dict[str, str] = {}

    def ingest(items: list[dict], color: str) -> None:
        for it in items or []:
            w = _word(it)
            if not w:
                continue
            freq = float(it.get("freq") or 0)
            if freq <= 0:
                continue
            # later roles override earlier if same surface (new > leaving > core)
            if w not in freqs or color != COLORS["core"]:
                freqs[w] = max(freqs.get(w, 0), freq)
                colors[w] = color
            else:
                freqs[w] = max(freqs[w], freq)

    ingest(report.get("core") or [], COLORS["core"])
    ingest(report.get("leaving") or [], COLORS["leaving"])
    ingest(report.get("new") or [], COLORS["new"])
    return freqs, colors


def report_to_svg(
    report: dict,
    *,
    width: int = DEFAULT_SIZE[0],
    height: int = DEFAULT_SIZE[1],
    font_path: str | None = None,
) -> str | None:
    """Return SVG string, or None if report has no words."""
    freqs, colors = _freqs_and_colors(report)
    if not freqs:
        return None

    from wordcloud import WordCloud

    font = font_path or _cyrillic_font()
    if not font:
        raise RuntimeError(
            "No Cyrillic font found. Set WORDSTAT_FONT to a .ttf path "
            "(e.g. C:\\Windows\\Fonts\\arial.ttf)."
        )

    def color_func(word, **_kwargs):
        return colors.get(word, COLORS["core"])

    wc = WordCloud(
        width=width,
        height=height,
        background_color="white",
        mode="RGB",
        font_path=font,
        color_func=color_func,
        prefer_horizontal=0.9,
        relative_scaling=0.4,
        max_words=len(freqs),
        collocations=False,
        margin=2,
    )
    wc.generate_from_frequencies(freqs)
    # wordcloud.to_svg embeds words as <text>; good for web hover preview
    try:
        return wc.to_svg(embed_rect=True)
    except TypeError:
        return wc.to_svg()


async def wordstat2svg(
    *,
    category_id: int,
    period: date | Period | str,
    out_dir: Path | str | None = None,
    width: int = DEFAULT_SIZE[0],
    height: int = DEFAULT_SIZE[1],
    font_path: str | None = None,
) -> Path | None:
    """Fetch report like API and write SVG. Returns path or None if empty."""
    report = await WordstatDAO.report(category_id=category_id, period=period)
    n = (
        len(report.get("leaving") or [])
        + len(report.get("core") or [])
        + len(report.get("new") or [])
    )
    if n == 0:
        logger.info(
            f"wordstat2svg skip cat={category_id} period={report.get('period')}: empty"
        )
        return None

    svg = report_to_svg(report, width=width, height=height, font_path=font_path)
    if not svg:
        return None

    dest_dir = Path(out_dir) if out_dir else default_out_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)
    path = dest_dir / svg_filename(category_id, report["period"])
    path.write_text(svg, encoding="utf-8")
    logger.info(
        f"wordstat2svg wrote {path} "
        f"(leaving={len(report['leaving'])} core={len(report['core'])} "
        f"new={len(report['new'])})"
    )
    return path


async def wordstat2svg_range(
    *,
    category_ids: list[int],
    period_from: date | Period | str,
    period_to: date | Period | str | None = None,
    out_dir: Path | str | None = None,
    **kwargs,
) -> dict:
    """Generate SVGs for cats × period range. Skips empty reports."""
    from app.wordstat.dao import _period_range

    start = _as_date(period_from)
    end = _as_date(period_to) if period_to else start
    if end < start:
        start, end = end, start
    periods = _period_range(start, end)

    written: list[str] = []
    skipped: list[str] = []
    for cat in category_ids:
        for p in periods:
            path = await wordstat2svg(
                category_id=cat, period=p, out_dir=out_dir, **kwargs
            )
            key = f"{cat}:{p.isoformat()}"
            if path:
                written.append(str(path))
            else:
                skipped.append(key)
    return {
        "written": written,
        "skipped": skipped,
        "out_dir": str(Path(out_dir) if out_dir else default_out_dir()),
    }

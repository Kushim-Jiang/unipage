#!/usr/bin/env python3
"""
Unified PDF page comparison for non-CJK Unicode blocks.

Renders reference and generated PDFs at high DPI, extracts outlines,
and compares contour shapes — pure geometry, no font rendering dependency.

Color scheme:
  - Matching outline pixels  → black  (0,0,0)
  - Only in reference        → red    (255,0,0)
  - Only in generated        → blue   (0,0,255)

Output per page:
  {prefix}_pgNN.png         — color-coded diff
  {prefix}_pgNN_overlay.png — green/magenta anaglyph overlay

Output summary:
  {prefix}_report.json      — per-page match percentages

Usage:
  python test/compare_pages.py ethiopic
  python test/compare_pages.py nabataean --dpi 300
  python test/compare_pages.py vithkuqi --page 1
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parent.parent
NON_CJK = PROJECT_ROOT / "temp" / "non-cjk"

# ── Block definitions ──────────────────────────────────────────

BLOCKS = {
    "ethiopic": {
        "ref_pdf": NON_CJK / "ethiopic" / "U1200-r.pdf",
        "gen_pdf": NON_CJK / "ethiopic" / "U1200-r2.pdf",
    },
    "nabataean": {
        "ref_pdf": NON_CJK / "nabataean" / "U10880-r.pdf",
        "gen_pdf": NON_CJK / "nabataean" / "U10880-r2.pdf",
    },
    "vithkuqi": {
        "ref_pdf": NON_CJK / "vithkuqi" / "U10570-r.pdf",
        "gen_pdf": NON_CJK / "vithkuqi" / "U10570-r2.pdf",
    },
}


# ═══════════════════════════════════════════════════════════════════
#  Public API — per-block comparison functions
# ═══════════════════════════════════════════════════════════════════


def compare_ethiopic(out_dir: str | Path | None = None, dpi: int = 600, page: int = -1):
    """Compare Ethiopic (U+1200–U+137F) reference vs generated PDF."""
    return _compare_block("ethiopic", out_dir, dpi, page)


def compare_nabataean(out_dir: str | Path | None = None, dpi: int = 600, page: int = -1):
    """Compare Nabataean (U+10880–U+108AF) reference vs generated PDF."""
    return _compare_block("nabataean", out_dir, dpi, page)


def compare_vithkuqi(out_dir: str | Path | None = None, dpi: int = 600, page: int = -1):
    """Compare Vithkuqi (U+10570–U+105BF) reference vs generated PDF."""
    return _compare_block("vithkuqi", out_dir, dpi, page)


# ═══════════════════════════════════════════════════════════════════
#  Internal
# ═══════════════════════════════════════════════════════════════════


def _compare_block(block_name: str, out_dir: str | Path | None, dpi: int, page: int) -> dict:
    blk = BLOCKS[block_name]
    ref_pdf = blk["ref_pdf"]
    gen_pdf = blk["gen_pdf"]

    if out_dir is None:
        out_dir = ref_pdf.parent
    else:
        out_dir = Path(out_dir)

    out_dir.mkdir(parents=True, exist_ok=True)
    prefix = block_name

    return _run_comparison(ref_pdf, gen_pdf, out_dir, prefix, dpi, page)


def _resolve_block(name: str) -> str:
    """Normalise block name (case-insensitive, partial match)."""
    name_l = name.lower()
    for key in BLOCKS:
        if key == name_l or key.startswith(name_l):
            return key
    return name_l


# ═══════════════════════════════════════════════════════════════════
#  Core rendering & comparison
# ═══════════════════════════════════════════════════════════════════


def render_page_to_array(doc, page_num: int, dpi: int = 600) -> np.ndarray:
    """Render a PDF page to a grayscale numpy array at given DPI."""
    import fitz

    page = doc[page_num]
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, colorspace=fitz.csGRAY)
    return np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)


def extract_outlines(img: np.ndarray, dark: int = 80, edge: float = 12.0) -> np.ndarray:
    """Extract outline pixels: dark areas + anti-aliased edges."""
    from scipy.ndimage import gaussian_filter, sobel

    smoothed = gaussian_filter(img.astype(np.float64), sigma=0.6)
    gx = sobel(smoothed, axis=1)
    gy = sobel(smoothed, axis=0)
    grad = np.sqrt(gx**2 + gy**2)

    is_dark = img < dark
    is_edge = grad > edge
    return is_dark | is_edge


def compare(ref_img: np.ndarray, gen_img: np.ndarray, dpi: int = 600) -> tuple[np.ndarray, dict]:
    """Compare two page images by their outlines."""
    ref_ink = extract_outlines(ref_img)
    gen_ink = extract_outlines(gen_img)

    h, w = ref_img.shape
    out = np.full((h, w, 3), 255, dtype=np.uint8)

    both = ref_ink & gen_ink
    only_ref = ref_ink & ~gen_ink
    only_gen = gen_ink & ~ref_ink

    out[both] = [0, 0, 0]
    out[only_ref] = [255, 0, 0]
    out[only_gen] = [0, 0, 255]

    content = ref_ink | gen_ink
    cp = max(int(np.sum(content)), 1)

    return out, {
        "match_pct": round(int(np.sum(both)) / cp * 100, 4),
        "ref_only_pct": round(int(np.sum(only_ref)) / cp * 100, 4),
        "gen_only_pct": round(int(np.sum(only_gen)) / cp * 100, 4),
        "match_px": int(np.sum(both)),
        "ref_only_px": int(np.sum(only_ref)),
        "gen_only_px": int(np.sum(only_gen)),
        "content_px": cp,
        "dpi": dpi,
    }


def make_overlay(ref_img: np.ndarray, gen_img: np.ndarray) -> np.ndarray:
    """Green/magenta overlay: ref→green, gen→magenta. Match→grayscale."""
    h, w = ref_img.shape
    out = np.zeros((h, w, 3), dtype=np.uint8)
    out[:, :, 1] = np.clip(255 - ref_img, 0, 255)
    inv_gen = np.clip(255 - gen_img, 0, 255)
    out[:, :, 0] = inv_gen
    out[:, :, 2] = inv_gen
    return out


def simple_compare(ref_img: np.ndarray, gen_img: np.ndarray, thr: int = 128):
    """Fast binary (non-outline) comparison. Returns (rgb, stats)."""
    h, w = ref_img.shape
    ri = ref_img < thr
    gi = gen_img < thr
    content = ri | gi
    cp = max(int(np.sum(content)), 1)

    out = np.full((h, w, 3), 255, dtype=np.uint8)
    out[ri & gi] = [0, 0, 0]
    out[ri & ~gi] = [255, 0, 0]
    out[gi & ~ri] = [0, 0, 255]

    return out, {
        "match_pct": round(int(np.sum(ri & gi)) / cp * 100, 4),
        "ref_only_pct": round(int(np.sum(ri & ~gi)) / cp * 100, 4),
        "gen_only_pct": round(int(np.sum(gi & ~ri)) / cp * 100, 4),
    }


def _run_comparison(
    ref_pdf: Path,
    gen_pdf: Path,
    out_dir: Path,
    prefix: str,
    dpi: int = 600,
    page: int = -1,
    simple: bool = False,
) -> dict:
    """Run full comparison pipeline. Returns match report dict."""
    import fitz

    ref = fitz.open(str(ref_pdf))
    gen = fitz.open(str(gen_pdf))
    n = min(ref.page_count, gen.page_count)
    pages = [page] if page >= 0 else range(n)

    print(f"Comparing {len(pages)} page(s) @ {dpi} DPI — {prefix}…")
    report: dict = {"dpi": dpi, "block": prefix, "pages": {}}

    for pg in pages:
        print(f"  Page {pg}…", end=" ", flush=True)
        ra = render_page_to_array(ref, pg, dpi)
        ga = render_page_to_array(gen, pg, dpi)

        mh = max(ra.shape[0], ga.shape[0])
        mw = max(ra.shape[1], ga.shape[1])

        def pad(a):
            if a.shape == (mh, mw):
                return a
            p = np.full((mh, mw), 255, dtype=np.uint8)
            p[: a.shape[0], : a.shape[1]] = a
            return p

        ra, ga = pad(ra), pad(ga)

        cmp_arr, stats = simple_compare(ra, ga) if simple else compare(ra, ga, dpi)

        tag = f"pg{pg:02d}"
        Image.fromarray(cmp_arr).save(str(out_dir / f"{prefix}_{tag}.png"), compress_level=1)
        Image.fromarray(make_overlay(ra, ga)).save(str(out_dir / f"{prefix}_{tag}_overlay.png"), compress_level=1)

        report["pages"][pg] = stats
        print(
            f"match={stats['match_pct']:.2f}%  "
            f"ref-only={stats['ref_only_pct']:.3f}%  "
            f"gen-only={stats['gen_only_pct']:.3f}%"
        )

    ref.close()
    gen.close()

    rp = out_dir / f"{prefix}_report.json"
    with open(rp, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    print(f"\nReport: {rp}")

    return report


# ═══════════════════════════════════════════════════════════════════
#  CLI entry point
# ═══════════════════════════════════════════════════════════════════


def main():
    parser = argparse.ArgumentParser(
        description="Unified PDF page comparison for non-CJK Unicode blocks",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  python test/compare_pages.py ethiopic
  python test/compare_pages.py nabataean --dpi 300 --page 0
  python test/compare_pages.py vithkuqi --outdir results/
        """,
    )
    parser.add_argument(
        "block",
        nargs="?",
        choices=list(BLOCKS) + ["all"],
        default="all",
        help="Block to compare (default: all)",
    )
    parser.add_argument("--dpi", type=int, default=600, help="Render DPI (default: 600)")
    parser.add_argument("--page", type=int, default=-1, help="Single page to compare (default: all)")
    parser.add_argument("--simple", action="store_true", help="Use fast binary comparison")
    parser.add_argument("--outdir", type=Path, default=None, help="Output directory (default: block directory)")
    args = parser.parse_args()

    blocks_to_run = list(BLOCKS) if args.block == "all" else [args.block]

    for name in blocks_to_run:
        print(f"\n{'=' * 60}")
        print(f"  {name.upper()}")
        print(f"{'=' * 60}")
        _compare_block(name, args.outdir, args.dpi, args.page)


if __name__ == "__main__":
    main()

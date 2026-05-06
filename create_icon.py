"""
Icon generator for mdtopdf.

Generates:
  assets/icons/icon_1024.png  — master high-res PNG
  assets/icons/icon.ico       — Windows multi-size ICO
  assets/icons/icon.icns      — macOS ICNS (requires macOS iconutil)
  assets/icons/icon_*.png     — individual sizes (16,32,48,64,128,256,512,1024)

Design concept
--------------
  • Rounded-square app-icon shape (iOS / macOS style)
  • Deep navy-to-indigo gradient background
  • Central "M" letterform (Markdown) in white, bold
  • Small "PDF" badge with coral accent in the bottom-right quadrant
  • Subtle page-fold / document shadow behind the "M"
  • Works cleanly at 16 × 16 up to 1024 × 1024
"""
from __future__ import annotations

import math
import os
import struct
import subprocess
import sys
import zlib
from pathlib import Path

# ---------------------------------------------------------------------------
# Pillow is required (already in requirements.txt)
# ---------------------------------------------------------------------------
try:
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
except ImportError:
    sys.exit("Pillow is not installed.  Run: pip install Pillow")

ASSETS_DIR = Path(__file__).parent / "assets" / "icons"
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Colour palette
# ---------------------------------------------------------------------------
BG_TOP    = (15,  23,  42)   # #0f172a  slate-900
BG_BOT    = (30,  41,  59)   # #1e293b  slate-800
PAGE_CLR  = (241, 245, 249)  # #f1f5f9  slate-100
FOLD_CLR  = (203, 213, 225)  # #cbd5e1  slate-300
TEXT_CLR  = (255, 255, 255)  # white
BADGE_BG  = (239,  68,  68)  # #ef4444  red-500
BADGE_TXT = (255, 255, 255)
ARROW_CLR = (251, 191,  36)  # #fbbf24  amber-400


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def _rounded_rect_mask(size: int, radius_frac: float = 0.22) -> Image.Image:
    """Return an 'L' mode mask with a filled rounded rectangle."""
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    r = int(size * radius_frac)
    draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=r, fill=255)
    return mask


def _linear_gradient(size: int, top: tuple, bot: tuple) -> Image.Image:
    """Vertical linear gradient from *top* to *bot* colour."""
    img = Image.new("RGBA", (size, size))
    draw = ImageDraw.Draw(img)
    for y in range(size):
        t = y / (size - 1)
        r = int(top[0] + (bot[0] - top[0]) * t)
        g = int(top[1] + (bot[1] - top[1]) * t)
        b = int(top[2] + (bot[2] - top[2]) * t)
        draw.line([(0, y), (size - 1, y)], fill=(r, g, b, 255))
    return img


def _best_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Try several system fonts; fall back to Pillow's built-in."""
    candidates = [
        "/System/Library/Fonts/HelveticaNeue.ttc",
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial Bold.ttf",
        "/Library/Fonts/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            try:
                idx = 1 if bold and path.endswith(".ttc") else 0
                return ImageFont.truetype(path, size, index=idx)
            except Exception:
                try:
                    return ImageFont.truetype(path, size, index=0)
                except Exception:
                    continue
    return ImageFont.load_default()


# ---------------------------------------------------------------------------
# Core icon renderer
# ---------------------------------------------------------------------------

def render_icon(size: int) -> Image.Image:
    """
    Draw the mdtopdf icon at *size* × *size* pixels and return an RGBA image.

    Layout (normalised coordinates, scaled by *size*):
    ┌──────────────────────────────────────────┐
    │  [gradient background, rounded corners]  │
    │                                          │
    │        ┌───────────┐                     │
    │        │  document │  (white page)       │
    │        │           │                     │
    │        │     M     │                     │
    │        │      →    │  (amber arrow)      │
    │        │       PDF │                     │
    │        └───────────┘                     │
    │                         ● badge          │
    └──────────────────────────────────────────┘
    """
    s = size
    canvas = Image.new("RGBA", (s, s), (0, 0, 0, 0))

    # ── 1. Background gradient ─────────────────────────────────────────────
    bg = _linear_gradient(s, BG_TOP, BG_BOT)
    mask = _rounded_rect_mask(s, radius_frac=0.22)
    bg.putalpha(mask)
    canvas.paste(bg, (0, 0), bg)
    draw = ImageDraw.Draw(canvas)

    # ── 2. Document / page shape ───────────────────────────────────────────
    # Page occupies ≈60 % of the icon, centred and slightly raised
    page_w = int(s * 0.54)
    page_h = int(s * 0.64)
    px = (s - page_w) // 2
    py = int(s * 0.14)
    fold = int(s * 0.12)          # folded-corner size

    # Shadow (soft)
    shadow_off = max(2, s // 64)
    for i in range(max(1, s // 48), 0, -1):
        alpha = int(80 * (1 - i / (s // 48 + 1)))
        draw.rounded_rectangle(
            [px + shadow_off + i, py + shadow_off + i,
             px + page_w + shadow_off + i, py + page_h + shadow_off + i],
            radius=max(2, s // 48),
            fill=(0, 0, 0, alpha),
        )

    # Page body (clip folded corner with polygon)
    pts = [
        (px,              py + fold),
        (px + fold,       py),
        (px + page_w,     py),
        (px + page_w,     py + page_h),
        (px,              py + page_h),
    ]
    draw.polygon(pts, fill=PAGE_CLR + (255,))

    # Fold triangle
    fold_pts = [
        (px,        py + fold),
        (px + fold, py),
        (px + fold, py + fold),
    ]
    draw.polygon(fold_pts, fill=FOLD_CLR + (255,))

    # ── 3. "M" glyph ──────────────────────────────────────────────────────
    m_size = int(page_h * 0.52)
    m_font = _best_font(m_size, bold=True)
    m_x = px + page_w // 2
    m_y = py + int(page_h * 0.20)

    # Draw with slight drop-shadow for legibility
    draw.text(
        (m_x + max(1, s // 128), m_y + max(1, s // 128)),
        "M", font=m_font, fill=(100, 116, 139, 180), anchor="mt",
    )
    draw.text((m_x, m_y), "M", font=m_font, fill=(15, 23, 42, 230), anchor="mt")

    # ── 4. Arrow + "pdf" label beneath the M ──────────────────────────────
    label_size = int(page_h * 0.175)
    label_font = _best_font(label_size, bold=True)
    label_y = m_y + m_size + int(s * 0.005)
    label_x = px + page_w // 2

    # Arrow
    arrow_size = int(label_size * 1.05)
    arr_font = _best_font(arrow_size)
    draw.text(
        (label_x - int(label_size * 1.1), label_y),
        "→", font=arr_font, fill=ARROW_CLR + (230,), anchor="lt",
    )
    # "PDF" text
    draw.text(
        (label_x + int(label_size * 0.0), label_y),
        "PDF", font=label_font, fill=(239, 68, 68, 230), anchor="lt",
    )

    # ── 5. "md" micro-badge (top-left corner of page) ─────────────────────
    if size >= 48:
        badge_font_size = max(8, int(page_h * 0.14))
        badge_font = _best_font(badge_font_size, bold=True)
        draw.text(
            (px + fold + max(2, s // 96), py + max(2, s // 96)),
            "md", font=badge_font, fill=(100, 116, 139, 200), anchor="lt",
        )

    return canvas


# ---------------------------------------------------------------------------
# Export helpers
# ---------------------------------------------------------------------------

ICON_SIZES = [16, 32, 48, 64, 128, 256, 512, 1024]


def export_pngs(master: Image.Image) -> dict[int, Path]:
    paths: dict[int, Path] = {}
    for sz in ICON_SIZES:
        resample = Image.LANCZOS if sz < 1024 else Image.NEAREST
        img = master.resize((sz, sz), resample)
        p = ASSETS_DIR / f"icon_{sz}.png"
        img.save(p, "PNG", optimize=True)
        paths[sz] = p
        print(f"  ✓ {p.name}")
    return paths


def export_ico(png_paths: dict[int, Path]) -> Path:
    """Build a proper multi-size ICO file from the rendered PNGs."""
    # ICO sizes that Windows actually uses
    ico_sizes = [sz for sz in [256, 128, 64, 48, 32, 16] if sz in png_paths]
    images = []
    for sz in ico_sizes:
        img = Image.open(png_paths[sz]).convert("RGBA")
        images.append(img)
    out = ASSETS_DIR / "icon.ico"
    # PIL's ICO writer handles multiple sizes via 'sizes' keyword
    images[0].save(
        out,
        format="ICO",
        sizes=[(img.width, img.height) for img in images],
        append_images=images[1:],
    )
    print(f"  ✓ {out.name}  ({len(images)} sizes: {[i.width for i in images]})")
    return out


def export_icns_macos(png_paths: dict[int, Path]) -> Path | None:
    """
    Build a macOS .icns bundle via the system ``iconutil`` command.
    Falls back gracefully on non-macOS platforms.
    """
    if sys.platform != "darwin":
        print("  ⚠  Skipping .icns — macOS only (iconutil not available)")
        return None

    iconset_dir = ASSETS_DIR / "icon.iconset"
    iconset_dir.mkdir(exist_ok=True)

    # iconutil naming convention: icon_<role>.png
    iconutil_map = {
        16:  ("icon_16x16.png",      "icon_16x16@2x.png",   32),
        32:  ("icon_32x32.png",      "icon_32x32@2x.png",   64),
        64:  ("icon_64x64.png",      None,                  None),
        128: ("icon_128x128.png",    "icon_128x128@2x.png", 256),
        256: ("icon_256x256.png",    "icon_256x256@2x.png", 512),
        512: ("icon_512x512.png",    "icon_512x512@2x.png", 1024),
        1024: ("icon_512x512@2x.png", None,                 None),
    }

    written: set[str] = set()
    for src_sz, (name1, name2, hi_sz) in iconutil_map.items():
        if src_sz in png_paths and name1 not in written:
            dest = iconset_dir / name1
            import shutil
            shutil.copy2(png_paths[src_sz], dest)
            written.add(name1)
        if name2 and hi_sz and hi_sz in png_paths and name2 not in written:
            dest = iconset_dir / name2
            import shutil
            shutil.copy2(png_paths[hi_sz], dest)
            written.add(name2)

    out = ASSETS_DIR / "icon.icns"
    try:
        subprocess.run(
            ["iconutil", "-c", "icns", str(iconset_dir), "-o", str(out)],
            check=True, capture_output=True,
        )
        print(f"  ✓ {out.name}  (via iconutil)")
    except subprocess.CalledProcessError as exc:
        print(f"  ✗ iconutil failed: {exc.stderr.decode()}")
        return None
    return out


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    print("🎨  Rendering master icon at 1024 × 1024 …")
    master = render_icon(1024)
    master_path = ASSETS_DIR / "icon_1024.png"
    master.save(master_path, "PNG", optimize=True)
    print(f"  ✓ {master_path.name}")

    print("\n📐  Exporting PNG sizes …")
    png_paths = export_pngs(master)

    print("\n🪟  Exporting Windows ICO …")
    export_ico(png_paths)

    print("\n🍎  Exporting macOS ICNS …")
    export_icns_macos(png_paths)

    print("\n✅  All icons written to:", ASSETS_DIR)
    print(
        "\nUsage:\n"
        "  Windows  → assets/icons/icon.ico      (PyInstaller: --icon=assets/icons/icon.ico)\n"
        "  macOS    → assets/icons/icon.icns     (PyInstaller: --icon=assets/icons/icon.icns)\n"
        "  Taskbar  → assets/icons/icon_48.png\n"
        "  Dock     → assets/icons/icon_512.png\n"
    )


if __name__ == "__main__":
    main()


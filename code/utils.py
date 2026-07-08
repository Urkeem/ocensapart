"""Small cross-module helpers for asset path resolution and UI drawing."""

from pathlib import Path
import sys
from pygame import Rect

# Where PyInstaller unpacks files at runtime (when bundled)
_MEIPASS = getattr(sys, "_MEIPASS", None)

# Base dir of the running app
BASE_DIR = Path(_MEIPASS) if _MEIPASS else Path(__file__).resolve().parent

# Project root: when bundled, BASE_DIR **is** the root; in dev we’re inside /code so go up one
PROJECT_ROOT = BASE_DIR if _MEIPASS else BASE_DIR.parent

LEGACY_ASSET_ROOTS = {
    "audio": ("graphics", "audio"),
    "font": ("graphics", "font"),
    "tilesets": ("graphics", "tilesets"),
}


def _as_path(*parts) -> Path:
    return Path(*[str(part) for part in parts if str(part)])


def _asset_candidates(path: Path) -> list[Path]:
    parts = path.parts
    if not parts:
        return [PROJECT_ROOT]

    first = parts[0].lower()
    rest = parts[1:]
    candidates = [PROJECT_ROOT / path]

    if first == "graphics":
        candidates.append(PROJECT_ROOT / "graphics" / "sprites" / _as_path(*rest))
    elif first in LEGACY_ASSET_ROOTS:
        candidates.append(PROJECT_ROOT / _as_path(*LEGACY_ASSET_ROOTS[first], *rest))

    return candidates


def rp(*parts) -> str:
    """Build a path that works in dev, after asset reorganization, and in the EXE."""
    path = _as_path(*parts)
    if path.is_absolute():
        return str(path.resolve())

    candidates = _asset_candidates(path)
    for candidate in candidates:
        if candidate.exists():
            return str(candidate.resolve())

    return str(candidates[0].resolve())


def load_bar(screen, bar_w, bar_h, progress, target_progress, bg_surf, bar_surf, center_pos):
    # Guard + clamp
    if target_progress <= 0:
        ratio = 0.0
    else:
        ratio = max(0.0, min(1.0, progress / target_progress))

    # Center both sprites around center_pos
    bg_rect = bg_surf.get_rect(center=center_pos)
    bar_rect = bar_surf.get_rect(center=center_pos)

    # Clip the bar by ratio
    clip_w = int(bar_rect.width * ratio)
    clip = Rect(0, 0, clip_w, bar_rect.height)

    screen.blit(bg_surf, bg_rect)
    screen.blit(bar_surf, bar_rect, clip)

    return progress

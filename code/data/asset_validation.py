"""Validation for paths and frame geometry declared in the content manifest."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import struct

from data.content_manifest import (
    CROP_ASSETS,
    EFFECT_ASSETS,
    ENEMY_ASSETS,
    FISH_SHEETS,
    ITEM_ASSETS,
    LOCATION_ASSETS,
    ORE_ASSETS,
    ROCK_ASSETS,
    STORY_NPCS,
    VESSEL_ASSETS,
    FrameSequenceSpec,
    SheetSpec,
)
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class ValidationIssue:
    asset_id: str
    message: str

    def __str__(self) -> str:
        return f"{self.asset_id}: {self.message}"


def _path(relative_path: str) -> Path:
    return PROJECT_ROOT.joinpath(*relative_path.replace("\\", "/").split("/"))


def png_size(path: Path) -> tuple[int, int]:
    with path.open("rb") as handle:
        header = handle.read(24)
    if len(header) < 24 or header[:8] != PNG_SIGNATURE or header[12:16] != b"IHDR":
        raise ValueError("not a valid PNG header")
    return struct.unpack(">II", header[16:24])


def _validate_static(asset_id: str, relative_path: str, expected_size=None):
    path = _path(relative_path)
    if not path.is_file():
        return [ValidationIssue(asset_id, f"missing {relative_path}")]
    try:
        size = png_size(path)
    except (OSError, ValueError) as exc:
        return [ValidationIssue(asset_id, f"cannot read {relative_path}: {exc}")]
    if expected_size is not None and size != expected_size:
        return [ValidationIssue(asset_id, f"expected {expected_size}, found {size} at {relative_path}")]
    return []


def _validate_sheet(asset_id: str, spec: SheetSpec):
    issues = _validate_static(asset_id, spec.path)
    if issues:
        return issues
    width, height = png_size(_path(spec.path))
    frame_w, frame_h = spec.frame_size
    needed_width = spec.columns * frame_w
    needed_height = spec.rows * frame_h
    if width < needed_width or height < needed_height:
        issues.append(
            ValidationIssue(
                asset_id,
                f"{width}x{height} cannot hold {spec.frame_count} "
                f"{frame_w}x{frame_h} row-major frames",
            )
        )
    elif spec.exact_grid and (width, height) != (needed_width, needed_height):
        issues.append(
            ValidationIssue(
                asset_id,
                f"expected exact {needed_width}x{needed_height} grid, found {width}x{height}",
            )
        )
    return issues


def _sequence_number(path: str) -> int | None:
    match = re.search(r"(\d+)(?=\.png$)", path, flags=re.IGNORECASE)
    return int(match.group(1)) if match else None


def _validate_sequence(asset_id: str, spec: FrameSequenceSpec):
    issues = []
    numbers = tuple(_sequence_number(path) for path in spec.paths)
    expected = tuple(range(1, len(spec.paths) + 1))
    if numbers != expected:
        issues.append(ValidationIssue(asset_id, f"frames are not in numeric order: {numbers}"))
    for index, path in enumerate(spec.paths, start=1):
        issues.extend(_validate_static(f"{asset_id}.{index}", path, spec.frame_size))
    return issues


def validate_asset_manifest() -> tuple[ValidationIssue, ...]:
    issues = []

    for item_id, item in ITEM_ASSETS.items():
        issues.extend(_validate_sheet(f"item.{item_id}", item.sheet))
    for effect_id, sheet in EFFECT_ASSETS.items():
        issues.extend(_validate_sheet(f"effect.{effect_id}", sheet))
    for crop_id, sheet in CROP_ASSETS.items():
        issues.extend(_validate_sheet(f"crop.{crop_id}", sheet))
    for fish_id, sheet in FISH_SHEETS.items():
        issues.extend(_validate_sheet(f"fish.{fish_id}", sheet))

    for rock_id, rock in ROCK_ASSETS.items():
        for index, path in enumerate(rock.assets, start=1):
            issues.extend(_validate_static(f"rock.{rock_id}.{index}", f"graphics/sprites/environment/{path}"))
        issues.extend(_validate_static(f"rock.{rock_id}.drop", f"graphics/sprites/environment/{rock.drop_asset}", (32, 32)))
    for ore_id, ore in ORE_ASSETS.items():
        issues.extend(_validate_static(f"ore.{ore_id}", ore.path, ore.expected_size))

    for vessel_id, vessel in VESSEL_ASSETS.items():
        for animation_id, animation in vessel.animations.items():
            key = f"vessel.{vessel_id}.{animation_id}"
            if isinstance(animation, FrameSequenceSpec):
                issues.extend(_validate_sequence(key, animation))
            else:
                issues.extend(_validate_sheet(key, animation))
        for base_id, overlay_id in vessel.synchronized_overlays.items():
            base = vessel.animations[base_id]
            overlay = vessel.animations[overlay_id]
            if base.frame_count != overlay.frame_count:
                issues.append(ValidationIssue(f"vessel.{vessel_id}", f"{base_id} and {overlay_id} are not synchronized"))

    for enemy_id, enemy in ENEMY_ASSETS.items():
        root = _path(enemy.root)
        if not root.is_dir():
            issues.append(ValidationIssue(f"enemy.{enemy_id}", f"missing {enemy.root}"))
            continue
        sheets = tuple(sorted(root.rglob("*.png")))
        if not sheets:
            issues.append(ValidationIssue(f"enemy.{enemy_id}", "contains no PNG sheets"))
        for sheet in sheets:
            key = f"enemy.{enemy_id}.{sheet.name}"
            try:
                width, height = png_size(sheet)
            except (OSError, ValueError) as exc:
                issues.append(ValidationIssue(key, str(exc)))
                continue
            frame_size = enemy.frame_size_for(sheet.name)
            if frame_size is not None:
                frame_w, frame_h = frame_size
                if width % frame_w or height % frame_h:
                    issues.append(ValidationIssue(key, f"{width}x{height} is not divisible by {frame_w}x{frame_h}"))

    for npc_id, npc in STORY_NPCS.items():
        role, filename = npc.visual_profile.split("/", 1)
        issues.extend(_validate_static(f"npc.{npc_id}", f"graphics/sprites/npcs/{role}/{filename}.png"))
    for location_id, location in LOCATION_ASSETS.items():
        if location.asset:
            issues.extend(_validate_static(f"location.{location_id}", location.asset))

    return tuple(issues)

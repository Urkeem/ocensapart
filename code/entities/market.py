"""Coastal market stalls and their open/closed visual states."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pygame

from sprites import WorldObject
from utils import rp


MARKET_SCALE = 2
STALL_ASSETS = {
    "produce": ("produce_stall_empty.png", "produce_stall.png"),
    # Grain and produce intentionally share the authored empty produce stall.
    "grain": ("produce_stall_empty.png", "grain_stall.png"),
    "fish_meat": ("fish_meat_stall_empty.png", "fish_meat_stall.png"),
}


@lru_cache(maxsize=1)
def market_asset_folder() -> Path:
    for folder_name in ("market", "markert"):
        folder = Path(rp("graphics", "houses", "primary", folder_name))
        if folder.is_dir():
            return folder
    return Path(rp("graphics", "houses", "primary", "market"))


@lru_cache(maxsize=None)
def load_stall_image(stall_kind: str, is_open: bool) -> pygame.Surface:
    empty_name, open_name = STALL_ASSETS[stall_kind]
    filename = open_name if is_open else empty_name
    image = pygame.image.load(str(market_asset_folder() / filename)).convert_alpha()
    return pygame.transform.scale(
        image,
        (image.get_width() * MARKET_SCALE, image.get_height() * MARKET_SCALE),
    )


class MarketStall(WorldObject):
    def __init__(self, record):
        self.record = record
        self.stall_id = record["id"]
        self.stall_kind = record["stall_kind"]
        self.is_open = False
        self.merchant = None
        super().__init__(
            record["world_pos"],
            load_stall_image(self.stall_kind, False),
            anchor="midbottom",
        )
        self.name = "market_stall"
        self.collision_box = pygame.Rect(
            self.rect.left + 10,
            self.rect.bottom - 32,
            self.rect.width - 20,
            28,
        )
        self.interaction_rect = self.rect.inflate(96, 72)

    def set_open(self, is_open):
        is_open = bool(is_open)
        if self.is_open == is_open:
            return
        anchor = self.rect.midbottom
        self.is_open = is_open
        self.image_base = load_stall_image(self.stall_kind, is_open)
        self.image = self.image_base.copy()
        self.rect = self.image.get_rect(midbottom=anchor)
        self.collision_box = pygame.Rect(
            self.rect.left + 10,
            self.rect.bottom - 32,
            self.rect.width - 20,
            28,
        )
        self.interaction_rect = self.rect.inflate(96, 72)


def ensure_chunk_market_stalls(chunk):
    runtime = chunk.runtime.setdefault("market_stalls", {})
    records = [
        record
        for record in chunk.props
        if isinstance(record, dict) and record.get("type") == "market_stall"
    ]
    valid_ids = {record["id"] for record in records}
    for stale_id in tuple(runtime):
        if stale_id not in valid_ids:
            del runtime[stale_id]
    for record in records:
        runtime.setdefault(record["id"], MarketStall(record))
    return tuple(runtime[record["id"]] for record in records)

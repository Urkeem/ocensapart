"""House placement, door collision, and deterministic house asset selection."""

from __future__ import annotations

import random
from pathlib import Path

import pygame

from sprites import WorldObject
from core.support import import_file
from utils import rp


HOUSE_SOURCE_SIZE = (96, 128)
HOUSE_SCALE = 2
HOUSE_SIZE = (HOUSE_SOURCE_SIZE[0] * HOUSE_SCALE, HOUSE_SOURCE_SIZE[1] * HOUSE_SCALE)
DOOR_SOURCE_RECT = pygame.Rect(31, 92, 36, 36)

HOUSE_CATEGORY_NAMES = ("primary", "secondary", "tertiary")

_HOUSE_IMAGE_CACHE: dict[str, pygame.Surface] = {}
_HOUSE_SIZE_CACHE: dict[str, tuple[int, int]] = {}


def get_house_asset_names() -> list[str]:
    house_dir = Path(rp("graphics", "houses"))
    return sorted(path.relative_to(house_dir).as_posix() for path in house_dir.rglob("*.png"))


def get_house_asset_names_by_category(category: str | None = None) -> list[str]:
    assets = get_house_asset_names()
    if category is None:
        return assets
    prefix = f"{category}/"
    return [asset for asset in assets if asset.startswith(prefix)]


def get_house_source_size(asset_name: str) -> tuple[int, int]:
    cached = _HOUSE_SIZE_CACHE.get(asset_name)
    if cached is not None:
        return cached

    image = pygame.image.load(rp("graphics", "houses", *asset_name.split("/")))
    size = image.get_size()
    _HOUSE_SIZE_CACHE[asset_name] = size
    return size


def get_house_asset_scale(asset_name: str) -> int:
    return HOUSE_SCALE


def get_house_render_size(asset_name: str, scale: int | None = None) -> tuple[int, int]:
    if scale is None:
        scale = get_house_asset_scale(asset_name)
    source_w, source_h = get_house_source_size(asset_name)
    return source_w * scale, source_h * scale


def get_house_footprint_tiles(asset_name: str, tile_size: int, scale: int | None = None) -> tuple[int, int]:
    render_w, render_h = get_house_render_size(asset_name, scale)
    return (
        max(2, int((render_w + tile_size - 1) // tile_size)),
        max(3, int((render_h + tile_size - 1) // tile_size)),
    )


def get_house_image(asset_name: str) -> pygame.Surface:
    cached = _HOUSE_IMAGE_CACHE.get(asset_name)
    if cached is not None:
        return cached

    image = import_file("graphics", "houses", *asset_name.split("/"))
    scale = get_house_asset_scale(asset_name)
    if scale != 1:
        width, height = image.get_size()
        image = pygame.transform.scale(image, (width * scale, height * scale))
    image = image.convert_alpha()
    _HOUSE_IMAGE_CACHE[asset_name] = image
    return image


class Door:
    def __init__(self, house: "House"):
        self.house = house
        self.name = "door"
        self.rect = self._make_rect()
        self.interaction_rect = self.rect.inflate(24, 18)
        self.interaction_rect.move_ip(0, 18)
        self.world_tile = house.record["door_tile"]

    def _make_rect(self):
        if "door_rect" in self.house.record:
            scaled_rect = pygame.Rect(self.house.record["door_rect"])
        else:
            scaled_rect = pygame.Rect(
                DOOR_SOURCE_RECT.x * HOUSE_SCALE,
                DOOR_SOURCE_RECT.y * HOUSE_SCALE,
                DOOR_SOURCE_RECT.width * HOUSE_SCALE,
                DOOR_SOURCE_RECT.height * HOUSE_SCALE,
            )
        scaled_rect.topleft = (
            self.house.rect.left + scaled_rect.x,
            self.house.rect.top + scaled_rect.y,
        )
        return scaled_rect

    @property
    def path_target(self):
        return self.world_tile


class House(WorldObject):
    def __init__(self, house_record):
        self.record = house_record
        self.asset_name = house_record["asset"]
        self.top_left = tuple(house_record["world_pos"])
        image = get_house_image(self.asset_name)

        super().__init__(self.top_left, image, anchor="topleft")
        self.name = "house"
        self.house_id = house_record["id"]
        self.world_tile = house_record["world_tile"]
        self.footprint = tuple(house_record["footprint"])
        self.door = Door(self)
        self.door_tile = house_record["door_tile"]
        self.collision_box = pygame.Rect(0, 0, int(self.rect.width * 0.68), int(self.rect.height * 0.22))
        self.collision_box.midbottom = (self.rect.centerx, self.rect.bottom - 46)
        self.left_prop_area, self.right_prop_area = self._make_prop_areas()

    def _make_prop_areas(self):
        area_size = 44
        bottom = self.rect.bottom - 12
        left = pygame.Rect(0, 0, area_size, area_size)
        right = pygame.Rect(0, 0, area_size, area_size)
        left.midbottom = (self.rect.left + 36, bottom)
        right.midbottom = (self.rect.right - 36, bottom)
        return left, right

    @property
    def sort_y(self):
        return self.rect.bottom

    @property
    def prop_areas(self):
        return self.left_prop_area, self.right_prop_area


def choose_house_asset(rng: random.Random) -> str:
    assets = get_house_asset_names()
    if not assets:
        raise FileNotFoundError("No house assets found in graphics/houses")
    return rng.choice(assets)


def choose_house_asset_from_category(rng: random.Random, category: str | None = None) -> str:
    assets = get_house_asset_names_by_category(category)
    if not assets and category is not None:
        assets = get_house_asset_names()
    if not assets:
        raise FileNotFoundError("No house assets found in graphics/houses")
    return rng.choice(assets)

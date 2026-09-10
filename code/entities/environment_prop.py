"""Static environment props such as rocks, shells, and decorative objects."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import random

import pygame

from inventory_item import Item
from sprites import WorldObject
from core.support import import_file
from utils import rp


_ENV_IMAGE_CACHE: dict[tuple[str, float], pygame.Surface] = {}
_ENV_SHEET_CACHE: dict[str, pygame.Surface] = {}
PICKUP_PROP_TYPES = frozenset(
    {"shell", "rock_piece", "hay", "flower", "pot", "coin", "gem"}
)
BREAKABLE_PROP_TYPES = frozenset({"crate", "barrel"})

ASSET_PATH_ALIASES = {
    "props/general/buckets.png": "props/buckets/buckets.png#0",
}

PROP_SHEET_FRAMES = {
    "shells/shell_spritesheet.png": (16, 16, "horizontal"),
    "shells/shell_spritesheet2.png": (16, 16, "horizontal"),
    "props/flowers_pot_fenced/flowerfenced.png": (80, 35, "vertical"),
    "props/flowers_pot_fenced/flowerthin.png": (22, 40, "vertical"),
    "props/flowers_pot_fenced/flowermeduim.png": (22, 30, "vertical"),
    "props/flowers_pot_fenced/flowerlarge.png": (29, 31, "vertical"),
    "props/flowers_pot_fenced/flowersmall.png": (20, 23, "vertical"),
    "props/pots/potsmeduim.png": (30, 32, "horizontal"),
    "props/pots/potsthin.png": (25, 27, "horizontal"),
    "props/buckets/buckets.png": (32, 32, "horizontal"),
    "props/general/wheelbarrow.png": (36, 44, "horizontal", 48),
}

PROP_SHEET_FRAME_COUNTS = {
    "shells/shell_spritesheet.png": 10,
    "shells/shell_spritesheet2.png": 4,
}

NON_PROP_ASSETS = {
    # Rendered by the shoreline underwater-biome layer, not as pickups.
    "shells/under_water_stuff.png",
}

# Collision profiles to manipulate individual prop collision boxes.
COLLISION_PROFILES = {
    "default": {
        "inflate": (-0.58, -0.76),
        "position": {
            "collision_anchor": "midbottom",
            "sprite_anchor": "midbottom",
            "offset": (0, 0),
        },
    },
    "rock": {
        "inflate": (-0.70, -0.86),
        "position": {
            "collision_anchor": "midbottom",
            "sprite_anchor": "midbottom",
            "offset": (0, -4),
        },
    },
    "crate": {
        "inflate": (-0.45, -0.55),
        "position": {
            "collision_anchor": "midbottom",
            "sprite_anchor": "midbottom",
            "offset": (0, 0),
        },
    },
    "barrel": {
        "inflate": (-0.50, -0.58),
        "position": {
            "collision_anchor": "midbottom",
            "sprite_anchor": "midbottom",
            "offset": (0, 0),
        },
    },
}

LIGHT_SOURCE_PROFILES = {
    "lantern": {
        "anchor": (0.29, 0.37),
        "radius": 240,
        "color": (255, 190, 88),
        "intensity": 120,
    },
}


def _split_asset_frame(asset_path: str) -> tuple[str, int | None]:
    if "#" not in asset_path:
        return asset_path, None
    base_path, frame_part = asset_path.rsplit("#", 1)
    if frame_part.startswith("frame="):
        try:
            return base_path, int(frame_part.split("=", 1)[1])
        except ValueError:
            return base_path, None
    try:
        return base_path, int(frame_part)
    except ValueError:
        return base_path, None


def _crop_prop_sheet_frame(image: pygame.Surface, asset_path: str, frame_index: int | None) -> pygame.Surface:
    if frame_index is None or asset_path not in PROP_SHEET_FRAMES:
        return image

    frame_w, frame_h, direction, *stride_override = PROP_SHEET_FRAMES[asset_path]
    if direction == "horizontal":
        stride = stride_override[0] if stride_override else frame_w
        frame_count = max(1, image.get_width() // stride)
        frame_index %= frame_count
        rect = pygame.Rect(frame_index * stride, 0, frame_w, frame_h)
    else:
        frame_count = max(1, image.get_height() // frame_h)
        frame_index %= frame_count
        rect = pygame.Rect(0, frame_index * frame_h, frame_w, frame_h)

    return image.subsurface(rect).copy()


@lru_cache(maxsize=None)
def list_environment_assets(*parts):
    folder = Path(rp("graphics", "environment", *parts))
    environment_root = Path(rp("graphics", "environment"))
    assets = []
    for path in sorted(folder.glob("*.png")):
        asset_path = path.relative_to(environment_root).as_posix()
        if asset_path in NON_PROP_ASSETS:
            continue
        frame_count = PROP_SHEET_FRAME_COUNTS.get(asset_path)
        if frame_count is None:
            assets.append(asset_path)
        else:
            assets.extend(f"{asset_path}#{index}" for index in range(frame_count))
    return tuple(assets)


def get_environment_image(asset_path: str, scale: float = 2):
    asset_path = ASSET_PATH_ALIASES.get(asset_path, asset_path)
    key = (asset_path, float(scale))
    cached = _ENV_IMAGE_CACHE.get(key)
    if cached is not None:
        return cached

    base_asset_path, frame_index = _split_asset_frame(asset_path)
    if base_asset_path == "props/general/wheelbarrow.png" and frame_index is None:
        frame_index = 0
    image = _ENV_SHEET_CACHE.get(base_asset_path)
    if image is None:
        image = import_file("graphics", "environment", *base_asset_path.split("/"))
        _ENV_SHEET_CACHE[base_asset_path] = image
    image = _crop_prop_sheet_frame(image, base_asset_path, frame_index)
    if scale != 1:
        image = pygame.transform.scale(
            image,
            (
                max(1, int(round(image.get_width() * scale))),
                max(1, int(round(image.get_height() * scale))),
            ),
        )
    image = image.convert_alpha()
    _ENV_IMAGE_CACHE[key] = image
    return image


class EnvironmentProp(WorldObject):
    def __init__(self, prop_record):
        self.record = prop_record
        self.prop_id = prop_record["id"]
        self.prop_type = prop_record["prop_type"]
        self.variant = prop_record.get("variant", "")
        self.scale = prop_record.get("scale", 2)
        self.alive = not prop_record.get("removed", False)
        default_health = 2 if self.prop_type in BREAKABLE_PROP_TYPES else 0
        self.health = max(0, int(prop_record.get("health", default_health)))
        if self.prop_type in BREAKABLE_PROP_TYPES and self.health == 0 and self.alive:
            self.health = default_health
        self.record["health"] = self.health
        self.light_profile = LIGHT_SOURCE_PROFILES.get(self.prop_type)
        image = get_environment_image(prop_record["asset"], self.scale)

        super().__init__(tuple(prop_record["world_pos"]), image, anchor="midbottom")
        self.name = self.prop_type

        if prop_record.get("blocks_movement", False):
            self.collision_box = self._make_collision_box()
        else:
            self.collision_box = pygame.Rect(0, 0, 0, 0)

        self.pickup_rect = self.rect.inflate(24, 24)

    @property
    def emits_light(self):
        return self.light_profile is not None

    @property
    def light_position(self):
        anchor_x, anchor_y = self.light_profile.get("anchor", (0.5, 0.5))
        return (
            self.rect.left + self.rect.width * anchor_x,
            self.rect.top + self.rect.height * anchor_y,
        )

    @property
    def light_radius(self):
        return self.record.get("light_radius", self.light_profile["radius"])

    @property
    def light_color(self):
        return self.record.get("light_color", self.light_profile["color"])

    @property
    def light_intensity(self):
        return self.record.get("light_intensity", self.light_profile["intensity"])

    def _get_collision_profile(self):
        return COLLISION_PROFILES.get(self.prop_type, COLLISION_PROFILES["default"])

    def _make_collision_box(self):
        profile = self._get_collision_profile()
        inflate_x, inflate_y = profile["inflate"]
        collision_box = self.rect.copy().inflate(
            self.rect.width * inflate_x,
            self.rect.height * inflate_y,
        )
        self._position_collision_box(collision_box, profile)
        return collision_box

    def _position_collision_box(self, collision_box, profile):
        position = profile.get("position", {})
        collision_anchor = position.get("collision_anchor", "midbottom")
        sprite_anchor = position.get("sprite_anchor", "midbottom")
        offset_x, offset_y = position.get("offset", (0, 0))
        sprite_anchor_pos = getattr(self.rect, sprite_anchor)
        setattr(
            collision_box,
            collision_anchor,
            (sprite_anchor_pos[0] + offset_x, sprite_anchor_pos[1] + offset_y),
        )

    @property
    def sort_y(self):
        if self.prop_type in {"weed", "bush"}:
            return self.rect.bottom + int(self.rect.height * 0.20)
        return self.rect.bottom

    def damage(self, player_inventory=None):
        if self.prop_type not in {"rock", *BREAKABLE_PROP_TYPES} or not self.alive:
            return None

        self.health -= 1
        self.record["health"] = self.health
        if self.health > 0:
            return {"broken": False, "drops": 0}

        if self.prop_type == "rock":
            amount = 3 if self.variant == "big" else 1
            drops = amount
        else:
            rng = random.Random(f"{self.prop_id}:drops")
            drops = {"wood": rng.randint(1, 3)}
            if self.prop_type == "crate" and rng.random() < 0.4:
                drops["coin"] = rng.randint(1, 3)
            elif self.prop_type == "barrel":
                drops["rum"] = 1

        self.remove()
        if self.prop_type in BREAKABLE_PROP_TYPES:
            for item_name, amount in drops.items():
                self.add_to_inventory(player_inventory, item_name, amount)
        return {"broken": True, "drops": drops}

    def pickup(self, player_inventory=None):
        if self.prop_type not in PICKUP_PROP_TYPES or not self.alive:
            return False

        item_name = self.record.get("pickup_item", self.prop_type)
        self.add_to_inventory(player_inventory, item_name, 1)
        self.remove()
        return True

    def add_to_inventory(self, player_inventory, name, amount):
        if player_inventory is None:
            return
        if name == "coin" and hasattr(player_inventory, "add_coins"):
            player_inventory.add_coins(amount)
            return
        player_inventory = getattr(player_inventory, "inventory", player_inventory)
        for _ in range(amount):
            player_inventory.add_item_to_slot(
                Item(
                    name,
                    self.image_base,
                    True,
                    player_inventory.craft_system.return_craft_product(name),
                )
            )

    def remove(self):
        self.alive = False
        self.record["removed"] = True
        self.collision_box = pygame.Rect(0, 0, 0, 0)

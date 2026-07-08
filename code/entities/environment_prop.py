"""Static environment props such as rocks, shells, and decorative objects."""

from __future__ import annotations

from pathlib import Path

import pygame

from inventory_item import Item
from sprites import WorldObject
from core.support import import_file
from utils import rp


_ENV_IMAGE_CACHE: dict[tuple[str, float], pygame.Surface] = {}

PROP_SHEET_FRAMES = {
    "props/flowers/flowerthin.png": (22, 40, "vertical"),
    "props/flowers/flowermeduim.png": (22, 30, "vertical"),
    "props/flowers/flowerlarge.png": (29, 31, "vertical"),
    "props/flowers/flowersmall.png": (20, 23, "vertical"),
    "props/pots/potsmeduim.png": (30, 32, "horizontal"),
    "props/pots/potsthin.png": (25, 27, "horizontal"),
}

# Collision profiles to manipulate individual prop collision boxes.
COLLISION_PROFILES = {
    "default": {
        "inflate": (-0.35, -0.45),
        "position": {
            "collision_anchor": "midbottom",
            "sprite_anchor": "midbottom",
            "offset": (0, 0),
        },
    },
    "rock": {
        "inflate": (-0.65, -0.85),
        "position": {
            "collision_anchor": "midbottom",
            "sprite_anchor": "midbottom",
            "offset": (0, -24),
        },
    },
    "crate": {
        "inflate": (-0.25, -0.35),
        "position": {
            "collision_anchor": "midbottom",
            "sprite_anchor": "midbottom",
            "offset": (0, 0),
        },
    },
    "barrel": {
        "inflate": (-0.35, -0.40),
        "position": {
            "collision_anchor": "midbottom",
            "sprite_anchor": "midbottom",
            "offset": (0, 0),
        },
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

    frame_w, frame_h, direction = PROP_SHEET_FRAMES[asset_path]
    if direction == "horizontal":
        frame_count = max(1, image.get_width() // frame_w)
        frame_index %= frame_count
        rect = pygame.Rect(frame_index * frame_w, 0, frame_w, frame_h)
    else:
        frame_count = max(1, image.get_height() // frame_h)
        frame_index %= frame_count
        rect = pygame.Rect(0, frame_index * frame_h, frame_w, frame_h)

    return image.subsurface(rect).copy()


def list_environment_assets(*parts):
    folder = Path(rp("graphics", "environment", *parts))
    return sorted(path.relative_to(Path(rp("graphics", "environment"))).as_posix() for path in folder.glob("*.png"))


def get_environment_image(asset_path: str, scale: float = 2):
    key = (asset_path, float(scale))
    cached = _ENV_IMAGE_CACHE.get(key)
    if cached is not None:
        return cached

    base_asset_path, frame_index = _split_asset_frame(asset_path)
    image = import_file("graphics", "environment", *base_asset_path.split("/"))
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
        self.health = prop_record.get("health", 0)
        image = get_environment_image(prop_record["asset"], self.scale)

        super().__init__(tuple(prop_record["world_pos"]), image, anchor="midbottom")
        self.name = self.prop_type

        if prop_record.get("blocks_movement", False):
            self.collision_box = self._make_collision_box()
        else:
            self.collision_box = pygame.Rect(0, 0, 0, 0)

        self.pickup_rect = self.rect.inflate(24, 24)

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
        if self.prop_type != "rock" or not self.alive:
            return None

        self.health -= 1
        self.record["health"] = self.health
        if self.health > 0:
            return {"broken": False, "drops": 0}

        amount = 3 if self.variant == "big" else 1
        self.remove()
        return {"broken": True, "drops": amount}

    def pickup(self, player_inventory=None):
        if self.prop_type not in {"shell", "rock_piece"} or not self.alive:
            return False

        item_name = self.record.get("pickup_item", self.prop_type)
        self.add_to_inventory(player_inventory, item_name, 1)
        self.remove()
        return True

    def add_to_inventory(self, player_inventory, name, amount):
        if player_inventory is None:
            return
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

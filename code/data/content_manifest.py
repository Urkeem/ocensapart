"""Stable IDs and explicit asset contracts for The Last Cure content.

Runtime systems should refer to the IDs in this module. Authored filenames are
kept at this boundary so spelling fixes and future art swaps do not leak into
save data or quest definitions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import ceil
from pathlib import PurePosixPath
import re


@dataclass(frozen=True)
class SheetSpec:
    path: str
    frame_size: tuple[int, int]
    frame_count: int
    columns: int
    traversal: str = "row_major"
    exact_grid: bool = True

    @property
    def rows(self) -> int:
        return ceil(self.frame_count / self.columns)

    def frame_rects(self) -> tuple[tuple[int, int, int, int], ...]:
        """Return frames left-to-right across each row, then top-to-bottom."""
        if self.traversal != "row_major":
            raise ValueError(f"Unsupported sheet traversal {self.traversal!r}")
        frame_w, frame_h = self.frame_size
        return tuple(
            (
                (index % self.columns) * frame_w,
                (index // self.columns) * frame_h,
                frame_w,
                frame_h,
            )
            for index in range(self.frame_count)
        )


@dataclass(frozen=True)
class ItemSpec:
    id: str
    display_name: str
    sheet: SheetSpec
    role: str
    world_drop: bool
    aliases: tuple[str, ...] = ()


def _item(
    item_id: str,
    filename: str,
    *,
    display_name: str | None = None,
    role: str = "rare_drop",
    world_drop: bool = True,
    frame_count: int = 8,
    frame_size: tuple[int, int] = (16, 16),
    aliases: tuple[str, ...] = (),
) -> ItemSpec:
    return ItemSpec(
        id=item_id,
        display_name=display_name or item_id.replace("_", " ").title(),
        sheet=SheetSpec(
            path=f"graphics/sprites/items/{filename}",
            frame_size=frame_size,
            frame_count=frame_count,
            columns=frame_count,
        ),
        role=role,
        world_drop=world_drop,
        aliases=aliases,
    )


ITEM_ASSETS = {
    spec.id: spec
    for spec in (
        # The gem sheets contain four authored 32x16 sprites.
        _item("blue_gem", "bluegem.png", frame_count=4, frame_size=(32, 16), aliases=("bluegem",)),
        _item("green_gem", "greengem.png", frame_count=4, frame_size=(32, 16), aliases=("greengem",)),
        _item(
            "red_gem",
            "Items_RedGem.png",
            frame_count=4,
            frame_size=(32, 16),
            aliases=("redgem", "items_redgem"),
        ),
        _item("orange_gem", "orangegem.png", frame_count=4, frame_size=(32, 16), aliases=("orangegem",)),
        _item("bomb", "bomb.png"),
        _item("coin", "coin.png"),
        _item("health_potion", "health_portion.png", aliases=("health_portion",)),
        _item("heart", "heart.png"),
        _item("scroll", "scroll.png"),
        _item("stamina_potion", "stamina_portion.png", aliases=("stamina_portion",)),
        _item(
            "reward_star",
            "star.png",
            display_name="Reward Star",
            role="points_effect",
            world_drop=False,
            aliases=("star",),
        ),
        _item(
            "story_key",
            "story/key.png",
            display_name="Story Key",
            role="story_item",
            aliases=("key",),
        ),
        _item(
            "royal_tiara",
            "story/tiara.png",
            display_name="Royal Tiara",
            role="story_item",
            aliases=("tiara",),
        ),
    )
}


EFFECT_ASSETS = {
    "fire": SheetSpec(
        path="graphics/effects/fire/fire.png",
        frame_size=(96, 96),
        frame_count=19,
        columns=4,
        traversal="row_major",
    ),
    "points_reward": ITEM_ASSETS["reward_star"].sheet,
}


_CROP_FILES = {
    "artichoke": "artichoke.png",
    "barley": "barley.png",
    "kidney_beans": "beanskidney.png",
    "beetroot": "beetroot.png",
    "bell_pepper": "bellpepper.png",
    "blackberries": "blackberries.png",
    "blackcurrants": "blackcurrants.png",
    "blueberries": "blueberries.png",
    "broccoli": "brocoli.png",
    "cabbage": "carbage.png",
    "carrot": "carrot.png",
    "cauliflower": "cauliflower.png",
    "celery": "celery.png",
    "chili_pepper": "chillipepper.png",
    "corn": "corn.png",
    "eggplant": "eggplant.png",
    "garlic": "garlic.png",
    "grapes": "grapes.png",
    "kale": "kale.png",
    "lettuce": "lettuce.png",
    "oats": "oats.png",
    "onion": "onion.png",
    "peas": "peas.png",
    "potato": "potato.png",
    "pumpkin": "pumpkin.png",
    "raspberries": "raspberries.png",
    "rye": "rye.png",
    "spinach": "spinach.png",
    "strawberry": "strawberry.png",
    "sweet_potato": "sweetpotato.png",
    "tomato": "tomato.png",
    "turnip": "turnip.png",
    "watermelon": "watermelon.png",
    "wheat": "wheat.png",
    "yam": "yam.png",
    "zucchini": "zucchini.png",
}

CROP_ASSETS = {
    crop_id: SheetSpec(
        path=f"graphics/sprites/environment/crops/{filename}",
        frame_size=(16, 16),
        frame_count=20,
        columns=10,
    )
    for crop_id, filename in _CROP_FILES.items()
}


_FISH_COUNTS = {
    "ocean": {"allseason": 4, "fall": 7, "spring": 8, "summer": 9, "winter": 6},
    "pond": {"allseason": 3, "fall": 5, "spring": 3, "summer": 5, "winter": 1},
    "river": {"allseason": 3, "fall": 3, "spring": 7, "summer": 6, "winter": 5},
}

FISH_SHEETS = {}
for _locality, _seasons in _FISH_COUNTS.items():
    for _season, _count in _seasons.items():
        _filename = (
            "ocean_fish_allseasons.png"
            if (_locality, _season) == ("ocean", "allseason")
            else f"{_locality}_fish_{_season}.png"
        )
        FISH_SHEETS[f"{_locality}.{_season}"] = SheetSpec(
            path=f"graphics/sprites/animals/fish/{_filename}",
            frame_size=(16, 16),
            frame_count=_count,
            columns=_count,
            # The ocean all-season source has one unused extra cell.
            exact_grid=(_locality, _season) != ("ocean", "allseason"),
        )


@dataclass(frozen=True)
class RockSpec:
    id: str
    assets: tuple[str, ...]
    hit_points: int
    drop_item: str
    drop_count: int
    drop_asset: str


_PEBBLE_ASSET = "rocks/pebbles.png"
ROCK_ASSETS = {
    "land_rock": RockSpec(
        id="land_rock",
        assets=tuple(f"rocks/{index}.png" for index in range(1, 7)),
        hit_points=3,
        drop_item="rock",
        drop_count=3,
        drop_asset=_PEBBLE_ASSET,
    ),
    "beach_rock_small": RockSpec(
        id="beach_rock_small",
        assets=tuple(f"rocks/beach_rocks/small/r{index}.png" for index in range(1, 4)),
        hit_points=3,
        drop_item="rock",
        drop_count=1,
        drop_asset=_PEBBLE_ASSET,
    ),
    "beach_rock_big": RockSpec(
        id="beach_rock_big",
        assets=tuple(f"rocks/beach_rocks/big/r{index}.png" for index in range(1, 4)),
        hit_points=6,
        drop_item="rock",
        drop_count=3,
        drop_asset=_PEBBLE_ASSET,
    ),
}


@dataclass(frozen=True)
class StaticAssetSpec:
    id: str
    path: str
    expected_size: tuple[int, int] | None = None
    aliases: tuple[str, ...] = ()


ORE_ASSETS = {
    spec.id: spec
    for spec in (
        StaticAssetSpec("coal_ore", "graphics/sprites/environment/ores/coalOre.png", (16, 16)),
        StaticAssetSpec("iron_ore", "graphics/sprites/environment/ores/ironOre.png", (16, 16)),
        StaticAssetSpec("gold_ore", "graphics/sprites/environment/ores/goldOre.png", (16, 16)),
        StaticAssetSpec("diamond_ore", "graphics/sprites/environment/ores/diamondOre.png", (16, 16)),
        StaticAssetSpec("ruby_ore", "graphics/sprites/environment/ores/rubyOre.png", (16, 16)),
        StaticAssetSpec(
            "blue_sapphire_ore",
            "graphics/sprites/environment/ores/blueSaphireOre.png",
            (16, 16),
            aliases=("blue_saphire_ore", "blueSaphireOre"),
        ),
    )
}


@dataclass(frozen=True)
class FrameSequenceSpec:
    paths: tuple[str, ...]
    frame_size: tuple[int, int]


@dataclass(frozen=True)
class VesselSpec:
    id: str
    animations: dict[str, SheetSpec | FrameSequenceSpec]
    horizontal_flip: dict[str, str] = field(default_factory=dict)
    synchronized_overlays: dict[str, str] = field(default_factory=dict)


def _boat_sequence(state: str, direction: str) -> FrameSequenceSpec:
    if direction == "down":
        infix = f"down-{state}"
        separator = "" if state == "idle" else "-"
        names = tuple(
            f"boat-anims-{infix}{separator}{index}.png"
            for index in range(1, 15)
        )
    elif direction == "up":
        names = tuple(f"boat-anims-up-{state}-{index}.png" for index in range(1, 15))
    else:
        names = tuple(f"boat-anims-{state}-{index}.png" for index in range(1, 15))
    return FrameSequenceSpec(
        paths=tuple(
            f"graphics/sprites/environment/boat/{state}/{direction}/{name}"
            for name in names
        ),
        frame_size=(288, 256),
    )


_SHIP_FILES = {
    "down_idle": ("ship-animations - down-idle-baked.png", 15),
    "down_sailing": ("ship-animations - down-sailing-baked.png", 17),
    "down_sailing_wind": ("ship-animations - down-sailing-windFX.png", 17),
    "up_idle": ("ship-animations - up-idle-baked.png", 15),
    "up_sailing": ("ship-animations - up-sailing-baked.png", 17),
    "up_sailing_wind": ("ship-animations - up-sailing-windFX.png", 17),
    "sideways_idle": ("ship-animations-sideways-idle-baked.png", 15),
    "sideways_sailing": ("ship-animations-sideways-sailing-baked.png", 17),
    "sideways_sailing_wind": ("ship-animations-sideways-sailing-windFX-baked.png", 17),
}

VESSEL_ASSETS = {
    "player_boat": VesselSpec(
        id="player_boat",
        animations={
            f"{direction}_{state}": _boat_sequence(state, direction)
            for state in ("idle", "sailing")
            for direction in ("down", "up", "sideways")
        },
        horizontal_flip={"left_idle": "sideways_idle", "left_sailing": "sideways_sailing"},
    ),
    "pirate_ship": VesselSpec(
        id="pirate_ship",
        animations={
            animation_id: SheetSpec(
                path=f"graphics/sprites/environment/ship/{filename}",
                frame_size=(608, 640),
                frame_count=frame_count,
                columns=frame_count,
            )
            for animation_id, (filename, frame_count) in _SHIP_FILES.items()
        },
        horizontal_flip={"left_idle": "sideways_idle", "left_sailing": "sideways_sailing"},
        synchronized_overlays={
            "down_sailing": "down_sailing_wind",
            "up_sailing": "up_sailing_wind",
            "sideways_sailing": "sideways_sailing_wind",
        },
    ),
}


@dataclass(frozen=True)
class EnemyAssetSpec:
    id: str
    tier: str
    root: str
    default_frame_size: tuple[int, int] | None = None
    frame_size_overrides: tuple[tuple[str, tuple[int, int]], ...] = ()

    def frame_size_for(self, filename: str) -> tuple[int, int] | None:
        for marker, frame_size in self.frame_size_overrides:
            if marker.lower() in filename.lower():
                return frame_size
        return self.default_frame_size


_ENEMY_FOLDERS = {
    "bat": ("primary", "Bat"),
    "cultist": ("primary", "cultist"),
    "goblin_berserker": ("primary", "goblin_berserker"),
    "goblin_slinger": ("primary", "goblin_slinger"),
    "greatsword_skeleton": ("primary", "Greatsword Skeleton"),
    "skeleton": ("primary", "Skeleton"),
    "skeleton_grunt": ("primary", "skeleton_grunt"),
    "skeleton_hunter": ("primary", "skeleton_hunter"),
    "skeleton_king": ("primary", "skeleton_king"),
    "slime": ("primary", "Slime"),
    "eyeball_monster": ("secondary", "Eyeball Monster"),
    "flame_golem": ("secondary", "Flame Golem"),
    "hellbat": ("secondary", "Hellbat"),
    "lava_slime": ("secondary", "Lava Slime"),
    "orc": ("secondary", "Orc"),
    "orc_rider": ("secondary", "Orc rider"),
    "werebear": ("secondary", "werebear"),
    "werewolf": ("secondary", "Werewolf"),
    "armored_orc": ("tertiary", "Armored Orc"),
    "armored_skeleton": ("tertiary", "Armored Skeleton"),
    "demon": ("tertiary", "Demon"),
    "elite_orc": ("tertiary", "Elite Orc"),
    "necromancer": ("tertiary", "Necromancer"),
    "warlock": ("tertiary", "Warlock"),
}

_DIRECTIONAL_ENEMIES = {
    "cultist", "goblin_berserker", "goblin_slinger", "skeleton_grunt", "skeleton_hunter"
}
ENEMY_ASSETS = {}
for _enemy_id, (_tier, _folder) in _ENEMY_FOLDERS.items():
    _default_size = (48, 48) if _enemy_id in _DIRECTIONAL_ENEMIES else None
    _overrides = ()
    if _enemy_id == "skeleton_king":
        _default_size = (48, 48)
        _overrides = (
            ("Attack02", (64, 128)),
            ("Attack01", (64, 64)),
            ("Attack03", (64, 64)),
        )
    ENEMY_ASSETS[_enemy_id] = EnemyAssetSpec(
        id=_enemy_id,
        tier=_tier,
        root=f"graphics/sprites/enemies/{_tier}/{_folder}",
        default_frame_size=_default_size,
        frame_size_overrides=_overrides,
    )


@dataclass(frozen=True)
class StoryNpcSpec:
    id: str
    visual_profile: str


STORY_NPCS = {
    spec.id: spec
    for spec in (
        StoryNpcSpec("wife", "woman/npc woman A v00"),
        StoryNpcSpec("lillian", "girl/npc girl v00"),
        StoryNpcSpec("jim", "old_man/npc old man A v00"),
        StoryNpcSpec("alchemist", "mystic/npc mystic A v00"),
        StoryNpcSpec("hunter", "man/npc man A v00"),
        StoryNpcSpec("navigator", "old_man/npc old man B v00"),
        StoryNpcSpec("king", "king/npc king A v00"),
        StoryNpcSpec("queen", "queen/npc queen A v00"),
        StoryNpcSpec("princess", "woman/npc woman B v00"),
        StoryNpcSpec("pirate", "dandy/npc dandy v00"),
        StoryNpcSpec("necromancer", "mystic/npc mystic A v01"),
    )
}


@dataclass(frozen=True)
class LocationAssetSpec:
    id: str
    kind: str
    asset: str | None = None


LOCATION_ASSETS = {
    spec.id: spec
    for spec in (
        LocationAssetSpec("player_farm", "authored_exterior"),
        LocationAssetSpec("player_house_interior", "authored_interior"),
        LocationAssetSpec("village", "authored_exterior"),
        LocationAssetSpec("castle_exterior", "authored_exterior", "graphics/sprites/houses/tertiary/castle.png"),
        LocationAssetSpec("castle_interior", "authored_interior"),
        LocationAssetSpec("alchemist_workspace", "authored_interior"),
        *(LocationAssetSpec(f"hold_{index}", "dungeon") for index in range(1, 6)),
        LocationAssetSpec("necromancer_citadel", "dungeon"),
    )
}


CONTENT_ID_ALIASES = {
    "blueSaphireOre": "blue_sapphire_ore",
    "blue_saphire_ore": "blue_sapphire_ore",
    "Items_RedGem": "red_gem",
    "health_portion": "health_potion",
    "stamina_portion": "stamina_potion",
    "beanskidney": "kidney_beans",
    "brocoli": "broccoli",
    "carbage": "cabbage",
    "chillipepper": "chili_pepper",
    "sweetpotato": "sweet_potato",
    # The available bow skeleton is the authored stand-in for this old name.
    "skeleton_slinger": "skeleton_hunter",
    "hold_6": "necromancer_citadel",
}


def normalize_content_id(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")
    for alias, canonical in CONTENT_ID_ALIASES.items():
        alias_normalized = re.sub(r"[^a-z0-9]+", "_", alias.lower()).strip("_")
        if normalized == alias_normalized:
            return canonical
    for item in ITEM_ASSETS.values():
        if normalized == item.id or normalized in {
            re.sub(r"[^a-z0-9]+", "_", alias.lower()).strip("_")
            for alias in item.aliases
        }:
            return item.id
    return normalized


def asset_filename(path: str) -> str:
    return PurePosixPath(path).name

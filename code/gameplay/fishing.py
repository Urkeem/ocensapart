"""Fish catalogs and sprite extraction for locality/season fishing pools."""

from dataclasses import dataclass
from pathlib import PurePosixPath
import random

import pygame

from utils import rp
from data.content_manifest import FISH_SHEETS


FISH_FRAME_SIZE = 16
FISH_LOCALITIES = ("ocean", "pond", "river")
FISH_SEASONS = ("spring", "summer", "fall", "winter")

# Counts intentionally follow the fishing rules rather than the raw sheet
# width. In particular, ocean_fish_allseasons.png has one extra cell that is
# not part of the four-fish all-season pool.
FISH_SHEET_COUNTS = {locality: {} for locality in FISH_LOCALITIES}
FISH_SHEET_FILES = {}
for _sheet_id, _sheet in FISH_SHEETS.items():
    _locality, _season = _sheet_id.split(".", 1)
    FISH_SHEET_COUNTS[_locality][_season] = _sheet.frame_count
    FISH_SHEET_FILES[(_locality, _season)] = PurePosixPath(_sheet.path).name


def normalize_season(season):
    normalized = str(season or "summer").strip().lower()
    return normalized if normalized in FISH_SEASONS else "summer"


@dataclass(frozen=True)
class FishSpecies:
    locality: str
    season: str
    sheet_file: str
    frame_index: int
    required_reels: int
    point_reward: int
    unlock_at_fishing_points: int

    @property
    def id(self):
        return f"{self.locality}.{self.season}.{self.frame_index + 1}"

    @property
    def name(self):
        season_name = "All-Season" if self.season == "allseason" else self.season.title()
        return f"{self.locality.title()} {season_name} Fish {self.frame_index + 1}"

    @property
    def frame_rect(self):
        return (self.frame_index * FISH_FRAME_SIZE, 0, FISH_FRAME_SIZE, FISH_FRAME_SIZE)

    @property
    def unlock_id(self):
        return f"fish.{self.id}"


LOCALITY_UNLOCK_POINTS = {
    "pond": 0,
    "river": 50,
    "ocean": 150,
}


def _fish_unlock_threshold(locality, season, frame_index):
    """Spread species across their locality's progression band."""
    base = LOCALITY_UNLOCK_POINTS[locality]
    season_index = {"allseason": 0, "spring": 1, "summer": 2, "fall": 3, "winter": 4}[season]
    step = 5 if locality == "pond" else 10 if locality == "river" else 15
    if season == "allseason":
        return 0 if locality == "pond" else base + frame_index * step
    return base + max(1, season_index) * step + frame_index * step


def _build_catalog():
    catalog = {}
    locality_order = {name: index for index, name in enumerate(FISH_LOCALITIES)}
    locality_point_bonus = {"pond": 0, "river": 1, "ocean": 2}
    season_order = {"allseason": 0, "spring": 1, "summer": 2, "fall": 3, "winter": 4}
    for locality, seasons in FISH_SHEET_COUNTS.items():
        for season, count in seasons.items():
            species = []
            for frame_index in range(count):
                # Each species consistently needs one to three successful reel-ins.
                required_reels = 1 + (
                    locality_order[locality] + season_order[season] + frame_index
                ) % 3
                point_reward = required_reels + locality_point_bonus[locality]
                species.append(FishSpecies(
                    locality=locality,
                    season=season,
                    sheet_file=FISH_SHEET_FILES[(locality, season)],
                    frame_index=frame_index,
                    required_reels=required_reels,
                    point_reward=point_reward,
                    unlock_at_fishing_points=_fish_unlock_threshold(
                        locality,
                        season,
                        frame_index,
                    ),
                ))
            catalog[(locality, season)] = tuple(species)
    return catalog


FISH_CATALOG = _build_catalog()
FISH_BY_ID = {
    fish.id: fish
    for species in FISH_CATALOG.values()
    for fish in species
}
FISH_BY_NAME = {fish.name: fish for fish in FISH_BY_ID.values()}


def fish_species(fish_id_or_name):
    return FISH_BY_ID.get(str(fish_id_or_name)) or FISH_BY_NAME.get(str(fish_id_or_name))


def is_locality_unlocked(locality, game_state=None, *, fishing_points=None):
    locality = str(locality or "pond").strip().lower()
    if locality not in LOCALITY_UNLOCK_POINTS:
        return False
    if fishing_points is None:
        fishing_points = (
            0 if game_state is None else game_state.progression.fishing_points
        )
    return int(fishing_points) >= LOCALITY_UNLOCK_POINTS[locality]


def is_fish_unlocked(species, game_state=None, *, fishing_points=None):
    if fishing_points is None:
        fishing_points = (
            0 if game_state is None else game_state.progression.fishing_points
        )
    return (
        is_locality_unlocked(
            species.locality,
            game_state,
            fishing_points=fishing_points,
        )
        and int(fishing_points) >= species.unlock_at_fishing_points
    )


def get_fish_pool(locality, season, game_state=None, *, fishing_points=None):
    """Return the eligible locality + season pool, filtering when state is supplied."""
    locality = str(locality or "pond").strip().lower()
    if locality not in FISH_LOCALITIES:
        locality = "pond"
    season = normalize_season(season)
    pool = FISH_CATALOG[(locality, "allseason")] + FISH_CATALOG[(locality, season)]
    # Catalog callers without progression context retain access to the raw pool.
    if game_state is None and fishing_points is None:
        return pool
    return tuple(
        species
        for species in pool
        if is_fish_unlocked(
            species,
            game_state,
            fishing_points=fishing_points,
        )
    )


def choose_fish(locality, season, rng=None, game_state=None, *, fishing_points=None):
    rng = rng or random
    pool = get_fish_pool(
        locality,
        season,
        game_state,
        fishing_points=fishing_points,
    )
    return rng.choice(pool) if pool else None


def fishing_block_reason(locality, game_state=None, *, fishing_points=None):
    locality = str(locality or "pond").strip().lower()
    if fishing_points is None:
        fishing_points = (
            0 if game_state is None else game_state.progression.fishing_points
        )
    if locality not in LOCALITY_UNLOCK_POINTS:
        return "This water is not fishable."
    required = LOCALITY_UNLOCK_POINTS[locality]
    if int(fishing_points) < required:
        label = "Sea" if locality == "ocean" else locality.title()
        return f"{label} fishing unlocks at {required} fishing points."
    return "No fish are available here this season."


def unlocked_fish_ids(game_state=None, *, fishing_points=None):
    return tuple(
        fish.id
        for fish in FISH_BY_ID.values()
        if is_fish_unlocked(
            fish,
            game_state,
            fishing_points=fishing_points,
        )
    )


def next_fish_unlocks(game_state=None, *, fishing_points=None, limit=5):
    if fishing_points is None:
        fishing_points = (
            0 if game_state is None else game_state.progression.fishing_points
        )
    locked = sorted(
        (
            fish
            for fish in FISH_BY_ID.values()
            if fish.unlock_at_fishing_points > int(fishing_points)
        ),
        key=lambda fish: (fish.unlock_at_fishing_points, fish.name),
    )
    return tuple(locked[: max(0, int(limit))])


def load_fish_icon(species, size=(32, 32)):
    """Extract one fish frame and scale it for an inventory slot."""
    sheet = pygame.image.load(
        rp("graphics", "sprites", "animals", "fish", species.sheet_file)
    ).convert_alpha()
    icon = pygame.Surface((FISH_FRAME_SIZE, FISH_FRAME_SIZE), pygame.SRCALPHA)
    icon.blit(sheet, (0, 0), species.frame_rect)
    return pygame.transform.scale(icon, size)

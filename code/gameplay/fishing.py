"""Fish catalogs and sprite extraction for locality/season fishing pools."""

from dataclasses import dataclass
import random

import pygame

from utils import rp


FISH_FRAME_SIZE = 16
FISH_LOCALITIES = ("ocean", "pond", "river")
FISH_SEASONS = ("spring", "summer", "fall", "winter")

# Counts intentionally follow the fishing rules rather than the raw sheet
# width. In particular, ocean_fish_allseasons.png has one extra cell that is
# not part of the four-fish all-season pool.
FISH_SHEET_COUNTS = {
    "ocean": {
        "allseason": 4,
        "fall": 7,
        "spring": 8,
        "summer": 9,
        "winter": 6,
    },
    "pond": {
        "allseason": 3,
        "fall": 5,
        "spring": 3,
        "summer": 5,
        "winter": 1,
    },
    "river": {
        "allseason": 3,
        "fall": 3,
        "spring": 7,
        "summer": 6,
        "winter": 5,
    },
}

FISH_SHEET_FILES = {
    (locality, season): (
        "ocean_fish_allseasons.png"
        if (locality, season) == ("ocean", "allseason")
        else f"{locality}_fish_{season}.png"
    )
    for locality, seasons in FISH_SHEET_COUNTS.items()
    for season in seasons
}


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

    @property
    def name(self):
        season_name = "All-Season" if self.season == "allseason" else self.season.title()
        return f"{self.locality.title()} {season_name} Fish {self.frame_index + 1}"

    @property
    def frame_rect(self):
        return (self.frame_index * FISH_FRAME_SIZE, 0, FISH_FRAME_SIZE, FISH_FRAME_SIZE)


def _build_catalog():
    catalog = {}
    locality_order = {name: index for index, name in enumerate(FISH_LOCALITIES)}
    season_order = {"allseason": 0, "spring": 1, "summer": 2, "fall": 3, "winter": 4}
    for locality, seasons in FISH_SHEET_COUNTS.items():
        for season, count in seasons.items():
            species = []
            for frame_index in range(count):
                # Each species consistently needs one to three successful reel-ins.
                required_reels = 1 + (
                    locality_order[locality] + season_order[season] + frame_index
                ) % 3
                species.append(FishSpecies(
                    locality=locality,
                    season=season,
                    sheet_file=FISH_SHEET_FILES[(locality, season)],
                    frame_index=frame_index,
                    required_reels=required_reels,
                ))
            catalog[(locality, season)] = tuple(species)
    return catalog


FISH_CATALOG = _build_catalog()


def get_fish_pool(locality, season):
    """Return all fish catchable at a locality during a season."""
    locality = str(locality or "pond").strip().lower()
    if locality not in FISH_LOCALITIES:
        locality = "pond"
    season = normalize_season(season)
    return FISH_CATALOG[(locality, "allseason")] + FISH_CATALOG[(locality, season)]


def choose_fish(locality, season, rng=None):
    rng = rng or random
    return rng.choice(get_fish_pool(locality, season))


def load_fish_icon(species, size=(32, 32)):
    """Extract one fish frame and scale it for an inventory slot."""
    sheet = pygame.image.load(
        rp("graphics", "sprites", "animals", "fish", species.sheet_file)
    ).convert_alpha()
    icon = pygame.Surface((FISH_FRAME_SIZE, FISH_FRAME_SIZE), pygame.SRCALPHA)
    icon.blit(sheet, (0, 0), species.frame_rect)
    return pygame.transform.scale(icon, size)

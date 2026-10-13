"""Crop progression, planting, and seed-market definitions."""

from __future__ import annotations

from dataclasses import dataclass

from data.content_manifest import CROP_ASSETS


@dataclass(frozen=True)
class CropDefinition:
    id: str
    display_name: str
    harvest_points: int
    unlock_at_farming_points: int
    seasons: tuple[str, ...]
    market_kind: str
    seed_price: int
    growth_days: int = 4

    @property
    def unlock_id(self) -> str:
        return f"crop.{self.id}"

    @property
    def starts_unlocked(self) -> bool:
        return self.unlock_at_farming_points <= 0


# Milestones follow the balancing bands in the implementation workflow.  The
# exact values live here so future balance changes do not affect UI or soil
# code.
_CROP_PROGRESSION = {
    "corn": (0, 2, "produce", 4, 5, ("summer", "fall")),
    "tomato": (0, 3, "produce", 4, 5, ("summer",)),
    "carrot": (20, 4, "produce", 5, 4, ("spring", "fall")),
    "lettuce": (25, 4, "produce", 5, 4, ("spring", "fall")),
    "spinach": (30, 4, "produce", 5, 4, ("spring", "fall")),
    "turnip": (35, 4, "produce", 5, 4, ("spring", "fall")),
    "potato": (40, 4, "produce", 6, 4, ("spring", "summer", "fall")),
    "beetroot": (45, 4, "produce", 6, 4, ("spring", "fall")),
    "cabbage": (50, 4, "produce", 6, 4, ("spring", "fall")),
    "kale": (55, 4, "produce", 6, 4, ("spring", "fall", "winter")),
    "broccoli": (60, 4, "produce", 7, 4, ("spring", "fall")),
    "wheat": (75, 5, "grain", 6, 4, ("summer", "fall")),
    "barley": (85, 5, "grain", 6, 4, ("spring", "fall")),
    "oats": (95, 5, "grain", 6, 4, ("spring", "fall")),
    "rye": (105, 5, "grain", 7, 4, ("fall", "winter")),
    "kidney_beans": (115, 5, "produce", 7, 4, ("summer", "fall")),
    "peas": (125, 5, "produce", 7, 4, ("spring",)),
    "onion": (135, 5, "produce", 7, 4, ("spring", "fall")),
    "garlic": (145, 5, "produce", 8, 4, ("spring", "fall")),
    "celery": (150, 5, "produce", 8, 4, ("spring", "fall")),
    "strawberry": (175, 6, "produce", 8, 4, ("spring", "summer")),
    "blueberries": (190, 6, "produce", 8, 4, ("summer",)),
    "raspberries": (205, 6, "produce", 9, 4, ("summer", "fall")),
    "blackberries": (220, 6, "produce", 9, 4, ("summer", "fall")),
    "blackcurrants": (235, 6, "produce", 9, 4, ("summer",)),
    "bell_pepper": (250, 6, "produce", 9, 4, ("summer",)),
    "chili_pepper": (260, 6, "produce", 10, 4, ("summer",)),
    "eggplant": (275, 6, "produce", 10, 4, ("summer",)),
    "zucchini": (290, 6, "produce", 10, 4, ("summer", "fall")),
    "pumpkin": (300, 6, "produce", 10, 5, ("fall",)),
    "cauliflower": (350, 8, "produce", 11, 4, ("spring", "fall")),
    "artichoke": (375, 8, "produce", 11, 5, ("spring", "fall")),
    "sweet_potato": (400, 8, "produce", 12, 5, ("summer", "fall")),
    "yam": (425, 8, "produce", 12, 5, ("summer", "fall")),
    "grapes": (450, 8, "produce", 13, 5, ("summer", "fall")),
    "watermelon": (475, 8, "produce", 13, 5, ("summer",)),
}


if set(_CROP_PROGRESSION) != set(CROP_ASSETS):
    missing = sorted(set(CROP_ASSETS) - set(_CROP_PROGRESSION))
    extra = sorted(set(_CROP_PROGRESSION) - set(CROP_ASSETS))
    raise ValueError(f"Crop progression catalog mismatch; missing={missing}, extra={extra}")


CROP_DEFINITIONS = {
    crop_id: CropDefinition(
        id=crop_id,
        display_name=crop_id.replace("_", " ").title(),
        unlock_at_farming_points=values[0],
        harvest_points=values[1],
        market_kind=values[2],
        seed_price=values[3],
        growth_days=values[4],
        seasons=tuple(values[5]),
    )
    for crop_id, values in _CROP_PROGRESSION.items()
}

# Harvested produce uses the dedicated fruit icon set in inventory, the
# hotbar, and collection effects. Closest visual matches cover crops that do
# not yet have their own fruiticons asset.
CROP_FRUIT_ICONS = {
    "artichoke": "Artichoke.png",
    "barley": "Wheat.png",
    "beetroot": "Beet.png",
    "bell_pepper": "Red Paprika.png",
    "blackberries": "Blackberry.png",
    "blackcurrants": "Blackberry.png",
    "blueberries": "Blueberry.png",
    "broccoli": "Broccoli.png",
    "cabbage": "Cabbage.png",
    "carrot": "Carrot.png",
    "cauliflower": "Cauliflower.png",
    "celery": "Asparagus.png",
    "chili_pepper": "Red Chilli.png",
    "corn": "Corn.png",
    "eggplant": "Eggplant.png",
    "garlic": "Garlic.png",
    "grapes": "Purple Grapes.png",
    "kale": "Spinach.png",
    "kidney_beans": "Hericot Beans.png",
    "lettuce": "Lettuce.png",
    "oats": "Wheat.png",
    "onion": "Onion.png",
    "peas": "Peas.png",
    "potato": "Potato.png",
    "pumpkin": "Pumpkin.png",
    "raspberries": "Raspberry.png",
    "rye": "Wheat.png",
    "spinach": "Spinach.png",
    "strawberry": "Strawberry.png",
    "sweet_potato": "Potato.png",
    "tomato": "Tomato.png",
    "turnip": "Radish.png",
    "watermelon": "Watermelon.png",
    "wheat": "Wheat.png",
    "yam": "Potato.png",
    "zucchini": "Cucumber.png",
}

STARTER_CROP_IDS = tuple(
    crop.id for crop in CROP_DEFINITIONS.values() if crop.starts_unlocked
)


def crop_definition(crop_id: str) -> CropDefinition | None:
    return CROP_DEFINITIONS.get(str(crop_id or "").strip().lower().replace(" ", "_"))


def is_crop_unlocked(crop_id: str, game_state=None, *, farming_points=None) -> bool:
    crop = crop_definition(crop_id)
    if crop is None:
        return False
    if farming_points is None:
        if game_state is None:
            farming_points = 0
        else:
            farming_points = game_state.progression.farming_points
    return int(farming_points) >= crop.unlock_at_farming_points


def unlocked_crop_ids(game_state=None, *, farming_points=None) -> tuple[str, ...]:
    return tuple(
        crop.id
        for crop in CROP_DEFINITIONS.values()
        if is_crop_unlocked(crop.id, game_state, farming_points=farming_points)
    )


def next_crop_unlocks(game_state=None, *, farming_points=None, limit=5):
    if farming_points is None:
        farming_points = (
            0 if game_state is None else game_state.progression.farming_points
        )
    locked = sorted(
        (
            crop
            for crop in CROP_DEFINITIONS.values()
            if crop.unlock_at_farming_points > int(farming_points)
        ),
        key=lambda crop: (crop.unlock_at_farming_points, crop.display_name),
    )
    return tuple(locked[: max(0, int(limit))])


def crop_seed_market_offers(market_kind: str):
    return tuple(
        (crop.id, crop.seed_price)
        for crop in CROP_DEFINITIONS.values()
        if crop.market_kind == market_kind
    )

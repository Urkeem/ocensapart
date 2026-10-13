"""Data-defined crafting and refining recipes with unlock conditions."""

from __future__ import annotations

from dataclasses import dataclass

from data.crops import CROP_DEFINITIONS


@dataclass(frozen=True)
class RecipeDefinition:
    id: str
    category: str
    output_id: str
    ingredients: dict[str, int]
    output_count: int = 1
    required_unlock: str | None = None
    required_farming_points: int = 0
    grants_unlock: str | None = None

    def is_unlocked(self, game_state=None) -> bool:
        if game_state is None:
            return self.required_unlock is None and self.required_farming_points <= 0
        return (
            (self.required_unlock is None or self.required_unlock in game_state.progression.unlocks)
            and game_state.progression.farming_points >= self.required_farming_points
        )


def _recipe(category, output_id, ingredients, **kwargs):
    return RecipeDefinition(
        id=f"{category}.{output_id}",
        category=category,
        output_id=output_id,
        ingredients=dict(ingredients),
        **kwargs,
    )


_BASE_RECIPES = (
    _recipe("tools", "axe", {"wood": 3, "iron": 2}),
    _recipe("tools", "hoe", {"wood": 2, "rock": 1}),
    _recipe("tools", "water", {"wood": 2, "shell": 1}),
    _recipe("tools", "pickaxe", {"wood": 3, "rock": 4}),
    _recipe("tools", "shovel", {"wood": 2, "rock": 2}),
    _recipe("tools", "fishing rod", {"wood": 3, "shell": 2}),
    _recipe("weapons", "sword", {"wood": 2, "iron": 4}, required_unlock="recipes.refined_equipment"),
    _recipe("weapons", "bow", {"wood": 4, "shell": 1}),
    _recipe("weapons", "spear", {"wood": 3, "rock": 2}),
    _recipe("weapons", "shield", {"wood": 4, "iron": 2}, required_unlock="recipes.refined_equipment"),
    _recipe("resources", "iron", {"iron_ore": 2, "coal_ore": 1}, grants_unlock="recipes.refined_equipment"),
    _recipe("resources", "fence", {"wood": 2}),
    _recipe("resources", "crate", {"wood": 4}),
    _recipe("resources", "wheelbarrow", {"wood": 6, "iron": 2}),
    _recipe("resources", "hay", {"weed": 3}),
    _recipe(
        "story",
        "temporary_medicine",
        {"corn": 2, "tomato": 2, "weed": 1},
        required_unlock="recipes.temporary_medicine",
    ),
    _recipe(
        "story",
        "royal_medicine",
        {"corn": 3, "tomato": 3, "shell": 1},
        required_unlock="recipes.royal_medicine",
    ),
    _recipe(
        "story",
        "last_cure",
        {"potion_of_life": 1, "potion_of_memory": 1, "potion_of_vigor": 1},
        required_unlock="recipes.last_cure",
    ),
)

RECIPES = {recipe.id: recipe for recipe in _BASE_RECIPES}
for _crop_id, _crop in CROP_DEFINITIONS.items():
    _seed_recipe = _recipe(
        "seeds",
        _crop_id,
        {_crop_id: 1},
        output_count=3,
        required_farming_points=_crop.unlock_at_farming_points,
    )
    RECIPES[_seed_recipe.id] = _seed_recipe


def recipes_for_category(category: str, game_state=None) -> tuple[RecipeDefinition, ...]:
    return tuple(
        recipe
        for recipe in RECIPES.values()
        if recipe.category == category and recipe.is_unlocked(game_state)
    )


def recipe_for(category: str, output_id: str) -> RecipeDefinition | None:
    return RECIPES.get(f"{category}.{output_id}")

"""Stable gameplay item definitions independent of authored filenames."""

from __future__ import annotations

from dataclasses import dataclass


TEMPERATE_TREE_FRUITS = (
    ("golden_apple", "Golden Apple", 10),
    ("green_apple", "Green Apple", 9),
    ("red_apple", "Red Apple", 10),
    ("orange", "Orange", 9),
    ("green_fig", "Green Fig", 8),
    ("purple_fig", "Purple Fig", 8),
    ("black_grapes", "Black Grapes", 7),
    ("green_grapes", "Green Grapes", 7),
    ("purple_grapes", "Purple Grapes", 7),
    ("yellow_grapes", "Yellow Grapes", 7),
)
TROPICAL_TREE_FRUITS = (
    ("cocoa_beans", "Cocoa Beans", 6),
    ("avocado", "Avocado", 12),
    ("mango", "Mango", 10),
    ("melon", "Melon", 9),
    ("pear", "Pear", 9),
)
PALM_TREE_FRUITS = (("coconut", "Coconut", 12),)
TREE_FRUITS = TEMPERATE_TREE_FRUITS + TROPICAL_TREE_FRUITS + PALM_TREE_FRUITS
TREE_FRUIT_IDS = frozenset(item_id for item_id, _display_name, _stamina in TREE_FRUITS)
TREE_FRUIT_STAMINA = {
    item_id: stamina
    for item_id, _display_name, stamina in TREE_FRUITS
}


@dataclass(frozen=True)
class ItemDefinition:
    id: str
    display_name: str
    icon_path: str | None = None
    stack_size: int = 50
    tags: tuple[str, ...] = ()
    value: int = 0
    gift_category: str | None = None
    recipe_uses: tuple[str, ...] = ()


def _item(item_id, *, icon=None, tags=(), value=0, gift=None, uses=(), stack=50):
    return ItemDefinition(
        id=item_id,
        display_name=item_id.replace("_", " ").title(),
        icon_path=icon,
        stack_size=stack,
        tags=tuple(tags),
        value=value,
        gift_category=gift,
        recipe_uses=tuple(uses),
    )


ITEM_DEFINITIONS = {
    item.id: item
    for item in (
        _item("rock", icon="graphics/sprites/icons/rock.png", tags=("resource",), value=1, uses=("tools.hoe", "tools.pickaxe", "tools.shovel", "weapons.spear")),
        _item("wood", icon="graphics/sprites/icons/wood.png", tags=("resource",), value=1),
        _item("shell", icon="graphics/sprites/icons/shell.png", tags=("resource", "gift"), value=2, gift="curiosity"),
        _item("weed", icon="graphics/sprites/icons/weed.png", tags=("resource",), value=1, uses=("resources.hay",)),
        _item("coal_ore", icon="graphics/sprites/icons/coal.png", tags=("raw_ore", "resource"), value=4, uses=("resources.iron",)),
        _item("iron_ore", icon="graphics/sprites/icons/iron.png", tags=("raw_ore", "resource"), value=6, uses=("resources.iron",)),
        _item("iron", icon="graphics/sprites/icons/iron.png", tags=("refined", "resource"), value=16, uses=("tools.axe", "weapons.sword", "weapons.shield", "resources.wheelbarrow")),
        _item("gold_ore", icon="graphics/sprites/icons/gold.png", tags=("raw_ore", "rare", "gift"), value=30, gift="mineral"),
        _item("diamond_ore", icon="graphics/sprites/icons/diamond.png", tags=("raw_ore", "rare", "gift"), value=80, gift="gem"),
        _item("ruby_ore", icon="graphics/sprites/icons/ruby.png", tags=("raw_ore", "rare", "gift"), value=65, gift="gem"),
        _item("blue_sapphire_ore", icon="graphics/sprites/icons/blueSaphire.png", tags=("raw_ore", "rare", "gift"), value=65, gift="gem"),
        _item("health_potion", icon="graphics/sprites/items/health_portion.png", tags=("consumable", "potion"), value=30, stack=10),
        _item("stamina_potion", icon="graphics/sprites/items/stamina_portion.png", tags=("consumable", "potion"), value=25, stack=10),
        _item("axe", icon="graphics/sprites/icons/axe.png", tags=("equipment", "tool"), stack=1),
        _item("hoe", icon="graphics/sprites/icons/hoe.png", tags=("equipment", "tool"), stack=1),
        _item("water", icon="graphics/sprites/icons/watering_can.png", tags=("equipment", "tool"), stack=1),
        _item("pickaxe", icon="graphics/sprites/icons/pickaxe.png", tags=("equipment", "tool"), stack=1),
        _item("shovel", icon="graphics/sprites/icons/shovel.png", tags=("equipment", "tool"), stack=1),
        _item("fishing_rod", icon="graphics/sprites/icons/fishing_rod.png", tags=("equipment", "tool"), stack=1),
        _item("sword", icon="graphics/sprites/icons/sword.png", tags=("equipment", "weapon"), stack=1),
        _item("spear", icon="graphics/sprites/icons/spear.png", tags=("equipment", "weapon"), stack=1),
        _item("shield", icon="graphics/sprites/icons/shield.png", tags=("equipment", "weapon"), stack=1),
        _item("hollow_crypt_key", icon="graphics/sprites/items/story/key.png", tags=("story", "key"), stack=1),
        _item("ironveil_key", icon="graphics/sprites/items/story/key.png", tags=("story", "key"), stack=1),
        _item("royal_tiara", icon="graphics/sprites/items/story/tiara.png", tags=("story", "quest_item"), stack=1),
        _item("kingdom_map", icon="graphics/sprites/items/scroll.png", tags=("story", "map"), stack=1),
        _item("temporary_medicine", icon="graphics/sprites/items/health_portion.png", tags=("story", "medicine"), stack=5),
        _item("royal_medicine", icon="graphics/sprites/items/health_portion.png", tags=("story", "medicine"), stack=5),
        _item("potion_of_life", icon="graphics/sprites/items/health_portion.png", tags=("story", "potion"), stack=1),
        _item("potion_of_memory", icon="graphics/sprites/items/stamina_portion.png", tags=("story", "potion"), stack=1),
        _item("potion_of_vigor", icon="graphics/sprites/items/stamina_portion.png", tags=("story", "potion"), stack=1),
        _item("last_cure", icon="graphics/sprites/items/health_portion.png", tags=("story", "cure"), stack=1),
        _item("cured_seed_bag", icon="graphics/sprites/items/scroll.png", tags=("story", "seed_bag"), stack=10),
    )
}

for _fruit_id, _fruit_name, _stamina in TREE_FRUITS:
    ITEM_DEFINITIONS[_fruit_id] = _item(
        _fruit_id,
        icon=f"graphics/sprites/fruiticons/{_fruit_name}.png",
        tags=("food", "edible", "tree_fruit"),
        value=max(2, _stamina // 2),
    )


def item_definition(item_id: str) -> ItemDefinition | None:
    return ITEM_DEFINITIONS.get(str(item_id or "").strip().lower().replace(" ", "_"))


def item_stack_size(item_id: str) -> int:
    definition = item_definition(item_id)
    return definition.stack_size if definition is not None else 50

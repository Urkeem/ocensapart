"""Inventory item definitions shared by pickups, crafting, and placement."""


ITEM_DEFINITIONS = {
    "axe": {"max_durability": 40},
    "hoe": {"max_durability": 50},
    "water": {"max_durability": 60},
    "watering can": {"max_durability": 60},
    "fishing rod": {"max_durability": 40},
    "pickaxe": {"max_durability": 45},
    "shovel": {"max_durability": 45},
    "fence": {"place": True, "placement_type": "fence"},
    "crate": {"place": True, "placement_type": "crate"},
    "hay": {"place": True, "placement_type": "hay"},
    "wheelbarrow": {"place": True, "placement_type": "wheelbarrow"},
}


def normalize_item_name(name):
    return str(name or "").strip().lower().replace("_", " ")


class Item_System:
    def __init__(self):
        self.item_life = {
            name: definition.get("max_durability", 0)
            for name, definition in ITEM_DEFINITIONS.items()
        }

    def return_item_life(self, item):
        return self.item_life.get(normalize_item_name(item), 0)


class Item:
    def __init__(
        self,
        name="",
        image="",
        can_craft=False,
        cr_p="",
        *,
        place=None,
        placement_type=None,
        durability=None,
        max_durability=None,
    ):
        self.name = name
        self.image = image
        self.item_system = Item_System()
        self.is_craft_item = can_craft
        self.craft_product = cr_p

        definition = ITEM_DEFINITIONS.get(normalize_item_name(name), {})
        self.place = definition.get("place", False) if place is None else bool(place)
        self.placement_type = (
            definition.get("placement_type")
            if placement_type is None
            else placement_type
        )
        configured_max = definition.get("max_durability", 0)
        self.max_durability = int(
            configured_max if max_durability is None else max_durability
        )
        self.durability = int(
            self.max_durability if durability is None else durability
        )
        # Keep the original attribute available for older callers.
        self.lifetime = self.durability

    def copy(self):
        return Item(
            self.name,
            self.image,
            self.is_craft_item,
            self.craft_product,
            place=self.place,
            placement_type=self.placement_type,
            durability=self.durability,
            max_durability=self.max_durability,
        )

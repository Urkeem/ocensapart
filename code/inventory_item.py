"""Simple inventory item types used by the inventory UI and player inventory."""


class Item_System:
    def __init__(self):
        self.item_life = {
            "Axe": 10, "Hoe": 30
        }
        pass

    def return_item_life(self, item):
        for key, value in self.item_life.items():
            if item == key:
                return value
            else:
                return 0 # all craft materials are one time use.


class Item:
    def __init__(self, name="", image="", can_craft=False, cr_p=''):
        self.name = name
        self.image = image  # the image passed in is already loaded.
        self.item_system = Item_System()
        self.is_craft_item = can_craft
        self.craft_product = cr_p
        self.lifetime = self.item_system.return_item_life(self.name)  # set if craft product
        pass

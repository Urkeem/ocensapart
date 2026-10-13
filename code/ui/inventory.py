"""Inventory data structures and Pygame UI widgets for item management."""

import pygame
from inventory_item import *
from assets import LoadAssets
from utils import rp
from data.content_manifest import CROP_ASSETS, ITEM_ASSETS, normalize_content_id
from data.crafting import RECIPES, recipe_for, recipes_for_category
from data.items import TREE_FRUIT_IDS, item_definition, item_stack_size
from data.crops import CROP_FRUIT_ICONS
from gameplay.crafting import CraftingService


_ICON_CACHE = {}
MAX_STACK_SIZE = 50


def normalize_item_name(name):
    return name.lower().replace(" ", "_")


def canonical_item_name(name):
    """Keep fish identity stable while accepting old display-name saves."""
    try:
        from gameplay.fishing import fish_species

        species = fish_species(name)
        if species is not None:
            return species.id
    except (ImportError, AttributeError):
        pass
    normalized = normalize_content_id(name)
    if normalized in TREE_FRUIT_IDS:
        return normalized
    return name


def display_item_name(name):
    try:
        from gameplay.fishing import fish_species

        species = fish_species(name)
        if species is not None:
            return species.name
    except (ImportError, AttributeError):
        pass
    definition = item_definition(name)
    return definition.display_name if definition is not None else str(name).replace("_", " ").title()


def load_item_icon(name, size=(32, 32)):
    if not name:
        return ""

    normalized_name = normalize_item_name(name)
    icon_name = "weed" if normalized_name == "bush" else normalized_name
    key = (icon_name, size)
    cached = _ICON_CACHE.get(key)
    if cached is not None:
        return cached

    try:
        from gameplay.fishing import fish_species, load_fish_icon

        species = fish_species(name)
        if species is not None:
            image = load_fish_icon(species, size)
            _ICON_CACHE[key] = image
            return image
    except (FileNotFoundError, ValueError, pygame.error):
        pass

    item_spec = ITEM_ASSETS.get(normalize_content_id(name))
    if item_spec is not None and item_spec.role != "points_effect":
        try:
            sheet = pygame.image.load(rp(*item_spec.sheet.path.split("/"))).convert_alpha()
            frame = sheet.subsurface(item_spec.sheet.frame_rects()[0]).copy()
            image = pygame.transform.scale(frame, size)
            _ICON_CACHE[key] = image
            return image
        except (FileNotFoundError, ValueError, pygame.error):
            pass

    item_data = item_definition(name)
    if item_data is not None and item_data.icon_path:
        try:
            image = pygame.image.load(rp(*item_data.icon_path.split("/"))).convert_alpha()
            image = pygame.transform.scale(image, size)
            _ICON_CACHE[key] = image
            return image
        except (FileNotFoundError, pygame.error):
            pass

    fruit_icon = CROP_FRUIT_ICONS.get(normalize_content_id(name))
    if fruit_icon is not None:
        try:
            image = pygame.image.load(
                rp("graphics", "sprites", "fruiticons", fruit_icon)
            ).convert_alpha()
            image = pygame.transform.scale(image, size)
            _ICON_CACHE[key] = image
            return image
        except (FileNotFoundError, pygame.error):
            pass

    candidates = [
        f"{icon_name}.png",
        f"{name}.png",
        f"{name.title().replace(' ', '_')}.png",
        f"{name.title().replace(' ', '')}.png",
    ]
    if normalized_name == "water":
        candidates.insert(0, "watering_can.png")
    if "apple" in name.lower():
        candidates.append("apple.png")

    icon_folders = (
        ("graphics", "sprites", "icons"),
        ("graphics", "icons"),
    )
    for filename in candidates:
        for folder in icon_folders:
            try:
                image = pygame.image.load(rp(*folder, filename)).convert_alpha()
                image = pygame.transform.scale(image, size)
                _ICON_CACHE[key] = image
                return image
            except (FileNotFoundError, pygame.error):
                continue

    try:
        crop_spec = CROP_ASSETS.get(normalize_content_id(name))
        crop_path = (
            crop_spec.path
            if crop_spec is not None
            else f"graphics/sprites/environment/crops/{icon_name}.png"
        )
        crop_sheet = pygame.image.load(
            rp(*crop_path.split("/"))
        ).convert_alpha()
        frame = crop_sheet.subsurface((16, 16, 16, 16)).copy()
        image = pygame.transform.scale(frame, size)
        _ICON_CACHE[key] = image
        return image
    except (FileNotFoundError, ValueError, pygame.error):
        pass

    _ICON_CACHE[key] = ""
    return ""


class Inventory:
    def __init__(self, size):
        self.assets = LoadAssets()
        self.size = size
        self.slots = [Slot() for _ in range(self.size)]  # create the slots
        self.is_inv = False
        self.craft_system = Craft_System()
        self.crafted_counts = {}
        self.selected_item_name = None
        self.hotbar_item_name = None
        pass

    def add_item_to_slot(self, item: Item, amount=1):
        """
        This is function create an empty slots array to keep track of the empty slots.
        Check if an item can be stacked > if true add it to the same slot else add it to an empty one.
        :param item:
        :return:
        """
        amount = max(0, int(amount))
        if amount == 0:
            return True
        item.name = canonical_item_name(item.name)
        stack_limit = item_stack_size(item.name)
        stackable_slots = [
            slot
            for slot in self.slots
            if slot.item.name == item.name and slot.amount < stack_limit
        ]
        empty_slots = [slot for slot in self.slots if slot.item.name == ""]
        capacity = sum(stack_limit - slot.amount for slot in stackable_slots)
        capacity += len(empty_slots) * stack_limit
        if capacity < amount:
            return False

        remaining = amount
        for slot in stackable_slots:
            added = min(remaining, stack_limit - slot.amount)
            slot.add_item(item, added)
            remaining -= added
            if remaining == 0:
                return True
        for slot in empty_slots:
            added = min(remaining, stack_limit)
            slot.add_item(item, added)
            remaining -= added
            if remaining == 0:
                return True
        return True

    def can_add_item(self, item_name, amount=1):
        item_name = canonical_item_name(item_name)
        stack_limit = item_stack_size(item_name)
        capacity = sum(
            stack_limit - slot.amount
            for slot in self.slots
            if slot.item.name == item_name and slot.amount < stack_limit
        )
        capacity += sum(slot.item.name == "" for slot in self.slots) * stack_limit
        return capacity >= max(0, int(amount))

    def count_item(self, item_name):
        item_name = canonical_item_name(item_name)
        return sum(
            slot.amount
            for slot in self.slots
            if canonical_item_name(slot.item.name) == item_name
        )

    def find_slot(self, item_name):
        item_name = canonical_item_name(item_name)
        for slot in self.slots:
            if canonical_item_name(slot.item.name) == item_name and slot.amount > 0:
                return slot
        return None

    def remove_item_count(self, item_name, amount=1):
        item_name = canonical_item_name(item_name)
        if self.count_item(item_name) < amount:
            return False
        remaining = amount
        for slot in self.slots:
            if canonical_item_name(slot.item.name) != item_name or slot.amount <= 0:
                continue
            removed = min(slot.amount, remaining)
            slot.amount -= removed
            remaining -= removed
            if slot.amount <= 0:
                slot.remove_item(slot.item)
            if remaining <= 0:
                if self.count_item(item_name) <= 0 and self.selected_item_name == item_name:
                    self.selected_item_name = None
                return True
        return False

    def select_placeable(self, item_name):
        slot = self.find_slot(item_name)
        if slot is None or not slot.item.place:
            return False
        self.selected_item_name = (
            None if self.selected_item_name == slot.item.name else slot.item.name
        )
        return True

    def get_selected_placeable(self):
        if not self.selected_item_name:
            return None
        slot = self.find_slot(self.selected_item_name)
        if slot is None or not slot.item.place:
            self.selected_item_name = None
            return None
        return slot.item

    def add_crafted_item(self, item_name, amount=1):
        self.crafted_counts[item_name] = self.crafted_counts.get(item_name, 0) + amount

    def get_crafted_count(self, item_name):
        return self.crafted_counts.get(item_name, 0)

    def swap_items(self):
        """
        Check if the inventory is opened
        click and grab an item in a slot
        move it to another slot
        :return:
        """
        pass

    def use_items(self):
        pass


class Slot:
    def __init__(self):
        self.assets = LoadAssets()
        self.amount = 0
        self.position = ()
        self.slot_width = 66
        self.occupied_image = self.assets.all_sprite_sheet.get_sprite(*self.assets.sprite_data["slot"])
        self.occupied_image = pygame.transform.scale(self.occupied_image, (64, 64))
        self.empty_image = self.assets.all_sprite_sheet.get_sprite(*self.assets.sprite_data["slot"])
        self.empty_image = pygame.transform.scale(self.empty_image, (64, 64))
        self.hover_image = pygame.image.load(
            rp("graphics", "game_ui", "selector", "s32.png")
        ).convert_alpha()
        self.hover_image = pygame.transform.scale(self.hover_image, (64, 64))
        self.item = Item("", "")  # each slot has item instance in it.
        self.rect = pygame.Rect(0 , 0, self.occupied_image.get_width(), self.occupied_image.get_height())

    def add_item(self, item, amount=1):
        """
        This function is called when there is need to add an item to the inventory.
        Here, check the slot if is empty that is the item name and image are empty string:
        if true: assign the item image and name to the item.

        """
        if self.amount <= 0 or not self.item.name:
            self.item = item.copy()
            self.item.image = load_item_icon(item.name) or item.image
        self.amount = min(item_stack_size(item.name), self.amount + max(0, int(amount)))
        # print(f"{item.name} was added to the inventory")
        pass

    def place_item_to_slot(self, item: Item, amount: int):
        self.item = item.copy()
        self.item.image = load_item_icon(item.name) or item.image
        self.amount = min(item_stack_size(item.name), max(0, int(amount)))

        pass

    def remove_item(self, item: Item):
        if self.item.name == item.name:  # Check the item being removed.
            self.item = Item("", "")
            self.amount = 0
        pass

    def is_clicked(self, mouse_pos):
        if mouse_pos[0] == 1:
            return self.rect.collidepoint(mouse_pos[1])


class Inventory_UI:
    def __init__(self, inv, screen, position, player=None):
        self.screen = screen

        self.inventory = inv
        self.player = player
        self.slot_ui = Slot_UI(inv)
        self.slot_width = 66  # Assuming each slot is 66 pixels wide
        self.font = pygame.font.Font(rp("font", "LycheeSoda.ttf"), 24)
        self.small_font = pygame.font.Font(rp("font", "LycheeSoda.ttf"), 18)
        self.panel_color = (16, 22, 34)
        self.panel_alt = (28, 37, 54)
        self.accent = (76, 145, 201)
        self.gold = (209, 177, 87)
        self.text_color = (236, 240, 245)

        self.inv_panel = pygame.Rect(0, 0, 390, 330)
        self.craft_panel = pygame.Rect(0, 0, 350, 330)
        self.category_panel = pygame.Rect(0, 0, 145, 330)
        total_width = self.inv_panel.width + self.craft_panel.width + self.category_panel.width + 28
        total_height = self.inv_panel.height
        self.position = (position[0] - total_width // 2, position[1] - total_height // 2)
        self.inv_panel.topleft = self.position
        self.craft_panel.topleft = (self.inv_panel.right + 12, self.position[1])
        self.category_panel.topleft = (self.craft_panel.right + 12, self.position[1])

        self.grabbing = False
        self.category = self.inventory.craft_system.get_categories()[0]
        self.selected_craft_item = None
        self.craft_page = 0
        self.category_buttons = {}
        self.craft_item_buttons = []
        self.resource_buttons = []
        self.page_buttons = {}
        self.craft_button = None
        self.resource_allocations = {}
        self.controller_focus_index = 0

    def display_inventory(self):
        """
        This function displays what ever is in the inventory it mostly handles the ui.
        :return:
        """
        self.draw_panel(self.inv_panel, "Inventory")
        hint = self.small_font.render(
            "Click: equip/select   Right-click: eat",
            True,
            (170, 184, 202),
        )
        self.screen.blit(hint, hint.get_rect(topright=(self.inv_panel.right - 12, self.inv_panel.y + 16)))
        self.slot_ui.display_slots(
            self.screen,
            (self.inv_panel.x + 12, self.inv_panel.y + 44),
            self.slot_width,
        )
        self.display_craft_panel()
        self.display_category_panel()
        self.draw_controller_focus()

    def get_controller_targets(self):
        targets = [slot.rect for slot in self.slot_ui.slots if slot.rect.width > 0]
        targets.extend(rect for rect, _ in self.craft_item_buttons)
        targets.extend(rect for rect, _, _ in self.resource_buttons)
        targets.extend(self.category_buttons.values())
        targets.extend(self.page_buttons.values())
        if self.craft_button is not None:
            targets.append(self.craft_button)
        return targets

    def draw_controller_focus(self):
        targets = self.get_controller_targets()
        if not targets:
            return
        self.controller_focus_index %= len(targets)
        pygame.draw.rect(
            self.screen,
            self.gold,
            targets[self.controller_focus_index].inflate(5, 5),
            3,
            border_radius=8,
        )

    def focused_inventory_food(self):
        """Return edible produce only when an inventory slot has focus.

        Crafting targets, including seed recipes, deliberately do not count as
        food even when their crop id matches an edible harvested crop.
        """
        if self.player is None:
            return None
        targets = self.get_controller_targets()
        inventory_slots = [slot for slot in self.slot_ui.slots if slot.rect.width > 0]
        if not targets or not inventory_slots:
            return None
        self.controller_focus_index %= len(targets)
        if self.controller_focus_index >= len(inventory_slots):
            return None
        return self.player.inventory_food_name(
            inventory_slots[self.controller_focus_index].item.name
        )

    def handle_controller_button(self, button):
        from gameplay.controls import (
            BUTTON_CONFIRM,
            BUTTON_DPAD_DOWN,
            BUTTON_DPAD_LEFT,
            BUTTON_DPAD_RIGHT,
            BUTTON_DPAD_UP,
        )

        targets = self.get_controller_targets()
        if not targets:
            return False
        self.controller_focus_index %= len(targets)

        if button == BUTTON_CONFIRM:
            self.handle_click((1, targets[self.controller_focus_index].center))
            return True

        directions = {
            BUTTON_DPAD_LEFT: pygame.Vector2(-1, 0),
            BUTTON_DPAD_RIGHT: pygame.Vector2(1, 0),
            BUTTON_DPAD_UP: pygame.Vector2(0, -1),
            BUTTON_DPAD_DOWN: pygame.Vector2(0, 1),
        }
        direction = directions.get(button)
        if direction is None:
            return False

        origin = pygame.Vector2(targets[self.controller_focus_index].center)
        best_index = None
        best_score = None
        for index, target in enumerate(targets):
            if index == self.controller_focus_index:
                continue
            offset = pygame.Vector2(target.center) - origin
            forward = offset.dot(direction)
            if forward <= 0:
                continue
            sideways = abs(offset.cross(direction))
            score = forward + sideways * 1.8
            if best_score is None or score < best_score:
                best_score = score
                best_index = index

        if best_index is not None:
            self.controller_focus_index = best_index
            return True
        return False

    def draw_panel(self, rect, title):
        pygame.draw.rect(self.screen, self.panel_color, rect, border_radius=10)
        pygame.draw.rect(self.screen, self.panel_alt, rect, 2, border_radius=10)
        text = self.font.render(title, True, self.text_color)
        self.screen.blit(text, (rect.x + 14, rect.y + 12))

    def draw_button(self, rect, label, selected=False):
        fill = self.accent if selected else self.panel_alt
        pygame.draw.rect(self.screen, fill, rect, border_radius=8)
        pygame.draw.rect(self.screen, self.gold if selected else (70, 86, 110), rect, 2, border_radius=8)
        color = (10, 15, 24) if selected else self.text_color
        text = self.small_font.render(label.title(), True, color)
        self.screen.blit(text, text.get_rect(center=rect.center))

    def draw_slot_surface(self, rect, item_name="", count_text="", selected=False):
        slot_image = self.inventory.slots[0].occupied_image if selected or item_name else self.inventory.slots[0].empty_image
        # slot_image = pygame.transform.scale(slot_image, rect.size)
        self.screen.blit(slot_image, slot_image.get_rect(center=rect.center))
        #if selected:
            # pygame.draw.rect(self.screen, self.gold, rect, 2, border_radius=6)

        image = self.get_inventory_image(item_name)
        if image:
            self.screen.blit(image, image.get_rect(center=rect.center))

        if count_text:
            text = self.small_font.render(str(count_text), True, self.text_color)
            self.screen.blit(text, text.get_rect(bottomright=(rect.right - 4, rect.bottom - 3)))

    def get_inventory_image(self, item_name):
        for slot in self.inventory.slots:
            if slot.item.name == item_name and slot.item.image:
                return slot.item.image
        image = load_item_icon(item_name)
        if image:
            return image
        try:
            image = pygame.image.load(rp("graphics", "overlay", f"{item_name}.png")).convert_alpha()
            return pygame.transform.scale(image, (32, 32))
        except (FileNotFoundError, pygame.error):
            return None

    def consume_resource(self, resource):
        if self.inventory.remove_item_count(resource, 1):
            return True

        if self.player is not None and resource in self.player.seed_inventory:
            if self.player.seed_inventory[resource] <= 0:
                return False
            self.player.seed_inventory[resource] -= 1
            return True

        return False

    def can_craft_selected(self):
        if self.selected_craft_item is None:
            return False
        game_state = getattr(self.player, "game_state", None)
        recipe_definition = self.inventory.craft_system.get_recipe_definition(
            self.category,
            self.selected_craft_item,
        )
        if recipe_definition is None or not recipe_definition.is_unlocked(game_state):
            return False
        recipe = recipe_definition.ingredients
        if not recipe:
            return False
        return all(
            self.resource_allocations.get(resource, 0) >= required
            and self.available_resource_count(resource) >= required
            for resource, required in recipe.items()
        )

    def available_resource_count(self, resource):
        return CraftingService(
            self.inventory,
            self.player,
            getattr(self.player, "game_state", None),
        ).available_count(
            resource,
            include_seed_inventory=self.category != "seeds",
        )

    def craft_selected_item(self):
        """
        This function crafts the selected craft item.
        :return:
        """
        if not self.can_craft_selected():
            return False

        result = CraftingService(
            self.inventory,
            self.player,
            getattr(self.player, "game_state", None),
        ).craft(self.category, self.selected_craft_item)
        if result.success:
            self.resource_allocations = {}
            if self.category == "seeds" and self.player is not None:
                self.player.select_seed(result.item_id)
        return result.success

    def draw_item_label(self, rect, item_name, selected=False):
        crafted = self.inventory.get_crafted_count(item_name)
        self.draw_slot_surface(rect, item_name, crafted if crafted else "", selected)
        label = self.small_font.render(display_item_name(item_name), True, self.text_color)
        self.screen.blit(label, label.get_rect(midtop=(rect.centerx, rect.bottom + 2)))

    def display_craft_panel(self):
        self.draw_panel(self.craft_panel, "Craft")
        self.craft_item_buttons = []
        self.resource_buttons = []
        self.page_buttons = {}
        self.craft_button = None

        items = self.inventory.craft_system.get_items(
            self.category,
            getattr(self.player, "game_state", None),
        )
        start = self.craft_page * 5
        visible_items = items[start:start + 5]
        top_rect = pygame.Rect(self.craft_panel.x + 14, self.craft_panel.y + 44, self.craft_panel.width - 28, 128)
        bottom_rect = pygame.Rect(self.craft_panel.x + 14, self.craft_panel.y + 194, self.craft_panel.width - 28, 112)
        pygame.draw.rect(self.screen, (12, 18, 29), top_rect, border_radius=8)
        pygame.draw.rect(self.screen, (12, 18, 29), bottom_rect, border_radius=8)

        for index, item_name in enumerate(visible_items):
            # craft item slots
            rect = pygame.Rect(top_rect.x + 12 + index * 66, top_rect.y + 12, 66, 66)
            self.draw_item_label(rect, item_name, selected=item_name == self.selected_craft_item)
            self.craft_item_buttons.append((rect, item_name))

        if start > 0:
            prev_rect = pygame.Rect(top_rect.x + 8, top_rect.bottom - 32, 70, 24)
            self.draw_button(prev_rect, "prev")
            self.page_buttons["prev"] = prev_rect
        if start + 5 < len(items):
            next_rect = pygame.Rect(top_rect.right - 78, top_rect.bottom - 32, 70, 24)
            self.draw_button(next_rect, "next")
            self.page_buttons["next"] = next_rect

        hint = self.small_font.render("Resources", True, self.text_color)
        self.screen.blit(hint, (bottom_rect.x + 10, bottom_rect.y + 8))
        if self.selected_craft_item is None:
            empty = self.small_font.render("Select an item above.", True, (170, 180, 190))
            self.screen.blit(empty, (bottom_rect.x + 10, bottom_rect.y + 40))
            return

        recipe = self.inventory.craft_system.get_recipe(self.category, self.selected_craft_item)
        for index, (resource, required) in enumerate(recipe.items()):
            # resource slots
            rect = pygame.Rect(bottom_rect.x + 4 + index * 66, bottom_rect.y + 32, 66, 66)  # 4 is padding
            allocated = self.resource_allocations.get(resource, 0)
            self.draw_slot_surface(rect, resource, f"{allocated}/{required}", allocated >= required)
            label = self.small_font.render(resource.title(), True, self.text_color)
            self.screen.blit(label, label.get_rect(midtop=(rect.centerx, rect.bottom + 2)))
            self.resource_buttons.append((rect, resource, required))

        can_craft = self.can_craft_selected()
        craft_rect = pygame.Rect(bottom_rect.right - 90, bottom_rect.bottom - 36, 78, 28)
        self.draw_button(craft_rect, "Craft", selected=can_craft)
        self.craft_button = craft_rect

    def display_category_panel(self):
        self.draw_panel(self.category_panel, "Category")
        self.category_buttons = {}
        for index, category in enumerate(self.inventory.craft_system.get_categories()):
            rect = pygame.Rect(self.category_panel.x + 14, self.category_panel.y + 50 + index * 48, self.category_panel.width - 28, 36)
            self.draw_button(rect, category, selected=category == self.category)
            self.category_buttons[category] = rect

    def handle_click(self, mouse_pos):
        """
        Click on the item, make a copy of it, delete it, pass it to the grabbed item variable, move it to an empty slot.
        :param mouse_pos:
        :return:
        """
        click_pos = mouse_pos[1]

        if mouse_pos[0] == 3:
            for slot in self.slot_ui.slots:
                if slot.rect.collidepoint(click_pos) and slot.item.name:
                    return self.player.consume_food(slot.item.name)
            return 0

        for category, rect in self.category_buttons.items():
            if rect.collidepoint(click_pos):
                self.category = category
                self.selected_craft_item = None
                self.craft_page = 0
                self.resource_allocations = {}
                return

        for direction, rect in self.page_buttons.items():
            if rect.collidepoint(click_pos):
                self.craft_page += 1 if direction == "next" else -1
                self.craft_page = max(0, self.craft_page)
                self.selected_craft_item = None
                self.resource_allocations = {}
                return

        for rect, item_name in self.craft_item_buttons:
            if rect.collidepoint(click_pos):
                self.selected_craft_item = item_name
                self.resource_allocations = {}
                if (
                    self.category == "seeds"
                    and self.player is not None
                    and self.player.seed_inventory.get(item_name, 0) > 0
                ):
                    self.player.select_seed(item_name)
                elif (
                    self.category in {"tools", "weapons"}
                    and self.player is not None
                    and self.player.is_tool_usable(item_name)
                ):
                    self.player.select_tool(item_name)
                return

        for rect, resource, required in self.resource_buttons:
            if rect.collidepoint(click_pos):
                if self.resource_allocations.get(resource, 0) >= required:
                    return
                if self.available_resource_count(resource) > self.resource_allocations.get(resource, 0):
                    self.resource_allocations[resource] = self.resource_allocations.get(resource, 0) + 1
                return

        if self.craft_button is not None and self.craft_button.collidepoint(click_pos):
            self.craft_selected_item()
            return

        if self.grabbing:
            """
            then add the grabbed item to a new empty slot else go ahead and grab the item
            """
            for i, slot in enumerate(self.slot_ui.slots):
                if slot.is_clicked(mouse_pos):
                    if slot.item.name != "":
                        # swap the items
                        temp_item = slot.item.copy()
                        temp_amount = slot.amount
                        slot.remove_item(slot.item)
                        slot.place_item_to_slot(self.grabbed_item, self.grabbed_amount)
                        self.grabbed_item = temp_item
                        self.grabbed_amount = temp_amount
                    else:
                        slot.place_item_to_slot(self.grabbed_item, self.grabbed_amount)
                        self.grabbing = False
                        self.grabbed_item.name = ""
                        self.grabbed_item.image = ""
                        self.grabbed_amount = 0
                    return
        else:
            for i, slot in enumerate(self.slot_ui.slots):
                if slot.is_clicked(mouse_pos):
                    if slot.item.name == "":
                        continue
                    if slot.item.place:
                        self.inventory.select_placeable(slot.item.name)
                        if self.inventory.get_selected_placeable() is not None:
                            self.inventory.is_inv = False
                        return
                    if self.player is not None and self.player.select_hotbar_item(slot.item.name):
                        return True
                    self.grabbed_item = slot.item.copy()
                    self.grabbed_amount = slot.amount
                    self.grabbing = True
                    slot.remove_item(slot.item)  # remove the item from the slot.
        return None

    def grab_item(self):
        """
        Click on the slot to grab its content.
        :return:
        """
        self.grabbed_item_rect = self.grabbed_item.image.get_rect()  # create the rect first
        controller_input = getattr(self.player, "controller_input", None)
        targets = self.get_controller_targets()
        if controller_input is not None and controller_input.connected and targets:
            self.controller_focus_index %= len(targets)
            self.grabbed_item_rect.center = targets[self.controller_focus_index].center
        else:
            # Update image position to follow the mouse.
            self.grabbed_item_rect.center = pygame.mouse.get_pos()

        # Draw the image at the updated position
        self.screen.blit(self.grabbed_item.image, self.grabbed_item_rect)

        pass


class Slot_UI:
    def __init__(self, inv):
        self.inventory = inv
        self.slots = self.inventory.slots  # grab the inventory slots.
        self.padding = 8
        self.columns = 5

    def display_slots(self, screen, position, slot_width):
        """
        This function displays what is in the slot that is the slot itself and the item in it.
        :param screen:
        :param position:
        :param slot_width:
        :return:
        """

        for index, slot in enumerate(self.slots):  # this iterates through the slots created in the inventory.
            row = index // self.columns
            col = index % self.columns
            slot.position = (position[0] + slot_width * col, position[1] + slot_width * row)

            # draw the slot and its contents
            if slot.item.name != "":
                screen.blit(slot.occupied_image, slot.position)
                self.display_item(screen, slot, slot.position, slot_width)
            else:
                screen.blit(slot.empty_image, slot.position)
            slot.rect = pygame.Rect(slot.position[0], slot.position[1], slot_width, slot_width)
            if (
                slot.item.name
                and slot.item.name == self.inventory.selected_item_name
            ):
                screen.blit(slot.hover_image, slot.hover_image.get_rect(center=slot.rect.center))
            if slot.item.name and slot.item.name == self.inventory.hotbar_item_name:
                screen.blit(slot.hover_image, slot.hover_image.get_rect(center=slot.rect.center))
            # pygame.draw.rect(screen, (255, 0, 0), slot.rect, 2)  # Red rectangle outline

    @staticmethod
    def display_item(screen, slot, slot_position, slot_w):
        """
        This function displays what item is in the slot.
        :param screen:
        :param slot:
        :param slot_position:
        :return:
        """
        if slot.item.image:
            image_rect = slot.item.image.get_rect(center=(slot_position[0] + slot_w * 0.5, slot_position[1] + slot_w * 0.5))
            screen.blit(slot.item.image, image_rect)
        font = pygame.font.Font(None, 24)
        text = font.render(str(slot.amount), True, (255, 255, 255))
        screen.blit(text, (slot_position[0] + slot_w*0.62, slot_position[1] + slot_w*0.58))
        pass


class Hot_bar:
    def __init__(self, inv):
        self.inv = inv
        self.hot_bar_size = 5
        self.hot_bar_slots = self.inv[:self.hot_bar_size]  # the first n inventory slots
        pass

    def update_hot_bar(self):
        pass


class Hot_Bar_UI:
    """Render the original five inventory slots as the bottom hotbar."""

    def __init__(self, inv, screen, position):
        self.screen = screen
        self.pos = position
        self.inventory = inv
        self.h_bar_slot_ui = Hot_Bar_Slot_UI(self.inventory)
        self.slot_width = 66
        background = self.inventory.assets.all_sprite_sheet.get_sprite(
            *self.inventory.assets.sprite_data["inv_bg"]
        )
        self.h_bar_image = pygame.transform.scale(
            background,
            (
                round(background.get_width() * 2.18),
                round(background.get_height() * 2),
            ),
        )
        inv_width = (5 * self.slot_width) + round(self.h_bar_slot_ui.padding * 1.6)
        self.position = (self.pos[0] - inv_width // 2, self.pos[1] - 64)

    def display_hot_bar(self):
        self.screen.blit(self.h_bar_image, self.position)
        self.h_bar_slot_ui.display_slots(self.screen, self.position, self.slot_width)

    def select_slot(self, index):
        if not 0 <= index < len(self.h_bar_slot_ui.hot_bar_slots):
            return
        slot = self.h_bar_slot_ui.hot_bar_slots[index]
        self.screen.blit(
            slot.hover_image,
            slot.hover_image.get_rect(center=slot.rect.center),
        )

    def slot_at(self, position):
        for index, slot in enumerate(self.h_bar_slot_ui.hot_bar_slots):
            if slot.rect.collidepoint(position):
                return index
        return None


class Hot_Bar_Slot_UI:
    def __init__(self, inv):
        self.inventory = inv
        self.hot_bar_size = 5
        self.hot_bar_slots = self.inventory.slots[:self.hot_bar_size]  # the first n inventory slots
        self.padding = 8

    def display_slots(self, screen, position, slot_width):
        """
        This function displays what is in the slot that is the slot itself and the item in it.
        :param screen:
        :param position:
        :param slot_width:
        :return:
        """

        for index, slot in enumerate(self.hot_bar_slots):  # this iterates through the slots created in the inventory.
            row = index // self.hot_bar_size
            col = index % self.hot_bar_size
            slot.position = (position[0] + slot_width*(-0.08+ col), position[1] + slot_width*(0.4+ row))
            slot.rect = pygame.Rect(slot.position[0], slot.position[1], slot_width, slot_width)

            if slot.item.name != "":
                screen.blit(slot.occupied_image, slot.position)
                self.display_item(screen, slot, slot.position, slot_width)
            else:
                screen.blit(slot.empty_image, slot.position)

    @staticmethod
    def display_item(screen, slot, slot_position, slot_w):
        """
        This function displays what item is in the slot.
        :param screen:
        :param slot:
        :param slot_position:
        :return:
        """
        if slot.item.image:
            image_rect = slot.item.image.get_rect(center=(slot_position[0] + slot_w * 0.5, slot_position[1] + slot_w * 0.5))
            screen.blit(slot.item.image, image_rect)
        font = pygame.font.Font(None, 24)
        text = font.render(str(slot.amount), True, (255, 255, 255))
        screen.blit(text, (slot_position[0] + slot_w * 0.8, slot_position[1] + slot_w * 0.6))
        pass


class Craft_System:
    def __init__(self):
        self.categories = {}
        for recipe in RECIPES.values():
            self.categories.setdefault(recipe.category, {})[recipe.output_id] = dict(recipe.ingredients)
        self.recipe = {
            item: ingredients
            for recipes in self.categories.values()
            for item, ingredients in recipes.items()
        }
        pass

    def return_craft_product(self, ingredient):
        for key, value in self.recipe.items():
            for k, v in value.items():
                if ingredient == k:
                    return key

    def get_categories(self):
        return list(self.categories.keys())

    def get_items(self, category, game_state=None):
        return [recipe.output_id for recipe in recipes_for_category(category, game_state)]

    def get_recipe(self, category, item):
        return self.categories.get(category, {}).get(item, {})

    @staticmethod
    def get_recipe_definition(category, item):
        return recipe_for(category, item)

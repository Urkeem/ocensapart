"""Explicit talk interaction and merchant shop dialogue."""

from __future__ import annotations

import pygame

from gameplay.controls import (
    BUTTON_CANCEL,
    BUTTON_CONFIRM,
    BUTTON_DPAD_DOWN,
    BUTTON_DPAD_UP,
)
from inventory_item import Item
from ui.inventory import load_item_icon
from utils import rp


class MerchantDialogue:
    def __init__(self, screen, player, npc_manager=None):
        self.screen = screen
        self.player = player
        self.npc_manager = npc_manager
        self.merchant = None
        self.selected = 0
        self.message = ""
        self.message_timer = 0.0
        self.font = pygame.font.Font(rp("font", "LycheeSoda.ttf"), 25)
        self.small_font = pygame.font.Font(rp("font", "LycheeSoda.ttf"), 19)
        width, height = screen.get_size()
        self.panel = pygame.Rect(0, 0, min(600, width - 40), min(430, height - 40))
        self.panel.center = (width // 2, height // 2)
        self.offer_rects = []
        self.offer_start = 0

    @property
    def active(self):
        return self.merchant is not None

    def set_npc_manager(self, npc_manager):
        self.npc_manager = npc_manager

    def _offers(self):
        if self.merchant is None:
            return []
        available = getattr(self.merchant, "available_offers", None)
        return available() if available is not None else self.merchant.offers

    def open(self, merchant):
        if merchant is None or not merchant.is_available:
            return False
        self.player.inventory.is_inv = False
        self.player.dialogue_active = True
        self.merchant = merchant
        self.selected = 0
        self.message = f"Welcome! Here is today's {merchant.stall.stall_kind.replace('_', ' ')} stock."
        self.message_timer = 3.0
        return True

    def close(self):
        self.merchant = None
        self.player.dialogue_active = False

    def try_open_near_player(self):
        if self.npc_manager is None:
            return False
        return self.open(self.npc_manager.find_talk_target(self.player))

    def purchase_selected(self):
        if not self.active or not self.merchant.is_available:
            self.close()
            return False
        offers = self._offers()
        if not offers:
            self.message = "No unlocked stock is available yet."
            self.message_timer = 2.5
            return False
        offer = offers[self.selected % len(offers)]
        if offer["stock"] <= 0:
            self.message = "That item is sold out."
            self.message_timer = 2.5
            return False
        price = offer["price"]
        if self.player.coins < price:
            self.message = f"You need {price} coins."
            self.message_timer = 2.5
            return False
        if offer.get("seed"):
            self.player.seed_inventory[offer["item"]] = (
                self.player.seed_inventory.get(offer["item"], 0) + 1
            )
        elif not self.player.inventory.add_item_to_slot(Item(offer["item"]), 1):
            self.message = "Your inventory is full."
            self.message_timer = 2.5
            return False
        self.player.spend_coins(price)
        offer["stock"] -= 1
        item_label = offer["item"].replace("_", " ").title()
        if offer.get("seed"):
            item_label += " Seeds"
        self.message = f"Bought {item_label} for {price} coins."
        self.message_timer = 2.5
        return True

    def handle_event(self, event):
        if not self.active:
            return False
        offers = self._offers()
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_ESCAPE, pygame.K_e):
                self.close()
            elif offers and event.key in (pygame.K_UP, pygame.K_w):
                self.selected = (self.selected - 1) % len(offers)
            elif offers and event.key in (pygame.K_DOWN, pygame.K_s):
                self.selected = (self.selected + 1) % len(offers)
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                self.purchase_selected()
            return True
        if event.type == pygame.CONTROLLERBUTTONDOWN:
            if event.button == BUTTON_CANCEL:
                self.close()
            elif offers and event.button == BUTTON_DPAD_UP:
                self.selected = (self.selected - 1) % len(offers)
            elif offers and event.button == BUTTON_DPAD_DOWN:
                self.selected = (self.selected + 1) % len(offers)
            elif event.button == BUTTON_CONFIRM:
                self.purchase_selected()
            return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for index, rect in enumerate(self.offer_rects):
                if rect.collidepoint(event.pos):
                    self.selected = self.offer_start + index
                    self.purchase_selected()
                    break
            return True
        return True

    def update(self, dt):
        self.message_timer = max(0.0, self.message_timer - dt)
        if self.active and not self.merchant.is_available:
            self.close()

    def draw_prompt(self):
        if self.active or self.npc_manager is None:
            return
        merchant = self.npc_manager.find_talk_target(self.player)
        if merchant is None:
            return
        label = self.small_font.render("E / Cross  Talk", True, (255, 244, 191))
        box = label.get_rect(midbottom=(self.screen.get_width() // 2, self.screen.get_height() - 112)).inflate(22, 12)
        pygame.draw.rect(self.screen, (14, 21, 31), box, border_radius=8)
        pygame.draw.rect(self.screen, (221, 178, 76), box, 2, border_radius=8)
        self.screen.blit(label, label.get_rect(center=box.center))

    def draw(self):
        if not self.active:
            self.draw_prompt()
            return
        overlay = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        overlay.fill((5, 8, 13, 145))
        self.screen.blit(overlay, (0, 0))
        pygame.draw.rect(self.screen, (17, 25, 38), self.panel, border_radius=12)
        pygame.draw.rect(self.screen, (222, 179, 76), self.panel, 3, border_radius=12)
        title = self.font.render(f"{self.merchant.dialogue_name}'s Market", True, (250, 237, 200))
        self.screen.blit(title, (self.panel.x + 22, self.panel.y + 18))
        coins = self.player.coins
        coin_text = self.small_font.render(f"Your coins: {coins}", True, (242, 202, 80))
        self.screen.blit(coin_text, coin_text.get_rect(topright=(self.panel.right - 22, self.panel.y + 24)))
        self.offer_rects = []
        top = self.panel.y + 66
        offers = self._offers()
        if offers:
            self.selected %= len(offers)
        visible_count = 5
        start = max(0, min(self.selected - visible_count // 2, len(offers) - visible_count))
        self.offer_start = start
        for row, offer in enumerate(offers[start:start + visible_count]):
            index = start + row
            rect = pygame.Rect(self.panel.x + 20, top + row * 66, self.panel.width - 40, 56)
            selected = index == self.selected
            pygame.draw.rect(self.screen, (55, 78, 104) if selected else (28, 40, 57), rect, border_radius=8)
            pygame.draw.rect(self.screen, (226, 185, 83) if selected else (66, 83, 104), rect, 2, border_radius=8)
            icon = load_item_icon(offer["item"], (38, 38))
            if icon:
                self.screen.blit(icon, icon.get_rect(center=(rect.x + 32, rect.centery)))
            name = offer["item"].replace("_", " ").title()
            if offer.get("seed"):
                name += " Seeds"
            label = self.small_font.render(name, True, (237, 241, 246))
            self.screen.blit(label, (rect.x + 60, rect.y + 8))
            detail = self.small_font.render(f"{offer['price']} coins    Stock: {offer['stock']}", True, (190, 201, 213))
            self.screen.blit(detail, (rect.x + 60, rect.y + 30))
            self.offer_rects.append(rect)
        message = self.message if self.message_timer > 0 else "Up/Down: choose   Enter/Cross: buy   E/Circle: close"
        footer = self.small_font.render(message, True, (230, 218, 180))
        self.screen.blit(footer, footer.get_rect(midbottom=(self.panel.centerx, self.panel.bottom - 18)))


class StoryDialogue:
    """Small story dialogue reader with keyboard, controller, and mouse choices."""

    def __init__(self, screen, player, resolver, on_complete=None):
        self.screen = screen
        self.player = player
        self.resolver = resolver
        self.on_complete = on_complete
        self.npc = None
        self.npc_id = None
        self.node = None
        self.line_index = 0
        self.selected_choice = 0
        self.chosen_choice_id = None
        self.choice_rects = []
        accessibility = getattr(getattr(player, "game_state", None), "accessibility", None)
        text_scale = getattr(accessibility, "text_scale", 1.0)
        self.high_contrast = bool(getattr(accessibility, "high_contrast", False))
        speed = getattr(accessibility, "dialogue_speed", "normal")
        self.characters_per_second = {"normal": 42.0, "fast": 95.0, "instant": float("inf")}.get(speed, 42.0)
        self.revealed_characters = 0.0
        self.font = pygame.font.Font(rp("font", "LycheeSoda.ttf"), round(26 * text_scale))
        self.small_font = pygame.font.Font(rp("font", "LycheeSoda.ttf"), round(20 * text_scale))
        width, height = screen.get_size()
        self.panel = pygame.Rect(24, height - min(260, height - 48), width - 48, min(230, height - 48))

    @property
    def active(self):
        return self.node is not None

    @property
    def choices_visible(self):
        return (
            self.active
            and self.line_index >= len(self.node.get("lines", ()))
            and self.chosen_choice_id is None
        )

    def open(self, npc, dialogue_id=None):
        npc_id = dialogue_id or getattr(npc, "story_id", None) or "villager"
        node = self.resolver.resolve(npc_id)
        if node is None:
            return False
        self.player.inventory.is_inv = False
        self.player.dialogue_active = True
        self.npc = npc
        self.npc_id = npc_id
        self.node = node
        self.line_index = 0
        self.selected_choice = 0
        self.chosen_choice_id = None
        self.revealed_characters = 0.0 if self.characters_per_second != float("inf") else float("inf")
        return True

    def close(self):
        self.npc = None
        self.npc_id = None
        self.node = None
        self.line_index = 0
        self.chosen_choice_id = None
        self.revealed_characters = 0.0
        self.player.dialogue_active = False

    def update(self, dt):
        if self.active and self.line_index < len(self.node.get("lines", ())):
            self.revealed_characters += max(0.0, float(dt)) * self.characters_per_second

    def _current_text(self):
        if not self.active or self.line_index >= len(self.node.get("lines", ())):
            return ""
        return str(self.node["lines"][self.line_index].get("text", ""))

    @property
    def current_line_revealed(self):
        return self.revealed_characters >= len(self._current_text())

    def advance(self):
        if not self.active:
            return False
        lines = self.node.get("lines", ())
        if self.line_index < len(lines) and not self.current_line_revealed:
            self.revealed_characters = float("inf")
            return True
        if self.line_index < len(lines) - 1:
            self.line_index += 1
            self.revealed_characters = 0.0 if self.characters_per_second != float("inf") else float("inf")
            return True
        choices = self.node.get("choices", ())
        if choices and self.line_index < len(lines):
            self.line_index = len(lines)
            return True
        if choices and self.chosen_choice_id is None:
            self.chosen_choice_id = choices[self.selected_choice]["id"]
            return True
        choice_id = self.chosen_choice_id
        npc, node = self.npc, self.node
        results = self.resolver.complete(self.npc_id, self.node, choice_id)
        self.close()
        if self.on_complete is not None:
            self.on_complete(npc, node, results)
        return True

    def handle_event(self, event):
        if not self.active:
            return False
        choices = self.node.get("choices", ())
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_ESCAPE, pygame.K_e):
                self.close()
            elif self.choices_visible and choices and event.key in (pygame.K_UP, pygame.K_w):
                self.selected_choice = (self.selected_choice - 1) % len(choices)
            elif self.choices_visible and choices and event.key in (pygame.K_DOWN, pygame.K_s):
                self.selected_choice = (self.selected_choice + 1) % len(choices)
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                self.advance()
            return True
        if event.type == pygame.CONTROLLERBUTTONDOWN:
            if event.button == BUTTON_CANCEL:
                self.close()
            elif self.choices_visible and choices and event.button == BUTTON_DPAD_UP:
                self.selected_choice = (self.selected_choice - 1) % len(choices)
            elif self.choices_visible and choices and event.button == BUTTON_DPAD_DOWN:
                self.selected_choice = (self.selected_choice + 1) % len(choices)
            elif event.button == BUTTON_CONFIRM:
                self.advance()
            return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.choices_visible:
                for index, rect in enumerate(self.choice_rects):
                    if rect.collidepoint(event.pos):
                        self.selected_choice = index
                        self.advance()
                        return True
            self.advance()
            return True
        return True

    def _wrap(self, text, max_width):
        words = str(text).split()
        lines, current = [], ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if current and self.font.size(candidate)[0] > max_width:
                lines.append(current)
                current = word
            else:
                current = candidate
        if current:
            lines.append(current)
        return lines

    def draw(self):
        if not self.active:
            return
        shadow = (0, 0, 0, 245) if self.high_contrast else (8, 13, 22, 215)
        panel_color = (5, 7, 11) if self.high_contrast else (24, 34, 49)
        border_color = (255, 220, 74) if self.high_contrast else (222, 179, 76)
        pygame.draw.rect(self.screen, shadow, self.panel.move(0, 4), border_radius=12)
        pygame.draw.rect(self.screen, panel_color, self.panel, border_radius=12)
        pygame.draw.rect(self.screen, border_color, self.panel, 3, border_radius=12)
        self.choice_rects = []
        if self.choices_visible:
            prompt = self.small_font.render("Choose a response", True, (250, 224, 155))
            self.screen.blit(prompt, (self.panel.x + 24, self.panel.y + 18))
            for index, choice in enumerate(self.node.get("choices", ())):
                rect = pygame.Rect(self.panel.x + 24, self.panel.y + 54 + index * 58, self.panel.width - 48, 48)
                selected = index == self.selected_choice
                pygame.draw.rect(self.screen, (60, 79, 104) if selected else (31, 44, 61), rect, border_radius=8)
                pygame.draw.rect(self.screen, (231, 190, 91) if selected else (79, 96, 116), rect, 2, border_radius=8)
                label = self.small_font.render(choice["text"], True, (242, 241, 235))
                self.screen.blit(label, label.get_rect(midleft=(rect.x + 14, rect.centery)))
                self.choice_rects.append(rect)
            return
        if self.chosen_choice_id is not None:
            choice = next(item for item in self.node.get("choices", ()) if item["id"] == self.chosen_choice_id)
            speaker = self.font.render(getattr(self.npc, "dialogue_name", "Villager"), True, (250, 220, 137))
            self.screen.blit(speaker, (self.panel.x + 24, self.panel.y + 18))
            for index, wrapped in enumerate(self._wrap(choice.get("response", ""), self.panel.width - 48)):
                rendered = self.font.render(wrapped, True, (240, 242, 244))
                self.screen.blit(rendered, (self.panel.x + 24, self.panel.y + 62 + index * 32))
            hint = self.small_font.render("Enter / Cross: continue", True, (176, 190, 207))
            self.screen.blit(hint, hint.get_rect(bottomright=(self.panel.right - 18, self.panel.bottom - 12)))
            return
        line = self.node.get("lines", ())[self.line_index]
        speaker = self.font.render(line.get("speaker", ""), True, (250, 220, 137))
        self.screen.blit(speaker, (self.panel.x + 24, self.panel.y + 18))
        visible_text = (
            str(line["text"])
            if self.revealed_characters == float("inf")
            else str(line["text"])[: int(self.revealed_characters)]
        )
        for index, wrapped in enumerate(self._wrap(visible_text, self.panel.width - 48)):
            rendered = self.font.render(wrapped, True, (240, 242, 244))
            self.screen.blit(rendered, (self.panel.x + 24, self.panel.y + 62 + index * 32))
        hint = self.small_font.render("Enter / Cross: continue    E / Circle: close", True, (176, 190, 207))
        self.screen.blit(hint, hint.get_rect(bottomright=(self.panel.right - 18, self.panel.bottom - 12)))


class DialogueController:
    """Routes a general NPC interaction to story dialogue or merchant service."""

    def __init__(
        self,
        screen,
        player,
        npc_manager,
        resolver,
        interaction_system=None,
        equipment_service_ui=None,
    ):
        self.screen = screen
        self.player = player
        self.npc_manager = npc_manager
        self.interaction_system = interaction_system
        self.equipment_service_ui = equipment_service_ui
        self.story = StoryDialogue(screen, player, resolver, self._on_story_complete)
        self.shop = MerchantDialogue(screen, player, npc_manager)
        self.small_font = pygame.font.Font(rp("font", "LycheeSoda.ttf"), 19)

    @property
    def active(self):
        return (
            self.story.active
            or self.shop.active
            or bool(self.equipment_service_ui and self.equipment_service_ui.active)
        )

    def set_npc_manager(self, npc_manager):
        self.npc_manager = npc_manager
        self.shop.set_npc_manager(npc_manager)
        if self.interaction_system is not None:
            self.interaction_system.set_npc_manager(npc_manager)

    def _target(self):
        if self.npc_manager is None:
            return None
        if self.interaction_system is not None:
            target = self.interaction_system.find_best(self.player)
            return target.entity if target is not None else None
        finder = getattr(self.npc_manager, "find_interaction_target", None)
        if finder is not None:
            return finder(self.player)
        return self.npc_manager.find_talk_target(self.player)

    def _target_record(self):
        if self.interaction_system is None:
            target = self._target()
            return None if target is None else type("Target", (), {"kind": "npc", "entity": target, "prompt": "Talk"})()
        return self.interaction_system.find_best(self.player)

    def open_target(self, target):
        if target is None:
            return False
        if hasattr(target, "kind"):
            if target.kind != "npc":
                return False
            target = target.entity
        if getattr(target, "story_id", None):
            return self.story.open(target)
        if getattr(target, "is_merchant", False):
            return self.story.open(target, "merchant")
        return self.story.open(target)

    def try_open_near_player(self):
        return self.open_target(self._target_record())

    def _on_story_complete(self, npc, node, results):
        if "open_shop" in results:
            self.shop.open(npc)
        elif "open_upgrade_service" in results and self.equipment_service_ui is not None:
            self.equipment_service_ui.open(npc)

    def handle_event(self, event):
        if self.story.active:
            return self.story.handle_event(event)
        if self.equipment_service_ui is not None and self.equipment_service_ui.active:
            return self.equipment_service_ui.handle_event(event)
        return self.shop.handle_event(event)

    def update(self, dt):
        self.story.update(dt)
        self.shop.update(dt)

    def draw(self):
        if self.story.active:
            self.story.draw()
            return
        if self.shop.active:
            self.shop.draw()
            return
        if self.equipment_service_ui is not None and self.equipment_service_ui.active:
            self.equipment_service_ui.draw()
            return
        target_record = self._target_record()
        if target_record is None:
            return
        target = target_record.entity
        if target_record.kind == "npc":
            name = getattr(target, "dialogue_name", None) or getattr(target, "story_id", None) or "Villager"
            prompt = f"Talk to {str(name).replace('_', ' ').title()}"
        else:
            prompt = target_record.prompt
        label = self.small_font.render(f"E / Cross  {prompt}", True, (255, 244, 191))
        box = label.get_rect(midbottom=(self.screen.get_width() // 2, self.screen.get_height() - 112)).inflate(22, 12)
        pygame.draw.rect(self.screen, (14, 21, 31), box, border_radius=8)
        pygame.draw.rect(self.screen, (221, 178, 76), box, 2, border_radius=8)
        self.screen.blit(label, label.get_rect(center=box.center))

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

    @property
    def active(self):
        return self.merchant is not None

    def set_npc_manager(self, npc_manager):
        self.npc_manager = npc_manager

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
        offers = self.merchant.offers
        if not offers:
            return False
        offer = offers[self.selected % len(offers)]
        if offer["stock"] <= 0:
            self.message = "That item is sold out."
            self.message_timer = 2.5
            return False
        price = offer["price"]
        inventory = self.player.inventory
        if self.player.coins < price:
            self.message = f"You need {price} coins."
            self.message_timer = 2.5
            return False
        if not inventory.add_item_to_slot(Item(offer["item"]), 1):
            self.message = "Your inventory is full."
            self.message_timer = 2.5
            return False
        self.player.spend_coins(price)
        offer["stock"] -= 1
        self.message = f"Bought {offer['item'].replace('_', ' ').title()} for {price} coins."
        self.message_timer = 2.5
        return True

    def handle_event(self, event):
        if not self.active:
            return False
        offers = self.merchant.offers
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_ESCAPE, pygame.K_e):
                self.close()
            elif event.key in (pygame.K_UP, pygame.K_w):
                self.selected = (self.selected - 1) % len(offers)
            elif event.key in (pygame.K_DOWN, pygame.K_s):
                self.selected = (self.selected + 1) % len(offers)
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                self.purchase_selected()
            return True
        if event.type == pygame.CONTROLLERBUTTONDOWN:
            if event.button == BUTTON_CANCEL:
                self.close()
            elif event.button == BUTTON_DPAD_UP:
                self.selected = (self.selected - 1) % len(offers)
            elif event.button == BUTTON_DPAD_DOWN:
                self.selected = (self.selected + 1) % len(offers)
            elif event.button == BUTTON_CONFIRM:
                self.purchase_selected()
            return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for index, rect in enumerate(self.offer_rects):
                if rect.collidepoint(event.pos):
                    self.selected = index
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
        for index, offer in enumerate(self.merchant.offers):
            rect = pygame.Rect(self.panel.x + 20, top + index * 66, self.panel.width - 40, 56)
            selected = index == self.selected
            pygame.draw.rect(self.screen, (55, 78, 104) if selected else (28, 40, 57), rect, border_radius=8)
            pygame.draw.rect(self.screen, (226, 185, 83) if selected else (66, 83, 104), rect, 2, border_radius=8)
            icon = load_item_icon(offer["item"], (38, 38))
            if icon:
                self.screen.blit(icon, icon.get_rect(center=(rect.x + 32, rect.centery)))
            name = offer["item"].replace("_", " ").title()
            label = self.small_font.render(name, True, (237, 241, 246))
            self.screen.blit(label, (rect.x + 60, rect.y + 8))
            detail = self.small_font.render(f"{offer['price']} coins    Stock: {offer['stock']}", True, (190, 201, 213))
            self.screen.blit(detail, (rect.x + 60, rect.y + 30))
            self.offer_rects.append(rect)
        message = self.message if self.message_timer > 0 else "Up/Down: choose   Enter/Cross: buy   E/Circle: close"
        footer = self.small_font.render(message, True, (230, 218, 180))
        self.screen.blit(footer, footer.get_rect(midbottom=(self.panel.centerx, self.panel.bottom - 18)))

"""Jim's compact equipment upgrade service UI."""

from __future__ import annotations

import pygame

from gameplay.controls import (
    BUTTON_CANCEL,
    BUTTON_CONFIRM,
    BUTTON_DPAD_DOWN,
    BUTTON_DPAD_UP,
)
from utils import rp


class EquipmentServiceUI:
    def __init__(self, screen, player, service):
        self.screen = screen
        self.player = player
        self.service = service
        self.active = False
        self.npc = None
        self.selection = 0
        self.message = ""
        self.row_rects = []
        self.upgrade_rect = pygame.Rect(0, 0, 0, 0)
        self.font = pygame.font.Font(rp("font", "LycheeSoda.ttf"), 26)
        self.small_font = pygame.font.Font(rp("font", "LycheeSoda.ttf"), 19)

    def equipment_ids(self):
        return tuple(
            equipment_id
            for equipment_id, record in self.player.equipment_state.items()
            if record.get("owned", False)
        )

    def open(self, npc=None):
        if not self.equipment_ids():
            return False
        self.active = True
        self.npc = npc
        self.selection = min(self.selection, len(self.equipment_ids()) - 1)
        self.message = "Choose equipment for Jim to reinforce."
        self.player.dialogue_active = True
        self.player.inventory.is_inv = False
        return True

    def close(self):
        self.active = False
        self.npc = None
        self.player.dialogue_active = False

    def upgrade_selected(self):
        items = self.equipment_ids()
        if not items:
            return False
        result = self.service.upgrade(items[self.selection])
        self.message = result.message
        return result.success

    def handle_event(self, event):
        if not self.active:
            return False
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                self.close()
            elif event.key in (pygame.K_UP, pygame.K_w):
                self.selection = (self.selection - 1) % len(self.equipment_ids())
            elif event.key in (pygame.K_DOWN, pygame.K_s):
                self.selection = (self.selection + 1) % len(self.equipment_ids())
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_u):
                self.upgrade_selected()
            return True
        if event.type == pygame.CONTROLLERBUTTONDOWN:
            if event.button == BUTTON_CANCEL:
                self.close()
            elif event.button == BUTTON_DPAD_UP:
                self.selection = (self.selection - 1) % len(self.equipment_ids())
            elif event.button == BUTTON_DPAD_DOWN:
                self.selection = (self.selection + 1) % len(self.equipment_ids())
            elif event.button == BUTTON_CONFIRM:
                self.upgrade_selected()
            return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for index, rect in enumerate(self.row_rects):
                if rect.collidepoint(event.pos):
                    self.selection = index
                    return True
            if self.upgrade_rect.collidepoint(event.pos):
                self.upgrade_selected()
            return True
        return True

    def draw(self):
        if not self.active:
            return
        shade = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        shade.fill((3, 6, 11, 190))
        self.screen.blit(shade, (0, 0))
        panel = pygame.Rect(0, 0, 640, min(620, self.screen.get_height() - 50))
        panel.center = self.screen.get_rect().center
        pygame.draw.rect(self.screen, (20, 29, 42), panel, border_radius=12)
        pygame.draw.rect(self.screen, (209, 177, 87), panel, 3, border_radius=12)
        self.screen.blit(self.font.render("Jim's Equipment Upgrades", True, (250, 231, 181)), (panel.x + 24, panel.y + 18))
        coins = self.small_font.render(f"Coins: {self.player.coins}", True, (231, 197, 104))
        self.screen.blit(coins, coins.get_rect(topright=(panel.right - 24, panel.y + 24)))

        self.row_rects = []
        items = self.equipment_ids()
        top = panel.y + 62
        row_height = min(48, max(34, (panel.height - 170) // max(1, len(items))))
        for index, equipment_id in enumerate(items):
            record = self.player.equipment_state[equipment_id]
            rect = pygame.Rect(panel.x + 24, top + index * row_height, panel.width - 48, row_height - 4)
            selected = index == self.selection
            pygame.draw.rect(self.screen, (52, 72, 94) if selected else (29, 41, 57), rect, border_radius=7)
            maximum = record["max_durability"]
            text = f"{equipment_id.title()}  {record['tier'].title()}  {record['durability']}/{maximum}"
            self.screen.blit(self.small_font.render(text, True, (239, 239, 231)), (rect.x + 12, rect.y + 9))
            cost = self.service.quote(equipment_id)
            cost_text = "MAX" if cost is None else f"{cost} coins"
            rendered_cost = self.small_font.render(cost_text, True, (226, 190, 104))
            self.screen.blit(rendered_cost, rendered_cost.get_rect(midright=(rect.right - 12, rect.centery)))
            self.row_rects.append(rect)

        self.upgrade_rect = pygame.Rect(panel.right - 180, panel.bottom - 58, 150, 34)
        pygame.draw.rect(self.screen, (76, 145, 201), self.upgrade_rect, border_radius=8)
        label = self.small_font.render("Upgrade", True, (244, 246, 248))
        self.screen.blit(label, label.get_rect(center=self.upgrade_rect.center))
        self.screen.blit(self.small_font.render(self.message, True, (196, 207, 218)), (panel.x + 24, panel.bottom - 52))

"""Quest journal and compact tracked-objective HUD."""

from __future__ import annotations

import pygame


TRACKED_QUEST_TOP = 214

from gameplay.controls import (
    BUTTON_CANCEL,
    BUTTON_CONFIRM,
    BUTTON_DPAD_DOWN,
    BUTTON_DPAD_LEFT,
    BUTTON_DPAD_RIGHT,
    BUTTON_DPAD_UP,
    BUTTON_JOURNAL,
    BUTTON_SPECIAL,
    BUTTON_TOOL,
    BUTTON_TOOL_NEXT,
)
from gameplay.quests import ACTIVE, AVAILABLE, READY_TO_TURN_IN
from gameplay.fishing import (
    FISH_BY_ID,
    LOCALITY_UNLOCK_POINTS,
    get_fish_pool,
    is_locality_unlocked,
    next_fish_unlocks,
    unlocked_fish_ids,
)
from data.crops import CROP_DEFINITIONS, next_crop_unlocks, unlocked_crop_ids
from utils import rp


class QuestJournalUI:
    categories = ("story", "side", "repeatable")

    def __init__(self, screen, player, quest_system):
        self.screen = screen
        self.player = player
        self.quest_system = quest_system
        self.open = False
        self.completed_tab = False
        self.category_index = 0
        self.view = "quests"
        self.selection = 0
        text_scale = getattr(getattr(getattr(player, "game_state", None), "accessibility", None), "text_scale", 1.0)
        self.font = pygame.font.Font(rp("font", "LycheeSoda.ttf"), round(24 * text_scale))
        self.small_font = pygame.font.Font(rp("font", "LycheeSoda.ttf"), round(18 * text_scale))

    @property
    def category(self):
        return self.categories[self.category_index]

    def entries(self):
        return self.quest_system.entries(
            completed=self.completed_tab,
            category=self.category,
        )

    def toggle(self):
        self.open = not self.open
        self.player.journal_active = self.open
        if self.open:
            self.player.inventory.is_inv = False
        return self.open

    def handle_event(self, event):
        is_keyboard = event.type == pygame.KEYDOWN
        is_controller = event.type == pygame.CONTROLLERBUTTONDOWN
        if not is_keyboard and not is_controller:
            return self.open
        key = getattr(event, "key", None)
        button = getattr(event, "button", None)
        if (is_keyboard and key == pygame.K_j) or (is_controller and button == BUTTON_JOURNAL):
            self.toggle()
            return True
        if not self.open:
            return False
        if (is_keyboard and key == pygame.K_ESCAPE) or (is_controller and button == BUTTON_CANCEL):
            self.toggle()
        elif (is_keyboard and key == pygame.K_p) or (is_controller and button == BUTTON_TOOL):
            self.view = "progression"
        elif (is_keyboard and key == pygame.K_q) or (is_controller and button == BUTTON_SPECIAL):
            self.view = "quests"
        elif self.view == "progression":
            return True
        elif (is_keyboard and key in (pygame.K_LEFT, pygame.K_a)) or (is_controller and button == BUTTON_DPAD_LEFT):
            self.category_index = (self.category_index - 1) % len(self.categories)
            self.selection = 0
        elif (is_keyboard and key in (pygame.K_RIGHT, pygame.K_d)) or (is_controller and button == BUTTON_DPAD_RIGHT):
            self.category_index = (self.category_index + 1) % len(self.categories)
            self.selection = 0
        elif (is_keyboard and key in (pygame.K_UP, pygame.K_w)) or (is_controller and button == BUTTON_DPAD_UP):
            self.selection = max(0, self.selection - 1)
        elif (is_keyboard and key in (pygame.K_DOWN, pygame.K_s)) or (is_controller and button == BUTTON_DPAD_DOWN):
            self.selection = min(max(0, len(self.entries()) - 1), self.selection + 1)
        elif (is_keyboard and key == pygame.K_c) or (is_controller and button == BUTTON_TOOL_NEXT):
            self.completed_tab = not self.completed_tab
            self.selection = 0
        elif ((is_keyboard and key == pygame.K_t) or (is_controller and button == BUTTON_CONFIRM)) and self.entries():
            definition, state = self.entries()[self.selection]
            if state["status"] in (ACTIVE, READY_TO_TURN_IN):
                current = self.quest_system.game_state.tracked_quest_id
                self.quest_system.track(None if current == definition["id"] else definition["id"])
        return True

    def draw_progression(self, panel):
        state = self.quest_system.game_state
        progression = state.progression
        left = pygame.Rect(panel.x + 22, panel.y + 92, (panel.width - 58) // 2, panel.height - 142)
        right = pygame.Rect(left.right + 14, left.y, left.width, left.height)
        for rect in (left, right):
            pygame.draw.rect(self.screen, (28, 39, 54), rect, border_radius=9)
            pygame.draw.rect(self.screen, (68, 84, 103), rect, 2, border_radius=9)

        crops = unlocked_crop_ids(state)
        crop_title = self.font.render(
            f"Farming - {progression.farming_points} points",
            True,
            (202, 232, 175),
        )
        self.screen.blit(crop_title, (left.x + 16, left.y + 14))
        crop_count = self.small_font.render(
            f"Crops unlocked: {len(crops)}/{len(CROP_DEFINITIONS)}",
            True,
            (205, 214, 221),
        )
        self.screen.blit(crop_count, (left.x + 16, left.y + 52))
        y = left.y + 86
        next_crops = next_crop_unlocks(state, limit=7)
        if not next_crops:
            self.screen.blit(self.small_font.render("Every crop is unlocked.", True, (220, 196, 116)), (left.x + 16, y))
        for crop in next_crops:
            text = self.small_font.render(
                f"{crop.unlock_at_farming_points}: {crop.display_name} (+{crop.harvest_points})",
                True,
                (221, 225, 228),
            )
            self.screen.blit(text, (left.x + 16, y))
            y += 27

        fish = unlocked_fish_ids(state)
        fish_title = self.font.render(
            f"Fishing - {progression.fishing_points} points",
            True,
            (174, 218, 239),
        )
        self.screen.blit(fish_title, (right.x + 16, right.y + 14))
        fish_count = self.small_font.render(
            f"Species unlocked: {len(fish)}/{len(FISH_BY_ID)}",
            True,
            (205, 214, 221),
        )
        self.screen.blit(fish_count, (right.x + 16, right.y + 52))
        y = right.y + 86
        season = getattr(self.player, "current_season", "summer")
        for locality, threshold in LOCALITY_UNLOCK_POINTS.items():
            unlocked = is_locality_unlocked(locality, state)
            eligible = len(get_fish_pool(locality, season, state)) if unlocked else 0
            label = "Sea" if locality == "ocean" else locality.title()
            status = f"{eligible} available" if unlocked else f"unlocks at {threshold}"
            text = self.small_font.render(
                f"{label}: {status}",
                True,
                (221, 225, 228) if unlocked else (172, 178, 185),
            )
            self.screen.blit(text, (right.x + 16, y))
            y += 27
        y += 12
        for species in next_fish_unlocks(state, limit=4):
            text = self.small_font.render(
                f"{species.unlock_at_fishing_points}: {species.name}",
                True,
                (191, 213, 226),
            )
            self.screen.blit(text, (right.x + 16, y))
            y += 27

        hint = self.small_font.render("J/Back close   Q/Triangle quests", True, (181, 191, 202))
        self.screen.blit(hint, hint.get_rect(bottomright=(panel.right - 18, panel.bottom - 14)))

    def draw_tracked(self):
        quest_id = self.quest_system.game_state.tracked_quest_id
        if not quest_id:
            return
        definition = self.quest_system.get_definition(quest_id)
        state = self.quest_system.get_state(quest_id)
        if state["status"] not in (ACTIVE, READY_TO_TURN_IN):
            return
        panel = pygame.Rect(
            14,
            TRACKED_QUEST_TOP,
            330,
            38 + 29 * len(definition.get("objectives", ())),
        )
        pygame.draw.rect(self.screen, (9, 15, 24, 205), panel, border_radius=8)
        pygame.draw.rect(self.screen, (209, 177, 87), panel, 2, border_radius=8)
        title = self.small_font.render(definition["title"], True, (250, 224, 155))
        self.screen.blit(title, (panel.x + 12, panel.y + 8))
        for index, objective in enumerate(definition.get("objectives", ())):
            value = int(state["objectives"].get(objective["id"], 0))
            required = int(objective.get("required", 1))
            mark = "[x]" if value >= required else "[ ]"
            label = self.small_font.render(
                f"{mark} {objective['description']}  {value}/{required}",
                True,
                (211, 219, 226),
            )
            self.screen.blit(label, (panel.x + 12, panel.y + 34 + index * 27))

    def draw(self):
        if not self.open:
            return
        shade = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        shade.fill((3, 6, 11, 185))
        self.screen.blit(shade, (0, 0))
        width, height = self.screen.get_size()
        panel = pygame.Rect(30, 30, width - 60, height - 60)
        pygame.draw.rect(self.screen, (20, 29, 42), panel, border_radius=12)
        pygame.draw.rect(self.screen, (209, 177, 87), panel, 3, border_radius=12)
        title = self.font.render("Journal", True, (250, 231, 181))
        self.screen.blit(title, (panel.x + 24, panel.y + 18))
        view_tabs = self.small_font.render(
            f"Q Quests{'  [active]' if self.view == 'quests' else ''}     P Progression{'  [active]' if self.view == 'progression' else ''}",
            True,
            (190, 210, 225),
        )
        self.screen.blit(view_tabs, view_tabs.get_rect(topright=(panel.right - 24, panel.y + 24)))
        if self.view == "progression":
            self.draw_progression(panel)
            return
        tab_name = "Completed" if self.completed_tab else "Current"
        tabs = self.small_font.render(
            f"{self.category.title()} Quests  |  {tab_name}   (Left/Right category, C tab)",
            True,
            (171, 197, 219),
        )
        self.screen.blit(tabs, (panel.x + 24, panel.y + 56))

        entries = self.entries()
        if not entries:
            empty = self.font.render("No quests in this section.", True, (158, 169, 182))
            self.screen.blit(empty, (panel.x + 34, panel.y + 120))
        for index, (definition, state) in enumerate(entries):
            y = panel.y + 98 + index * 142
            selected = index == self.selection
            rect = pygame.Rect(panel.x + 22, y, panel.width - 44, 128)
            pygame.draw.rect(self.screen, (43, 59, 78) if selected else (28, 39, 54), rect, border_radius=8)
            pygame.draw.rect(self.screen, (220, 181, 85) if selected else (68, 84, 103), rect, 2, border_radius=8)
            tracked = "  [Tracked]" if self.quest_system.game_state.tracked_quest_id == definition["id"] else ""
            heading = self.font.render(f"{definition['title']}{tracked}", True, (242, 229, 190))
            self.screen.blit(heading, (rect.x + 14, rect.y + 8))
            status_text = state["status"].replace("_", " ").title()
            self.screen.blit(self.small_font.render(status_text, True, (154, 198, 224)), (rect.right - 150, rect.y + 14))
            blocked_reason = self.quest_system.blocked_reason(definition["id"])
            if blocked_reason:
                reason = self.small_font.render(blocked_reason, True, (221, 159, 133))
                self.screen.blit(reason, (rect.x + 18, rect.y + 52))
            for objective_index, objective in enumerate(definition.get("objectives", ()) if not blocked_reason else ()):
                value = int(state["objectives"].get(objective["id"], 0))
                required = int(objective.get("required", 1))
                detail = self.small_font.render(
                    f"{objective['description']}: {value}/{required}",
                    True,
                    (215, 220, 226),
                )
                self.screen.blit(detail, (rect.x + 18, rect.y + 48 + objective_index * 25))
        hint = self.small_font.render("J/Back close   T/Cross track or untrack", True, (181, 191, 202))
        self.screen.blit(hint, hint.get_rect(bottomright=(panel.right - 18, panel.bottom - 14)))

"""Act milestone overlays for the completed story campaign."""

from __future__ import annotations

import pygame

from gameplay.events import QuestStateChanged
from utils import rp


STORY_MILESTONES = {
    "prologue.first_defense": ("Prologue Complete", "The farm still stands"),
    "act1.temporary_medicine": ("Act I Complete", "Borrowed time"),
    "act2.recover_kingdom_map": ("Act II Complete", "The road through the Holds"),
    "act3.royal_aid": ("Act III Complete", "The crown joins the farm"),
    "pirate.befriend": ("Pirate Alliance", "Ironveil has a ship"),
    "holds.grimroot": ("Holds I-III Cleared", "The survivors are coming home"),
    "holds.ironveil_prison": ("Holds IV-V Cleared", "The Princess is free"),
    "act6.rescue_alchemist_family": ("Act VI Complete", "The Potion of Life"),
    "act7.necromancer_citadel": ("Act VII Complete", "The Necromancer has fallen"),
    "act8.distribute_cure": ("Act VIII Complete", "The cure reaches every field"),
    "epilogue.rebuilding": ("Ironveil Reborn", "The Last Cure"),
}


class StoryPresentation:
    def __init__(self, screen, dispatcher, accessibility=None):
        self.screen = screen
        self.reduced_motion = bool(getattr(accessibility, "reduced_motion", False))
        text_scale = getattr(accessibility, "text_scale", 1.0)
        self.title_font = pygame.font.Font(rp("font", "LycheeSoda.ttf"), round(52 * text_scale))
        self.subtitle_font = pygame.font.Font(rp("font", "LycheeSoda.ttf"), round(25 * text_scale))
        self.queue = []
        self.current = None
        self.timer = 0.0
        self.duration = 2.5 if self.reduced_motion else 3.6
        self._unsubscribe = dispatcher.subscribe(QuestStateChanged, self.on_quest_changed)

    @property
    def active(self):
        return self.current is not None

    def on_quest_changed(self, event):
        if event.new_status != "completed" or event.quest_id not in STORY_MILESTONES:
            return False
        self.queue.append(STORY_MILESTONES[event.quest_id])
        if self.current is None:
            self._begin_next()
        return True

    def _begin_next(self):
        self.current = self.queue.pop(0) if self.queue else None
        self.timer = 0.0

    def update(self, dt):
        if self.current is None:
            return
        self.timer += max(0.0, float(dt))
        if self.timer >= self.duration:
            self._begin_next()

    def draw(self):
        if self.current is None:
            return
        if self.reduced_motion:
            alpha = 215
        else:
            edge = min(1.0, self.timer / 0.45, (self.duration - self.timer) / 0.45)
            alpha = round(215 * max(0.0, edge))
        overlay = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        overlay.fill((4, 7, 13, alpha))
        self.screen.blit(overlay, (0, 0))
        title, subtitle = self.current
        title_surface = self.title_font.render(title, True, (252, 229, 157))
        subtitle_surface = self.subtitle_font.render(subtitle, True, (233, 239, 245))
        center = self.screen.get_rect().center
        self.screen.blit(title_surface, title_surface.get_rect(center=(center[0], center[1] - 22)))
        self.screen.blit(subtitle_surface, subtitle_surface.get_rect(center=(center[0], center[1] + 34)))

    def close(self):
        self._unsubscribe()

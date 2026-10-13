"""In-game save naming overlay."""

from __future__ import annotations

import pygame

from gameplay.config import UI_ACCENT, UI_ACCENT_2, UI_BG, UI_MUTED, UI_PANEL, UI_PANEL_ALT, UI_TEXT, UI_WARN
from gameplay.controls import BUTTON_CANCEL, BUTTON_CONFIRM
from utils import rp


class SaveNameDialog:
    """Collect an optional save name while keeping controller saves simple."""

    def __init__(self, screen, save_manager):
        self.screen = screen
        self.save_manager = save_manager
        self.active = False
        self.text = ""
        self.suggestion = "save_1"
        self.message = ""
        font_path = rp("font", "LycheeSoda.ttf")
        self.title_font = pygame.font.Font(font_path, 40)
        self.body_font = pygame.font.Font(font_path, 24)
        self.small_font = pygame.font.Font(font_path, 18)

    def open(self):
        self.active = True
        self.message = ""
        if self.save_manager.path is not None:
            self.text = self.save_manager.current_name or self.save_manager._name_from_existing_save(
                self.save_manager.path
            )
            self.suggestion = self.text
        else:
            self.text = ""
            self.suggestion = self.save_manager.next_default_name()
        pygame.key.start_text_input()

    def close(self):
        self.active = False
        pygame.key.stop_text_input()

    def handle_event(self, event):
        """Return ``(action, name)`` when the dialog completes."""
        if not self.active:
            return None
        if event.type == pygame.TEXTINPUT:
            if len(self.text) < 48:
                self.text += event.text
            return None
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_BACKSPACE:
                self.text = self.text[:-1]
            elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                name = self.text.strip() or self.suggestion
                self.close()
                return "save", name
            elif event.key == pygame.K_ESCAPE:
                self.close()
                return "cancel", None
            elif event.unicode and event.unicode.isprintable() and not hasattr(pygame, "TEXTINPUT"):
                if len(self.text) < 48:
                    self.text += event.unicode
            return None
        if event.type == pygame.CONTROLLERBUTTONDOWN:
            if event.button == BUTTON_CONFIRM:
                name = self.text.strip() or self.suggestion
                self.close()
                return "save", name
            if event.button == BUTTON_CANCEL:
                self.close()
                return "cancel", None
        return None

    def draw(self):
        if not self.active:
            return
        shade = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        shade.fill((3, 7, 13, 205))
        self.screen.blit(shade, (0, 0))

        width, height = self.screen.get_size()
        panel = pygame.Rect(0, 0, min(620, width - 80), 310)
        panel.center = (width // 2, height // 2)
        pygame.draw.rect(self.screen, UI_PANEL, panel, border_radius=14)
        pygame.draw.rect(self.screen, UI_PANEL_ALT, panel, 2, border_radius=14)

        title = self.title_font.render("Save Game", True, UI_TEXT)
        self.screen.blit(title, title.get_rect(center=(panel.centerx, panel.y + 55)))
        subtitle = self.small_font.render(
            "Enter a name, or leave it blank to use the suggested name.",
            True,
            UI_MUTED,
        )
        self.screen.blit(subtitle, subtitle.get_rect(center=(panel.centerx, panel.y + 94)))

        input_rect = pygame.Rect(panel.x + 42, panel.y + 124, panel.width - 84, 62)
        pygame.draw.rect(self.screen, (10, 18, 29), input_rect, border_radius=10)
        pygame.draw.rect(self.screen, UI_ACCENT, input_rect, 2, border_radius=10)
        display_text = self.text or self.suggestion
        text_color = UI_TEXT if self.text else UI_MUTED
        value = self.body_font.render(display_text, True, text_color)
        self.screen.blit(value, (input_rect.x + 16, input_rect.y + 17))
        if (pygame.time.get_ticks() // 500) % 2:
            cursor_x = min(input_rect.right - 12, input_rect.x + 16 + value.get_width() + 2)
            pygame.draw.line(self.screen, UI_ACCENT_2, (cursor_x, input_rect.y + 15), (cursor_x, input_rect.bottom - 15), 2)

        hint = "Enter: save    Esc: cancel"
        hint_surface = self.small_font.render(hint, True, UI_MUTED)
        self.screen.blit(hint_surface, hint_surface.get_rect(center=(panel.centerx, panel.bottom - 56)))
        if self.message:
            message = self.small_font.render(self.message, True, UI_WARN)
            self.screen.blit(message, message.get_rect(center=(panel.centerx, panel.bottom - 26)))

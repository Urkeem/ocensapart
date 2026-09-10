"""Pre-game title, mode, seed, customization, and loading flow."""

import pygame

from core.camera import Camera
from entities.npc import NPCManager
from entities.player import Player
from gameplay.assets import get_shared_assets
from gameplay.controls import (
    BUTTON_CANCEL,
    BUTTON_CONFIRM,
    BUTTON_DPAD_DOWN,
    BUTTON_DPAD_LEFT,
    BUTTON_DPAD_RIGHT,
    BUTTON_DPAD_UP,
    BUTTON_SPECIAL,
    get_controller_input,
)
from gameplay.config import (
    DEFAULT_ACTIVE_RADIUS,
    DEFAULT_CHUNK_SIZE,
    DEFAULT_NPC_COUNT,
    DEFAULT_TILE_SIZE,
    UI_ACCENT,
    UI_ACCENT_2,
    UI_BG,
    UI_MUTED,
    UI_PANEL,
    UI_PANEL_ALT,
    UI_TEXT,
    UI_WARN,
    WORLD_SCALE,
)
from gameplay.world_objects import (
    prewarm_chunk_runtime,
    prewarm_runtime_asset_caches,
    spawn_rock_piece_drops,
)
from gameplay.savegame import SaveGameManager, deserialize_chunk_states, restore_player
from ui.hud import GameplayHUD
from utils import rp
from world.soil import SoilLayer
from world.worldmanager import WorldRun


class StartupFlow:
    def __init__(self, screen):
        self.screen = screen
        self.screen_width, self.screen_height = screen.get_size()
        self.stage = "title"
        self.mode_index = 0
        self.modes = ["Island Voyage", "Story Mode"]
        self.seed_text = ""
        self.world_run = None
        self.customization_categories = ["skin", "clothes", "hair"]
        self.customization_category_index = 0
        self.customization = {}
        self.assets = None
        self.runtime_assets_ready = False
        self.world = None
        self.island_prepared = False
        self.soil_layer = None
        self.hud = None
        self.npc_manager = None
        self.player = None
        self.camera = None
        self.last_player_chunk = None
        self.loading_progress = 0.0
        self.loading_label = ""
        self.loading_note = ""
        self.target_chunk_count = 0
        self.done = False
        self.quit_requested = False
        self.controller_input = get_controller_input()
        self.save_manager = SaveGameManager()
        self.loaded_save_data = None

        startup_font_path = rp("font", "LycheeSoda.ttf")
        self.big_font = pygame.font.Font(startup_font_path, 78)
        self.title_font = pygame.font.Font(startup_font_path, 56)
        self.body_font = pygame.font.Font(startup_font_path, 28)
        self.small_font = pygame.font.Font(startup_font_path, 20)

    def handle_event(self, event):
        self.controller_input.handle_event(event)
        is_keyboard = event.type == pygame.KEYDOWN
        is_controller = event.type == pygame.CONTROLLERBUTTONDOWN
        axis_button = self.controller_input.menu_navigation_button(event)
        if not is_keyboard and not is_controller and axis_button is None:
            return

        key = getattr(event, "key", None)
        button = axis_button if axis_button is not None else getattr(event, "button", None)
        is_controller_navigation = is_controller or axis_button is not None
        confirm = (
            (is_keyboard and key in (pygame.K_RETURN, pygame.K_SPACE))
            or (is_controller and button == BUTTON_CONFIRM)
        )
        cancel = (
            (is_keyboard and key == pygame.K_ESCAPE)
            or (is_controller and button == BUTTON_CANCEL)
        )
        up = (
            (is_keyboard and key in (pygame.K_UP, pygame.K_w))
            or (is_controller_navigation and button == BUTTON_DPAD_UP)
        )
        down = (
            (is_keyboard and key in (pygame.K_DOWN, pygame.K_s))
            or (is_controller_navigation and button == BUTTON_DPAD_DOWN)
        )
        left = (
            (is_keyboard and key in (pygame.K_LEFT, pygame.K_a))
            or (is_controller_navigation and button == BUTTON_DPAD_LEFT)
        )
        right = (
            (is_keyboard and key in (pygame.K_RIGHT, pygame.K_d))
            or (is_controller_navigation and button == BUTTON_DPAD_RIGHT)
        )

        if self.stage == "title":
            load_requested = (
                (is_keyboard and key == pygame.K_l)
                or (is_controller and button == BUTTON_SPECIAL)
            )
            if load_requested:
                if not self.save_manager.exists:
                    self.loading_note = "No saved voyage was found."
                else:
                    try:
                        self.begin_loading(self.save_manager.load())
                    except (OSError, ValueError, TypeError) as error:
                        self.loading_note = f"Could not load save: {error}"
            elif confirm:
                self.stage = "mode"
            elif cancel:
                self.quit_requested = True

        elif self.stage == "mode":
            if up:
                self.mode_index = (self.mode_index - 1) % len(self.modes)
            elif down:
                self.mode_index = (self.mode_index + 1) % len(self.modes)
            elif confirm:
                if self.mode_index == 0:
                    self.stage = "seed"
                else:
                    self.loading_note = "Story mode is coming later."
            elif cancel:
                self.stage = "title"

        elif self.stage == "seed":
            if confirm:
                self.begin_customization()
            elif is_keyboard and key == pygame.K_BACKSPACE:
                self.seed_text = self.seed_text[:-1]
            elif cancel:
                self.stage = "mode"
            elif is_keyboard:
                if event.unicode.isdigit() or (event.unicode == "-" and not self.seed_text):
                    self.seed_text += event.unicode

        elif self.stage == "customize":
            if left:
                self.change_customization_option(-1)
            elif right:
                self.change_customization_option(1)
            elif up:
                self.customization_category_index = (
                    self.customization_category_index - 1
                ) % len(self.customization_categories)
            elif down:
                self.customization_category_index = (
                    self.customization_category_index + 1
                ) % len(self.customization_categories)
            elif confirm:
                self.begin_loading()
            elif cancel:
                self.stage = "seed"

    def get_selected_seed(self):
        if self.seed_text.strip() in ("", "-"):
            return 0
        return int(self.seed_text)

    def begin_loading(self, save_data=None):
        self.stage = "loading"
        self.loading_progress = 0.0
        self.loading_label = "Preparing voyage"
        self.loading_note = "Starting asset initialization..."
        self.world_run = None
        self.world = None
        self.island_prepared = False
        self.soil_layer = None
        self.hud = None
        self.npc_manager = None
        self.player = None
        self.camera = None
        self.last_player_chunk = None
        self.target_chunk_count = 0
        self.loaded_save_data = save_data
        if save_data:
            self.customization = dict(save_data.get("player", {}).get("customization", {}))

    def begin_customization(self):
        self.stage = "customize"
        if self.assets is None:
            self.assets = get_shared_assets()
        self.customization = self.assets.normalize_character_customization(self.customization)

    def get_customization_options(self, category):
        if self.assets is None:
            return []
        options = self.assets.get_character_options().get(category, [])
        if category == "weapon":
            return [None] + options
        return options

    def change_customization_option(self, direction):
        category = self.customization_categories[self.customization_category_index]
        options = self.get_customization_options(category)
        if not options:
            return

        current = self.customization.get(category)
        if current not in options:
            current = options[0]
        current_index = options.index(current)
        self.customization[category] = options[(current_index + direction) % len(options)]
    
    async def update(self):
        if self.stage != "loading" or self.done:
            return

        if self.assets is None:
            self.loading_label = "Initializing assets"
            self.loading_note = "Loading sprite sheets and animation data..."
            self.assets = get_shared_assets()
            self.loading_progress = 0.15
            return

        if not self.runtime_assets_ready:
            self.loading_label = "Preparing world visuals"
            self.loading_note = "Caching terrain, trees, houses, and island props..."
            prewarm_runtime_asset_caches()
            self.runtime_assets_ready = True
            self.loading_progress = 0.25
            return

        if self.world is None:
            self.loading_label = "Creating island"
            run_state = (self.loaded_save_data or {}).get("world_run", {})
            seed = int(run_state.get("seed", self.get_selected_seed()))
            island_index = int(run_state.get("current_index", 1))
            self.loading_note = f"Regenerating saved island chain from seed {seed}..." if self.loaded_save_data else f"Generating island chain from seed {seed}..."
            self.world_run = WorldRun(seed=seed, start_index=island_index)
            self.world_run.discovered_islands.update(run_state.get("discovered_islands", ()))
            self.world = self.world_run.create_world(
                spawn_chunk=(0, 0),
                chunk_size=DEFAULT_CHUNK_SIZE,
                active_radius=DEFAULT_ACTIVE_RADIUS,
                tile_size=DEFAULT_TILE_SIZE,
            )
            if self.loaded_save_data:
                self.world.saved_chunk_states = deserialize_chunk_states(
                    self.loaded_save_data.get("world", {}).get("chunks", {})
                )
            self.soil_layer = SoilLayer(self.world)
            self.camera = Camera(self.screen_width, self.screen_height, mode="edge")
            spawn_x, spawn_y = self.world.get_spawn_position()
            self.player = Player(
                (spawn_x, spawn_y),
                assets=self.assets,
                speed=100,
                visual_scale=WORLD_SCALE,
                soil_layer=self.soil_layer,
                customization=self.customization,
                controller_input=self.controller_input,
            )
            self.player.rock_drop_callback = spawn_rock_piece_drops
            if self.loaded_save_data:
                restore_player(self.player, self.loaded_save_data.get("player"))
            self.hud = GameplayHUD(self.player, self.screen)
            self.world.current_player_chunk = self.world.world_to_chunk(
                self.player.center
            )
            self.target_chunk_count = max(1, len(self.world.get_level_chunk_coords()))
            self.loading_progress = 0.30
            return

        if not self.island_prepared:
            self.loading_label = "Generating complete island"
            self.loading_note = (
                f"Finishing all {self.target_chunk_count} chunks before landing..."
            )
            self.world.prepare_full_island(
                prewarm_chunk_callback=lambda chunk: prewarm_chunk_runtime(
                    chunk,
                    self.world,
                    self.soil_layer,
                )
            )
            self.island_prepared = True
            self.loading_progress = 0.90
            return

        self.loading_label = "Launching"
        self.loading_note = f"Everything is in place. Landing on {self.world.level_name}..."
        if self.npc_manager is None:
            self.npc_manager = NPCManager(
                self.world,
                self.assets,
                count=DEFAULT_NPC_COUNT,
            )
        self.loading_progress = 1.0
        self.last_player_chunk = self.world.world_to_chunk(self.player.center)
        self.done = True

    def draw(self):
        self.screen.fill(UI_BG)
        self.draw_background_swells()

        if self.stage == "title":
            self.draw_title_screen()
        elif self.stage == "mode":
            self.draw_mode_screen()
        elif self.stage == "seed":
            self.draw_seed_screen()
        elif self.stage == "customize":
            self.draw_customize_screen()
        elif self.stage == "loading":
            self.draw_loading_screen()

    def draw_background_swells(self):
        width, height = self.screen.get_size()
        for i, radius in enumerate((520, 380, 260)):
            surf = pygame.Surface((width, height), pygame.SRCALPHA)
            alpha = 22 + i * 12
            pygame.draw.circle(surf, (40, 80, 120, alpha), (width // 2, height + 80), radius)
            self.screen.blit(surf, (0, 0))

    def draw_center_panel(
        self,
        title,
        subtitle=None,
        footer=None,
        center_text=False,
        title_font=None,
        subtitle_font=None,
        size=None,
    ):
        if self.controller_input.connected and title == "Choose your mode":
            footer = "Use D-pad or left stick and Cross"
        if size:
            panel_w, panel_h = size
            panel = pygame.Rect(0, 0, min(panel_w, self.screen_width - 80), min(panel_h, self.screen_height - 80))
        else:
            panel = pygame.Rect(0, 0, 600, 600)
        panel.center = (self.screen_width // 2, self.screen_height // 2)
        pygame.draw.rect(self.screen, UI_PANEL, panel, border_radius=10)
        pygame.draw.rect(self.screen, UI_PANEL_ALT, panel, 2, border_radius=10)

        title_surf = (title_font or self.title_font).render(title, True, UI_TEXT)
        if center_text:
            title_rect = title_surf.get_rect(center=(panel.centerx, panel.y + 62))
        else:
            title_rect = title_surf.get_rect(topleft=(panel.x + 36, panel.y + 34))
        self.screen.blit(title_surf, title_rect)

        if subtitle:
            sub_surf = (subtitle_font or self.small_font).render(subtitle, True, UI_MUTED)
            if center_text:
                sub_rect = sub_surf.get_rect(center=(panel.centerx, panel.y + 106))
            else:
                sub_rect = sub_surf.get_rect(topleft=(panel.x + 38, panel.y + 86))
            self.screen.blit(sub_surf, sub_rect)

        if footer:
            foot_surf = self.small_font.render(footer, True, UI_MUTED)
            if center_text:
                foot_rect = foot_surf.get_rect(center=(panel.centerx, panel.bottom - 38))
            else:
                foot_rect = foot_surf.get_rect(topleft=(panel.x + 36, panel.bottom - 46))
            self.screen.blit(foot_surf, foot_rect)

        return panel

    def draw_title_screen(self):
        if self.controller_input.connected:
            footer = "Cross: new voyage    Triangle: load voyage"
        else:
            footer = "Enter: new voyage    L: load voyage"
        panel = self.draw_center_panel(
            "Oceans Apart",
            "A drifting world of islands, storms, and stories.",
            footer,
            center_text=True,
            size=(600, 260),
        )
        subtitle = self.body_font.render("Set sail into a fresh world.", True, UI_ACCENT_2)
        self.screen.blit(subtitle, (panel.x + 160, panel.y + 148))
        if self.loading_note:
            note = self.small_font.render(self.loading_note, True, UI_WARN)
            self.screen.blit(note, note.get_rect(midbottom=(panel.centerx, panel.bottom - 12)))

    def draw_mode_screen(self):
        panel = self.draw_center_panel(
            "Choose your mode",
            "Story mode stays visible for now, but island voyage is the playable path.",
            "Use â†‘ â†“ and Enter",
            center_text=True,
            size=(600, 360),
        )
        start_y = panel.y + 150
        for i, mode in enumerate(self.modes):
            option_rect = pygame.Rect(panel.x + 36, start_y + i * 84, panel.width - 72, 58)
            selected = i == self.mode_index
            fill = UI_ACCENT if selected else UI_PANEL_ALT
            pygame.draw.rect(self.screen, fill, option_rect, border_radius=14)
            text_color = UI_BG if selected else UI_TEXT
            label = self.body_font.render(mode, True, text_color)
            self.screen.blit(label, label.get_rect(midleft=(option_rect.x + 20, option_rect.centery)))

            if mode == "Story Mode":
                badge = self.small_font.render("coming soon", True, UI_WARN if selected else UI_MUTED)
                self.screen.blit(badge, badge.get_rect(midright=(option_rect.right - 18, option_rect.centery)))

        if self.loading_note:
            note = self.small_font.render(self.loading_note, True, UI_ACCENT_2)
            self.screen.blit(note, (panel.x + 36, panel.bottom - 88))

    def draw_seed_screen(self):
        footer = (
            "Cross = customize    Circle = back"
            if self.controller_input.connected
            else "Enter = customize    Esc = back"
        )
        panel = self.draw_center_panel(
            "Voyage seed",
            "Enter a seed to generate an island chain. Leave it blank to use 0.",
            footer,
            center_text=True,
            size=(600, 360),

        )
        input_rect = pygame.Rect(panel.x + 36, panel.y + 170, panel.width - 72, 74)
        pygame.draw.rect(self.screen, (12, 18, 29), input_rect, border_radius=14)
        pygame.draw.rect(self.screen, UI_ACCENT, input_rect, 2, border_radius=14)

        value = self.seed_text if self.seed_text else "0"
        value_surf = self.body_font.render(value, True, UI_TEXT)
        self.screen.blit(value_surf, (input_rect.x + 18, input_rect.y + 20))

        hint = self.small_font.render("Examples: 0, 1392, 8675309, -17", True, UI_MUTED)
        self.screen.blit(hint, (panel.x + 38, input_rect.bottom + 18))

    def draw_customize_screen(self):
        footer = (
            "D-pad = navigate    Cross = continue    Circle = back"
            if self.controller_input.connected
            else "Up/Down = category    Left/Right = option    Enter = continue"
        )
        panel = self.draw_center_panel(
            "Customize",
            "Choose your look before landing.",
            footer,
            center_text=True,
            size=(680, 500),

        )
        if self.assets is None:
            return

        preview_frames = self.assets.get_character_frames("down_idle", self.customization)
        preview_index = int((pygame.time.get_ticks() / 360) % len(preview_frames))
        preview = pygame.transform.scale(preview_frames[preview_index], (192, 192))
        preview_rect = preview.get_rect(center=(panel.centerx, panel.y + 168))
        pygame.draw.rect(self.screen, (12, 18, 29), preview_rect.inflate(26, 26), border_radius=12)
        pygame.draw.rect(self.screen, UI_ACCENT, preview_rect.inflate(26, 26), 2, border_radius=12)
        self.screen.blit(preview, preview_rect)

        start_y = panel.y + 292
        for index, category in enumerate(self.customization_categories):
            selected = index == self.customization_category_index
            row = pygame.Rect(panel.x + 70, start_y + index * 40, panel.width - 140, 32)
            if selected:
                pygame.draw.rect(self.screen, UI_ACCENT, row, border_radius=8)

            label_color = UI_BG if selected else UI_TEXT
            value_color = UI_BG if selected else UI_ACCENT_2
            label = self.small_font.render(category.title(), True, label_color)
            options = self.get_customization_options(category)
            value = self.customization.get(category)
            value_text = "None" if value is None else str(value)
            if not options:
                value_text = "None"
            value_label = self.small_font.render(value_text, True, value_color)

            self.screen.blit(label, label.get_rect(midleft=(row.x + 14, row.centery)))
            self.screen.blit(value_label, value_label.get_rect(midright=(row.right - 14, row.centery)))

    def draw_loading_screen(self):
        # draw the loading screen
        panel = self.draw_center_panel(
            self.loading_label or "Preparing",
            self.loading_note or "Please wait...",
            None,
            center_text=True,
            title_font=self.body_font,
            subtitle_font=self.small_font,
            size=(620, 260),
        )
        bar_rect = pygame.Rect(panel.x + 54, panel.y + 142, panel.width - 108, 28)
        pygame.draw.rect(self.screen, (12, 18, 29), bar_rect, border_radius=12)
        fill_w = max(10, int(bar_rect.width * self.loading_progress)) if self.loading_progress > 0 else 0
        if fill_w:
            fill_rect = pygame.Rect(bar_rect.x, bar_rect.y, fill_w, bar_rect.height)
            pygame.draw.rect(self.screen, UI_ACCENT, fill_rect, border_radius=12)

        percent = self.small_font.render(f"{int(self.loading_progress * 100)}%", True, UI_TEXT)
        self.screen.blit(percent, (bar_rect.right - percent.get_width(), bar_rect.bottom + 12))

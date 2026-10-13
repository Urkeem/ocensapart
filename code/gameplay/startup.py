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
    BUTTON_TOOL,
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
    prewarm_chunk_runtime_step,
    prewarm_runtime_asset_caches,
    spawn_rock_piece_drops,
)
from gameplay.savegame import SaveGameManager, deserialize_chunk_states, restore_player
from gameplay.game_state import GameState
from gameplay.locations import ensure_player_farm, player_farm_chunk_coord
from ui.hud import GameplayHUD
from utils import rp
from world.soil import SoilLayer
from world.worldmanager import WorldRun


class StartupFlow:
    def __init__(self, screen):
        self.screen = screen
        self.screen_width, self.screen_height = screen.get_size()
        self.stage = "boot"
        self.boot_started_at = pygame.time.get_ticks()
        self.boot_duration_ms = 2400
        self.mode_index = 0
        self.modes = ["Island Voyage", "Story Mode"]
        self.selected_mode = "voyage"
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
        self.landing_chunk_coords = set()
        self.done = False
        self.quit_requested = False
        self.controller_input = get_controller_input()
        self.save_manager = SaveGameManager()
        self.save_slots = self.save_manager.list_saves()
        self.save_index = 0
        self.selected_save_path = None
        self.loaded_save_data = None
        self.game_state = GameState()
        self.settings_index = 0
        self.settings_rows = ("text_scale", "high_contrast", "reduced_motion", "dialogue_speed")
        self.setup_focus = 0
        self.setup_rows = (
            "mode",
            "seed",
            "skin",
            "clothes",
            "hair",
            "start",
            "saves",
            "load",
            "settings",
            "quit",
        )
        self.setup_hitboxes = {}

        startup_font_path = rp("font", "LycheeSoda.ttf")
        self.big_font = pygame.font.Font(startup_font_path, 78)
        self.title_font = pygame.font.Font(startup_font_path, 56)
        self.body_font = pygame.font.Font(startup_font_path, 28)
        self.small_font = pygame.font.Font(startup_font_path, 20)
        self.tiny_font = pygame.font.Font(startup_font_path, 16)
        try:
            self.title_art = pygame.image.load(
                rp("graphics", "sprites", "title_screen.png")
            ).convert()
        except (OSError, pygame.error):
            self.title_art = None

    def handle_event(self, event):
        self.controller_input.handle_event(event)
        is_keyboard = event.type == pygame.KEYDOWN
        is_controller = event.type == pygame.CONTROLLERBUTTONDOWN
        axis_button = self.controller_input.menu_navigation_button(event)
        is_mouse = event.type == pygame.MOUSEBUTTONDOWN
        if not is_keyboard and not is_controller and axis_button is None and not is_mouse:
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

        if self.stage == "boot":
            if cancel:
                self.quit_requested = True
            elif confirm or is_keyboard or is_controller or is_mouse:
                self.open_setup()

        elif self.stage in ("title", "setup"):
            load_requested = (
                (is_keyboard and key == pygame.K_l)
                or (is_controller and button == BUTTON_SPECIAL)
            )
            settings_requested = (
                (is_keyboard and key == pygame.K_s)
                or (is_controller and button == BUTTON_TOOL)
            )
            if settings_requested:
                self.settings_return_stage = self.stage
                self.stage = "settings"
            elif load_requested:
                self.load_selected_save()
            elif is_mouse:
                self.handle_setup_click(event.pos)
            elif up:
                self.setup_focus = (self.setup_focus - 1) % len(self.setup_rows)
            elif down:
                self.setup_focus = (self.setup_focus + 1) % len(self.setup_rows)
            elif left:
                self.change_setup_value(-1)
            elif right:
                self.change_setup_value(1)
            elif is_keyboard and self.setup_rows[self.setup_focus] == "seed":
                if key == pygame.K_BACKSPACE:
                    self.seed_text = self.seed_text[:-1]
                elif event.unicode.isdigit() or (event.unicode == "-" and not self.seed_text):
                    self.seed_text += event.unicode
            elif confirm:
                self.activate_setup_row()
            elif cancel:
                self.quit_requested = True

        elif self.stage == "settings":
            if up:
                self.settings_index = (self.settings_index - 1) % len(self.settings_rows)
            elif down:
                self.settings_index = (self.settings_index + 1) % len(self.settings_rows)
            elif left:
                self.change_accessibility_setting(-1)
            elif right or confirm:
                self.change_accessibility_setting(1)
            elif cancel:
                self.stage = getattr(self, "settings_return_stage", "setup")

    def open_setup(self):
        self.stage = "setup"
        self.refresh_save_slots()
        self.begin_customization()

    def refresh_save_slots(self):
        self.save_slots = self.save_manager.list_saves()
        if not self.save_slots:
            self.save_index = 0
        else:
            self.save_index = max(0, min(self.save_index, len(self.save_slots) - 1))

    def change_setup_value(self, direction):
        row = self.setup_rows[self.setup_focus]
        if row == "mode":
            self.mode_index = (self.mode_index + direction) % len(self.modes)
            self.selected_mode = "story" if self.mode_index == 1 else "voyage"
        elif row in self.customization_categories:
            self.customization_category_index = self.customization_categories.index(row)
            self.change_customization_option(direction)
        elif row == "saves" and self.save_slots:
            self.save_index = (self.save_index + direction) % len(self.save_slots)

    def activate_setup_row(self):
        row = self.setup_rows[self.setup_focus]
        if row in ("mode", *self.customization_categories):
            self.change_setup_value(1)
        elif row == "seed":
            self.setup_focus = self.setup_rows.index("skin")
        elif row == "start":
            self.begin_loading()
        elif row in ("saves", "load"):
            self.load_selected_save()
        elif row == "settings":
            self.settings_return_stage = "setup"
            self.stage = "settings"
        elif row == "quit":
            self.quit_requested = True

    def handle_setup_click(self, position):
        for target, rect in self.setup_hitboxes.items():
            if not rect.collidepoint(position):
                continue
            if isinstance(target, tuple) and target[0] == "save":
                self.save_index = target[1]
                self.setup_focus = self.setup_rows.index("saves")
                return
            self.setup_focus = self.setup_rows.index(target)
            if target in ("start", "load", "settings", "quit"):
                self.activate_setup_row()
            elif target in ("mode", *self.customization_categories):
                self.change_setup_value(1)
            return

    def load_selected_save(self):
        self.refresh_save_slots()
        if not self.save_slots:
            self.loading_note = "No saved games were found."
            return False
        slot = self.save_slots[self.save_index]
        if not slot.valid:
            self.loading_note = f"Could not load {slot.name}: {slot.error}"
            return False
        try:
            self.selected_save_path = slot.path
            self.begin_loading(self.save_manager.load(slot.path), slot.path)
            return True
        except (OSError, ValueError, TypeError) as error:
            self.loading_note = f"Could not load save: {error}"
            return False

    def get_selected_seed(self):
        if self.seed_text.strip() in ("", "-"):
            return 0
        return int(self.seed_text)

    def begin_loading(self, save_data=None, save_path=None):
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
        self.landing_chunk_coords = set()
        self.loaded_save_data = save_data
        self.selected_save_path = save_path
        selected_accessibility = self.game_state.accessibility.to_dict()
        self.game_state = GameState.from_dict((save_data or {}).get("game_state"))
        if not save_data:
            self.game_state.accessibility = self.game_state.accessibility.from_dict(selected_accessibility)
        if save_data:
            self.selected_mode = str(self.game_state.flag("game.mode", "voyage"))
        else:
            self.game_state.set_flag("game.mode", self.selected_mode)
            if self.selected_mode == "story":
                self.game_state.set_location("player_house_interior")
        if save_data:
            self.customization = dict(save_data.get("player", {}).get("customization", {}))

    def begin_customization(self):
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

    def change_accessibility_setting(self, direction):
        setting = self.settings_rows[self.settings_index]
        accessibility = self.game_state.accessibility
        if setting == "text_scale":
            values = (1.0, 1.25, 1.5)
            current = min(range(len(values)), key=lambda index: abs(values[index] - accessibility.text_scale))
            accessibility.text_scale = values[(current + direction) % len(values)]
        elif setting == "dialogue_speed":
            values = ("normal", "fast", "instant")
            current = values.index(accessibility.dialogue_speed)
            accessibility.dialogue_speed = values[(current + direction) % len(values)]
        else:
            setattr(accessibility, setting, not getattr(accessibility, setting))
    
    async def update(self):
        if self.stage == "boot":
            if pygame.time.get_ticks() - self.boot_started_at >= self.boot_duration_ms:
                self.open_setup()
            return
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
            self.loading_label = "Creating kingdom" if self.selected_mode == "story" else "Creating island"
            run_state = (self.loaded_save_data or {}).get("world_run", {})
            seed = int(run_state.get("seed", self.get_selected_seed()))
            island_index = int(run_state.get("current_index", 1))
            self.loading_note = f"Regenerating saved island chain from seed {seed}..." if self.loaded_save_data else f"Generating island chain from seed {seed}..."
            world_kind = run_state.get(
                "world_kind",
                "kingdom" if self.selected_mode == "story" else "island",
            )
            self.world_run = WorldRun(seed=seed, start_index=island_index, world_kind=world_kind)
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
            self.player.game_state = self.game_state
            if self.loaded_save_data:
                restore_player(self.player, self.loaded_save_data.get("player"))
            self.hud = GameplayHUD(self.player, self.screen)
            self.world.current_player_chunk = self.world.world_to_chunk(
                self.player.center
            )
            self.camera.update(self.player)
            chunk_pixel_w = self.world.chunk_size[0] * self.world.tile_size
            chunk_pixel_h = self.world.chunk_size[1] * self.world.tile_size
            view_left = int(self.camera.offset.x)
            view_top = int(self.camera.offset.y)
            view_right = view_left + int(self.screen_width / self.camera.zoom)
            view_bottom = view_top + int(self.screen_height / self.camera.zoom)
            self.landing_chunk_coords = {
                coord
                for chunk_y in range(
                    view_top // chunk_pixel_h,
                    ((view_bottom - 1) // chunk_pixel_h) + 1,
                )
                for chunk_x in range(
                    view_left // chunk_pixel_w,
                    ((view_right - 1) // chunk_pixel_w) + 1,
                )
                if self.world.is_chunk_in_level_bounds(
                    coord := (chunk_x, chunk_y)
                )
            }
            if self.game_state.flag("game.mode") == "story":
                self.landing_chunk_coords.add(
                    player_farm_chunk_coord(self.world, self.game_state)
                )
            self.world.queue_chunks_around(self.world.current_player_chunk)
            self.world.prepare_loaded_chunks_incrementally(
                self.landing_chunk_coords
            )
            self.target_chunk_count = max(1, len(self.landing_chunk_coords))
            self.loading_progress = 0.30
            return

        if not self.island_prepared:
            self.world.process_chunk_streaming(
                prewarm_chunk_callback=lambda chunk: prewarm_chunk_runtime_step(
                    chunk,
                    self.world,
                    self.soil_layer,
                ),
                max_installs=4,
                max_prewarm_steps=1,
            )
            completed, total = self.world.get_streaming_progress(
                self.landing_chunk_coords
            )
            self.loading_label = "Preparing landing area"
            self.loading_note = f"Finishing nearby chunks: {completed}/{total}"
            self.loading_progress = 0.30 + (0.60 * completed / max(1, total))
            if not self.world.is_streaming_area_ready(self.landing_chunk_coords):
                return
            self.island_prepared = True
            self.loading_progress = 0.90
            return

        self.loading_label = "Launching"
        self.loading_note = f"Everything is in place. Landing on {self.world.level_name}..."
        if self.npc_manager is None:
            ensure_player_farm(
                self.world,
                self.soil_layer,
                self.game_state,
            )
            self.npc_manager = NPCManager(
                self.world,
                self.assets,
                count=DEFAULT_NPC_COUNT,
                game_state=self.game_state,
            )
            self.world.start_chunk_streaming(self.world.current_player_chunk)
        self.loading_progress = 1.0
        self.last_player_chunk = self.world.world_to_chunk(self.player.center)
        self.done = True

    def shutdown(self):
        if self.world is not None:
            self.world.shutdown_chunk_streaming()

    def draw(self):
        self.screen.fill(UI_BG)
        if self.stage == "boot":
            self.draw_boot_splash()
            return

        self.draw_menu_background()
        if self.stage in ("title", "setup"):
            self.draw_setup_screen()
        elif self.stage == "settings":
            self.draw_settings_screen()
        elif self.stage == "loading":
            self.draw_loading_screen()

    def draw_scaled_title_art(self, darken=0):
        if self.title_art is None:
            self.draw_background_swells()
            return
        source_w, source_h = self.title_art.get_size()
        scale = max(self.screen_width / source_w, self.screen_height / source_h)
        size = (round(source_w * scale), round(source_h * scale))
        artwork = pygame.transform.smoothscale(self.title_art, size)
        rect = artwork.get_rect(center=(self.screen_width // 2, self.screen_height // 2))
        self.screen.blit(artwork, rect)
        if darken:
            shade = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
            shade.fill((4, 8, 16, darken))
            self.screen.blit(shade, (0, 0))

    def draw_boot_splash(self):
        # The studio splash is intentionally separate from the game menu art.
        # It should read as a clean boot card before the setup screen appears.
        self.screen.fill((0, 0, 0))
        elapsed = max(0, pygame.time.get_ticks() - self.boot_started_at)
        fade_in = min(1.0, elapsed / 650)
        fade_out = min(1.0, max(0, self.boot_duration_ms - elapsed) / 420)
        alpha = round(255 * min(fade_in, fade_out))

        center = (self.screen_width // 2, self.screen_height // 2)
        title = self.big_font.render("Oceans Apart", True, UI_TEXT)
        title.set_alpha(alpha)
        self.screen.blit(title, title.get_rect(center=(center[0], center[1] - 45)))
        subtitle = self.body_font.render("The Last Cure", True, UI_ACCENT)
        subtitle.set_alpha(alpha)
        self.screen.blit(subtitle, subtitle.get_rect(center=(center[0], center[1] + 18)))
        byline = self.body_font.render("A game by Little Squire", True, UI_ACCENT_2)
        byline.set_alpha(alpha)
        self.screen.blit(byline, byline.get_rect(center=(center[0], center[1] + 70)))

    def draw_menu_background(self):
        self.draw_scaled_title_art(darken=188)

    def _draw_setup_row(self, key, rect, label, value="", *, accent=False):
        selected = self.setup_rows[self.setup_focus] == key
        fill = UI_ACCENT if selected else (UI_PANEL_ALT if not accent else (45, 80, 92))
        pygame.draw.rect(self.screen, fill, rect, border_radius=9)
        if not selected:
            pygame.draw.rect(self.screen, (74, 99, 116), rect, 1, border_radius=9)
        color = UI_BG if selected else UI_TEXT
        self.screen.blit(self.small_font.render(label, True, color), (rect.x + 14, rect.y + 10))
        if value:
            value_color = UI_BG if selected else UI_ACCENT_2
            value_surface = self.small_font.render(value, True, value_color)
            self.screen.blit(value_surface, value_surface.get_rect(midright=(rect.right - 14, rect.centery)))
        self.setup_hitboxes[key] = rect

    def draw_setup_screen(self):
        self.setup_hitboxes = {}
        margin = max(24, min(54, self.screen_width // 28))
        header_y = max(22, self.screen_height // 24)
        title = self.title_font.render("Oceans Apart", True, UI_TEXT)
        self.screen.blit(title, (margin, header_y))
        byline = self.small_font.render("The Last Cure  |  Little Squire", True, UI_ACCENT_2)
        self.screen.blit(byline, (margin + 4, header_y + title.get_height() - 4))

        content_top = header_y + title.get_height() + 42
        content_bottom = self.screen_height - margin
        gap = 18
        available_w = self.screen_width - margin * 2 - gap
        left_w = max(500, round(available_w * 0.59))
        if left_w > available_w - 300:
            left_w = max(420, available_w - 300)
        left = pygame.Rect(margin, content_top, left_w, content_bottom - content_top)
        right = pygame.Rect(left.right + gap, content_top, available_w - left_w, left.height)
        for panel in (left, right):
            pygame.draw.rect(self.screen, (*UI_PANEL, 235), panel, border_radius=14)
            pygame.draw.rect(self.screen, UI_PANEL_ALT, panel, 2, border_radius=14)

        section = self.body_font.render("New Game", True, UI_TEXT)
        self.screen.blit(section, (left.x + 24, left.y + 18))
        row_h = 43
        row_gap = 8
        row_w = left.width - 48
        mode_rect = pygame.Rect(left.x + 24, left.y + 66, row_w, row_h)
        self._draw_setup_row("mode", mode_rect, "Mode", self.modes[self.mode_index])
        seed_rect = pygame.Rect(left.x + 24, mode_rect.bottom + row_gap, row_w, row_h)
        seed_value = self.seed_text if self.seed_text else "0"
        self._draw_setup_row("seed", seed_rect, "World seed", seed_value)

        preview_size = min(178, max(116, left.height - 286))
        preview_box = pygame.Rect(left.x + 24, seed_rect.bottom + 18, preview_size, preview_size)
        pygame.draw.rect(self.screen, (9, 18, 29), preview_box, border_radius=12)
        pygame.draw.rect(self.screen, (74, 99, 116), preview_box, 1, border_radius=12)
        if self.assets is not None:
            preview_frames = self.assets.get_character_frames("down_idle", self.customization)
            if preview_frames:
                preview_index = int((pygame.time.get_ticks() / 360) % len(preview_frames))
                target = min(preview_size - 20, 160)
                preview = pygame.transform.scale(preview_frames[preview_index], (target, target))
                self.screen.blit(preview, preview.get_rect(center=preview_box.center))

        appearance_x = preview_box.right + 16
        appearance_w = left.right - 24 - appearance_x
        appearance_y = preview_box.y
        for index, category in enumerate(self.customization_categories):
            rect = pygame.Rect(appearance_x, appearance_y + index * (row_h + row_gap), appearance_w, row_h)
            value = self.customization.get(category)
            value_text = "Default" if value is None else str(value)
            self._draw_setup_row(category, rect, category.title(), value_text)

        start_rect = pygame.Rect(left.x + 24, left.bottom - 62, row_w, 42)
        self._draw_setup_row("start", start_rect, "Start New Game", "Enter")

        saves_title = self.body_font.render("Saved Games", True, UI_TEXT)
        self.screen.blit(saves_title, (right.x + 20, right.y + 18))
        saves_top = right.y + 62
        cards_bottom = right.bottom - 146
        visible_slots = max(1, min(5, (cards_bottom - saves_top) // 67))
        if not self.save_slots:
            empty = self.small_font.render("No saved games yet", True, UI_MUTED)
            self.screen.blit(empty, empty.get_rect(center=(right.centerx, saves_top + 54)))
            empty_rect = pygame.Rect(right.x + 18, saves_top, right.width - 36, 78)
            self.setup_hitboxes["saves"] = empty_rect
        else:
            first = min(max(0, self.save_index - visible_slots + 1), max(0, len(self.save_slots) - visible_slots))
            for visual_index, slot_index in enumerate(range(first, min(len(self.save_slots), first + visible_slots))):
                slot = self.save_slots[slot_index]
                card = pygame.Rect(right.x + 16, saves_top + visual_index * 67, right.width - 32, 57)
                selected = self.setup_rows[self.setup_focus] == "saves" and slot_index == self.save_index
                pygame.draw.rect(self.screen, UI_ACCENT if selected else UI_PANEL_ALT, card, border_radius=9)
                name_color = UI_BG if selected else (UI_TEXT if slot.valid else UI_WARN)
                detail_color = UI_BG if selected else UI_MUTED
                name_surface = self.small_font.render(slot.name, True, name_color)
                self.screen.blit(name_surface, (card.x + 12, card.y + 7))
                detail = f"{slot.mode.title()}  |  Seed {slot.seed}  |  Day {slot.day}"
                if not slot.valid:
                    detail = "Save cannot be read"
                detail_surface = self.tiny_font.render(detail, True, detail_color)
                self.screen.blit(detail_surface, (card.x + 12, card.y + 33))
                self.setup_hitboxes[("save", slot_index)] = card
            self.setup_hitboxes["saves"] = pygame.Rect(right.x + 16, saves_top, right.width - 32, max(57, visible_slots * 67))

        button_w = right.width - 36
        load_rect = pygame.Rect(right.x + 18, right.bottom - 132, button_w, 40)
        settings_rect = pygame.Rect(right.x + 18, load_rect.bottom + 8, (button_w - 8) // 2, 38)
        quit_rect = pygame.Rect(settings_rect.right + 8, settings_rect.y, button_w - settings_rect.width - 8, 38)
        self._draw_setup_row("load", load_rect, "Load Selected Game", "Enter")
        self._draw_setup_row("settings", settings_rect, "Accessibility")
        self._draw_setup_row("quit", quit_rect, "Quit")

        footer = "Up/Down: select   Left/Right: change   Enter: confirm   Esc: quit"
        if self.controller_input.connected:
            footer = "D-pad/Stick: select and change   Cross: confirm   Circle: quit"
        footer_surface = self.tiny_font.render(footer, True, UI_MUTED)
        self.screen.blit(footer_surface, footer_surface.get_rect(bottomright=(self.screen_width - margin, self.screen_height - 6)))
        if self.loading_note:
            note = self.tiny_font.render(self.loading_note, True, UI_WARN)
            self.screen.blit(note, note.get_rect(bottomleft=(margin, self.screen_height - 6)))

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
            footer = "Cross: new voyage    Triangle: load    Square: accessibility"
        else:
            footer = "Enter: new voyage    L: load    S: accessibility"
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

    def draw_settings_screen(self):
        panel = self.draw_center_panel(
            "Accessibility",
            "Settings are saved with your voyage.",
            "Up/Down: choose    Left/Right or Enter/Cross: change    Esc/Circle: back",
            center_text=True,
            size=(680, 460),
        )
        settings = self.game_state.accessibility
        labels = {
            "text_scale": ("Text size", f"{settings.text_scale:g}x"),
            "high_contrast": ("High contrast", "On" if settings.high_contrast else "Off"),
            "reduced_motion": ("Reduced motion", "On" if settings.reduced_motion else "Off"),
            "dialogue_speed": ("Dialogue speed", settings.dialogue_speed.title()),
        }
        for index, setting in enumerate(self.settings_rows):
            row = pygame.Rect(panel.x + 56, panel.y + 138 + index * 58, panel.width - 112, 44)
            selected = index == self.settings_index
            pygame.draw.rect(self.screen, UI_ACCENT if selected else UI_PANEL_ALT, row, border_radius=9)
            color = UI_BG if selected else UI_TEXT
            label, value = labels[setting]
            self.screen.blit(self.small_font.render(label, True, color), (row.x + 14, row.y + 11))
            value_surface = self.small_font.render(value, True, color if selected else UI_ACCENT_2)
            self.screen.blit(value_surface, value_surface.get_rect(midright=(row.right - 14, row.centery)))

    def draw_mode_screen(self):
        panel = self.draw_center_panel(
            "Choose your mode",
            "Follow the opening story or explore a fresh island voyage.",
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
                badge = self.small_font.render("Morning Chores", True, UI_WARN if selected else UI_MUTED)
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

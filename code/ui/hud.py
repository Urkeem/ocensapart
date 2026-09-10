"""In-game HUD drawing for player tools, time, weather, and inventory status."""

import pygame

from gameplay.controls import (
    AXIS_INVENTORY,
    BUTTON_CANCEL,
    BUTTON_CONFIRM,
    BUTTON_DPAD_LEFT,
    BUTTON_DPAD_RIGHT,
    get_controller_input,
)
from ui.inventory import Inventory_UI, Hot_Bar_UI, load_item_icon
from inventory_item import Item
from utils import rp


FARMSTEAD_MARKER_COLOR = (55, 145, 255)


class GameplayHUD:
    def __init__(self, player, screen):
        self.player = player
        self.screen = screen
        self.screen_w, self.screen_h = screen.get_size()
        self.font = pygame.font.Font(rp("font", "LycheeSoda.ttf"), 22)
        self.small_font = pygame.font.Font(rp("font", "LycheeSoda.ttf"), 16)
        self.death_title_font = pygame.font.Font(rp("font", "LycheeSoda.ttf"), 50)

        self.inventory_ui = Inventory_UI(
            player.inventory,
            screen,
            (self.screen_w // 2, self.screen_h // 2),
            player,
        )
        self.hotbar_ui = Hot_Bar_UI(
            player.inventory,
            screen,
            (self.screen_w // 2, int(self.screen_h * 0.92)),
        )

        self.overlay_icons = {}
        self.life_icons = {}
        self.minimap_size = 170
        self.minimap_padding = 14
        self.death_options = ("Exit", "Revive")
        self.death_selection = 1
        self.death_exit_requested = False
        self.death_button_rects = []
        self.notification_text = ""
        self.notification_until = 0

    def load_icon(self, name):
        icon = self.overlay_icons.get(name)
        if icon is not None:
            return icon

        icon = load_item_icon(name, (48, 48))
        if not icon:
            try:
                crop_sheet = pygame.image.load(
                    rp("graphics", "environment", "crops", f"{name}.png")
                ).convert_alpha()
                icon = crop_sheet.subsurface((16, 16, 16, 16)).copy()
                icon = pygame.transform.scale(icon, (48, 48))
            except (FileNotFoundError, ValueError, pygame.error):
                icon = pygame.image.load(
                    rp("graphics", "overlay", f"{name}.png")
                ).convert_alpha()
                icon = pygame.transform.scale(icon, (48, 48))
        self.overlay_icons[name] = icon
        return icon

    def load_life_icon(self, state):
        icon = self.life_icons.get(state)
        if icon is not None:
            return icon

        frame = self.player.assets.life_frames[str(state)]
        icon = self.player.assets.all_sprite_sheet.get_sprite(*frame).convert_alpha()
        icon = pygame.transform.scale(icon, (30, 30))
        self.life_icons[state] = icon
        return icon

    def populate_inventory(self):
        pass

    def get_count(self, name):
        return None

    def sync_counts(self):
        for slot in self.player.inventory.slots:
            name = slot.item.name
            if not name:
                continue
            count = self.get_count(name)
            if count is not None:
                slot.amount = count

    def handle_event(self, event):
        controller_input = getattr(self.player, "controller_input", get_controller_input())
        if not self.player.is_alive:
            self.player.inventory.is_inv = False
            if not self.player.death_animation_complete:
                return
            axis_button = controller_input.menu_navigation_button(event)
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_LEFT, pygame.K_a):
                    self.death_selection = 0
                elif event.key in (pygame.K_RIGHT, pygame.K_d):
                    self.death_selection = 1
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    self.activate_death_option()
            elif event.type == pygame.CONTROLLERBUTTONDOWN:
                if event.button == BUTTON_DPAD_LEFT:
                    self.death_selection = 0
                elif event.button == BUTTON_DPAD_RIGHT:
                    self.death_selection = 1
                elif event.button == BUTTON_CONFIRM:
                    self.activate_death_option()
            elif axis_button == BUTTON_DPAD_LEFT:
                self.death_selection = 0
            elif axis_button == BUTTON_DPAD_RIGHT:
                self.death_selection = 1
            elif event.type == pygame.MOUSEMOTION:
                for index, rect in enumerate(self.death_button_rects):
                    if rect.collidepoint(event.pos):
                        self.death_selection = index
                        break
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for index, rect in enumerate(self.death_button_rects):
                    if rect.collidepoint(event.pos):
                        self.death_selection = index
                        self.activate_death_option()
                        break
            return
        keyboard_toggle = (
            event.type == pygame.KEYDOWN
            and event.key in (pygame.K_i, pygame.K_RETURN)
        )
        controller_toggle = controller_input.is_axis_pressed(event, AXIS_INVENTORY)
        if keyboard_toggle or controller_toggle:
            self.player.inventory.is_inv = not self.player.inventory.is_inv
            return

        if (
            self.player.inventory.is_inv
            and event.type == pygame.CONTROLLERBUTTONDOWN
        ):
            if event.button == BUTTON_CANCEL:
                self.player.inventory.is_inv = False
                self.player.seed_cooldown = max(self.player.seed_cooldown, 0.2)
                # Prevent the same Circle press from becoming a combat dodge
                # later in the session event pipeline.
                self.player.action_lock_timer = max(self.player.action_lock_timer, 0.1)
            else:
                self.inventory_ui.handle_controller_button(event.button)
            return


        if self.player.inventory.is_inv:
            axis_button = controller_input.menu_navigation_button(event)
            if axis_button is not None:
                self.inventory_ui.handle_controller_button(axis_button)
                return

        if self.player.inventory.is_inv and event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.inventory_ui.handle_click((1, event.pos))

    def activate_death_option(self):
        option = self.death_options[self.death_selection]
        if option == "Revive":
            self.player.revive()
            self.death_selection = 1
        else:
            self.death_exit_requested = True

    def draw_death_panel(self):
        if not self.player.death_animation_complete:
            return

        shade = pygame.Surface((self.screen_w, self.screen_h), pygame.SRCALPHA)
        shade.fill((3, 5, 10, 190))
        self.screen.blit(shade, (0, 0))

        panel = pygame.Rect(0, 0, 430, 220)
        panel.center = (self.screen_w // 2, self.screen_h // 2)
        pygame.draw.rect(self.screen, (7, 10, 16, 190), panel.move(0, 5), border_radius=14)
        pygame.draw.rect(self.screen, (24, 28, 39), panel, border_radius=14)
        pygame.draw.rect(self.screen, (154, 49, 49), panel, 3, border_radius=14)

        title = self.death_title_font.render("YOU DIED", True, (236, 226, 218))
        self.screen.blit(title, title.get_rect(midtop=(panel.centerx, panel.y + 24)))

        button_size = (150, 52)
        gap = 22
        start_x = panel.centerx - (button_size[0] * 2 + gap) // 2
        button_y = panel.y + 118
        self.death_button_rects = [
            pygame.Rect(start_x + index * (button_size[0] + gap), button_y, *button_size)
            for index in range(2)
        ]
        for index, (label, rect) in enumerate(zip(self.death_options, self.death_button_rects)):
            selected = index == self.death_selection
            fill = (126, 43, 43) if selected else (37, 44, 58)
            border = (239, 185, 94) if selected else (103, 116, 135)
            pygame.draw.rect(self.screen, fill, rect, border_radius=8)
            pygame.draw.rect(self.screen, border, rect, 2, border_radius=8)
            text = self.font.render(label, True, (244, 244, 242))
            self.screen.blit(text, text.get_rect(center=rect.center))

        hint = self.small_font.render(
            "Left / Right to choose    Enter / Cross to confirm",
            True,
            (177, 186, 199),
        )
        self.screen.blit(hint, hint.get_rect(midbottom=(panel.centerx, panel.bottom - 12)))

    def get_selected_hotbar_index(self):
        tool_count = len(self.player.tools)
        if self.player.selected_tool in self.player.tools:
            return self.player.tools.index(self.player.selected_tool)
        if self.player.selected_seed in self.player.seeds:
            return tool_count + self.player.seeds.index(self.player.selected_seed)
        return 0

    def draw_selected_overlay(self):
        placeable = self.player.inventory.get_selected_placeable()
        active_name = placeable.name if placeable is not None else self.player.selected_tool
        tool_icon = self.load_icon(active_name)
        seed_icon = self.load_icon(self.player.selected_seed)

        tool_rect = tool_icon.get_rect(midbottom=(self.screen_w - 64, self.screen_h - 42))
        seed_rect = seed_icon.get_rect(midbottom=(self.screen_w - 124, self.screen_h - 42))

        pygame.draw.rect(self.screen, (12, 18, 29), tool_rect.inflate(16, 16), border_radius=8)
        pygame.draw.rect(self.screen, (76, 145, 201), tool_rect.inflate(16, 16), 2, border_radius=8)
        pygame.draw.rect(self.screen, (12, 18, 29), seed_rect.inflate(16, 16), border_radius=8)
        pygame.draw.rect(self.screen, (209, 177, 87), seed_rect.inflate(16, 16), 2, border_radius=8)

        self.screen.blit(tool_icon, tool_rect)
        self.screen.blit(seed_icon, seed_rect)

        if placeable is not None:
            tool_status = str(self.player.inventory.count_item(placeable.name))
        else:
            durability = self.player.tool_durability.get(self.player.selected_tool, 0)
            maximum = self.player.tool_max_durability.get(self.player.selected_tool, 0)
            tool_status = f"{durability}/{maximum}"
            if self.player.selected_tool == "water":
                tool_status = f"{self.player.water_amount}/{self.player.water_capacity}  {tool_status}"
        status_text = self.small_font.render(tool_status, True, (236, 240, 245))
        self.screen.blit(
            status_text,
            status_text.get_rect(midtop=(tool_rect.centerx, tool_rect.bottom + 2)),
        )

        seed_count = self.font.render(str(self.player.seed_inventory.get(self.player.selected_seed, 0)), True, (236, 240, 245))
        self.screen.blit(seed_count, seed_count.get_rect(midtop=(seed_rect.centerx, seed_rect.bottom + 2)))

    def show_notification(self, text, duration_ms=2400):
        self.notification_text = str(text)
        self.notification_until = pygame.time.get_ticks() + int(duration_ms)

    def draw_health_panel(self):
        max_health = max(1, int(getattr(self.player, "max_health", 1)))
        health = max(0, min(max_health, int(getattr(self.player, "health", max_health))))
        panel = pygame.Rect(14, 14, 270, 58)

        pygame.draw.rect(self.screen, (7, 10, 16, 150), panel.move(0, 3), border_radius=8)
        pygame.draw.rect(self.screen, (18, 26, 38, 226), panel, border_radius=8)
        pygame.draw.rect(self.screen, (209, 177, 87), panel, 2, border_radius=8)
        hp_label = self.font.render("HP", True, (242, 236, 224))
        self.screen.blit(hp_label, hp_label.get_rect(midleft=(panel.x + 14, panel.centery)))
        bar = pygame.Rect(panel.x + 58, panel.y + 15, 190, 28)
        pygame.draw.rect(self.screen, (53, 24, 29), bar, border_radius=7)
        fill_width = round(bar.width * (health / max_health))
        if fill_width > 0:
            pygame.draw.rect(
                self.screen,
                (194, 48, 58),
                pygame.Rect(bar.x, bar.y, fill_width, bar.height),
                border_radius=7,
            )
        pygame.draw.rect(self.screen, (113, 124, 141), bar, 2, border_radius=7)
        value = self.small_font.render(f"{health}/{max_health}", True, (250, 244, 236))
        self.screen.blit(value, value.get_rect(center=bar.center))

    def draw_coin_panel(self):
        panel = pygame.Rect(self.screen_w - 174, 14, 160, 54)
        pygame.draw.rect(self.screen, (7, 10, 16, 150), panel.move(0, 3), border_radius=8)
        pygame.draw.rect(self.screen, (18, 26, 38, 226), panel, border_radius=8)
        pygame.draw.rect(self.screen, (209, 177, 87), panel, 2, border_radius=8)
        icon = self.load_icon("coin")
        icon = pygame.transform.scale(icon, (34, 34))
        self.screen.blit(icon, icon.get_rect(midleft=(panel.x + 12, panel.centery)))
        amount = self.font.render(str(self.player.coins), True, (247, 224, 139))
        self.screen.blit(amount, amount.get_rect(midleft=(panel.x + 58, panel.centery)))

    def draw_weather_panel(self, weather):
        if weather is None:
            return
        panel = pygame.Rect(self.screen_w - 224, 78, 210, 66)
        pygame.draw.rect(self.screen, (7, 10, 16, 150), panel.move(0, 3), border_radius=8)
        pygame.draw.rect(self.screen, (18, 26, 38, 226), panel, border_radius=8)
        pygame.draw.rect(self.screen, (76, 145, 201), panel, 2, border_radius=8)
        title = self.font.render(
            f"{weather.time.formatted()}  {weather.weather}",
            True,
            (236, 240, 245),
        )
        subtitle = self.small_font.render(
            f"{weather.current_season}  Day {weather.time.day}",
            True,
            (190, 204, 214),
        )
        self.screen.blit(title, (panel.x + 12, panel.y + 8))
        self.screen.blit(subtitle, (panel.x + 12, panel.y + 37))

    def draw_notification(self):
        if not self.notification_text or pygame.time.get_ticks() >= self.notification_until:
            return
        text = self.small_font.render(self.notification_text, True, (244, 240, 225))
        rect = text.get_rect(midtop=(self.screen_w // 2, 18)).inflate(24, 14)
        pygame.draw.rect(self.screen, (18, 26, 38), rect, border_radius=8)
        pygame.draw.rect(self.screen, (209, 177, 87), rect, 2, border_radius=8)
        self.screen.blit(text, text.get_rect(center=rect.center))

    def _minimap_rect(self):
        return pygame.Rect(
            self.screen_w - self.minimap_size - self.minimap_padding,
            max(self.minimap_padding, self.screen_h - self.minimap_size - 112),
            self.minimap_size,
            self.minimap_size,
        )

    def _minimap_tile_bounds(self, world):
        chunk_w, chunk_h = world.chunk_size
        coords = world.get_level_chunk_coords()
        min_chunk_x = min(coord[0] for coord in coords)
        max_chunk_x = max(coord[0] for coord in coords)
        min_chunk_y = min(coord[1] for coord in coords)
        max_chunk_y = max(coord[1] for coord in coords)
        return (
            min_chunk_x * chunk_w,
            min_chunk_y * chunk_h,
            (max_chunk_x + 1) * chunk_w,
            (max_chunk_y + 1) * chunk_h,
        )

    def _minimap_point(self, world, rect, world_pixel_pos):
        min_x, min_y, max_x, max_y = self._minimap_tile_bounds(world)
        tile_x = world_pixel_pos[0] / world.tile_size
        tile_y = world_pixel_pos[1] / world.tile_size
        width = max(1, max_x - min_x)
        height = max(1, max_y - min_y)
        return (
            rect.x + int(((tile_x - min_x) / width) * rect.width),
            rect.y + int(((tile_y - min_y) / height) * rect.height),
        )

    def _enemy_positions(self, npc_manager):
        if npc_manager is None:
            return []
        positions = []
        for npc in getattr(npc_manager, "npcs", []):
            is_enemy = (
                getattr(npc, "is_enemy", False)
                or getattr(npc, "hostile", False)
                or getattr(npc, "faction", None) == "enemy"
                or getattr(npc, "name", "") == "enemy"
            )
            if is_enemy:
                if hasattr(npc, "center"):
                    positions.append(npc.center)
                elif hasattr(npc, "rect"):
                    positions.append(npc.rect.center)
        return positions

    def _house_positions(self, world):
        positions = []
        if world is None:
            return positions

        for chunk in world.loaded_chunks.values():
            for record in chunk.props:
                if not (isinstance(record, dict) and record.get("type") == "house"):
                    continue
                if record.get("scene") == "farmstead":
                    continue

                world_pos = record.get("world_pos")
                if not world_pos:
                    continue

                render_size = record.get("render_size")
                if render_size:
                    positions.append((
                        world_pos[0] + render_size[0] // 2,
                        world_pos[1] + render_size[1] // 2,
                    ))
                else:
                    footprint = record.get("footprint", (1, 1))
                    positions.append((
                        world_pos[0] + (footprint[0] * world.tile_size) // 2,
                        world_pos[1] + (footprint[1] * world.tile_size) // 2,
                    ))
        return positions

    @staticmethod
    def _farmstead_positions(world):
        """Return farm markers, including guaranteed farms not loaded yet."""
        positions = []
        chunk_width, chunk_height = world.chunk_size
        farmstead_coords = list(getattr(world, "farmstead_chunks", ()))
        known_coords = set(farmstead_coords)
        for chunk_coord, chunk in world.loaded_chunks.items():
            if chunk_coord in known_coords:
                continue
            if any(
                isinstance(record, dict)
                and record.get("type") == "house"
                and record.get("scene") == "farmstead"
                for record in chunk.props
            ):
                farmstead_coords.append(chunk_coord)
                known_coords.add(chunk_coord)

        for chunk_coord in farmstead_coords:
            chunk = world.loaded_chunks.get(chunk_coord)
            pen = None
            if chunk is not None:
                pen = next(
                    (
                        record
                        for record in chunk.props
                        if isinstance(record, dict)
                        and record.get("type") == "animal_pen"
                    ),
                    None,
                )
            if pen is not None:
                left, top, width, height = pen["local_rect"]
                world_tile_x = chunk.origin_tile[0] + left + width / 2
                world_tile_y = chunk.origin_tile[1] + top + height / 2
            else:
                world_tile_x = chunk_coord[0] * chunk_width + chunk_width / 2
                world_tile_y = chunk_coord[1] * chunk_height + chunk_height / 2
            positions.append((
                world_tile_x * world.tile_size,
                world_tile_y * world.tile_size,
            ))
        return positions

    def draw_minimap(self, world, npc_manager=None):
        if world is None:
            return

        rect = self._minimap_rect()
        map_surface = pygame.Surface(rect.size, pygame.SRCALPHA)
        map_surface.fill((8, 14, 22, 218))

        min_x, min_y, max_x, max_y = self._minimap_tile_bounds(world)
        total_tiles_w = max(1, max_x - min_x)
        total_tiles_h = max(1, max_y - min_y)

        for chunk in world.loaded_chunks.values():
            chunk_w, chunk_h = chunk.chunk_size
            for local_y in range(chunk_h):
                for local_x in range(chunk_w):
                    idx = chunk.get_index(local_x, local_y)
                    terrain = chunk.layers["terrain"][idx]
                    if terrain == -1:
                        continue

                    world_tile_x, world_tile_y = chunk.get_world_tile(local_x, local_y)
                    px = int(((world_tile_x - min_x) / total_tiles_w) * rect.width)
                    py = int(((world_tile_y - min_y) / total_tiles_h) * rect.height)
                    next_px = int(((world_tile_x + 1 - min_x) / total_tiles_w) * rect.width)
                    next_py = int(((world_tile_y + 1 - min_y) / total_tiles_h) * rect.height)
                    tile_rect = pygame.Rect(
                        px,
                        py,
                        max(1, next_px - px),
                        max(1, next_py - py),
                    )
                    color = (215, 194, 118) if terrain == 0 else (75, 140, 78)
                    pygame.draw.rect(map_surface, color, tile_rect)

        pygame.draw.rect(self.screen, (7, 10, 16, 180), rect.move(0, 3), border_radius=8)
        pygame.draw.rect(self.screen, (18, 26, 38), rect.inflate(8, 8), border_radius=8)
        pygame.draw.rect(self.screen, (76, 145, 201), rect.inflate(8, 8), 2, border_radius=8)
        self.screen.blit(map_surface, rect)

        player_pos = self._minimap_point(world, rect, self.player.center)
        pygame.draw.circle(self.screen, (70, 235, 105), player_pos, 4)
        pygame.draw.circle(self.screen, (7, 10, 16), player_pos, 5, 1)

        for house_pos in self._house_positions(world):
            dot_pos = self._minimap_point(world, rect, house_pos)
            pygame.draw.circle(self.screen, (230, 60, 65), dot_pos, 3)

        for farmstead_pos in self._farmstead_positions(world):
            dot_pos = self._minimap_point(world, rect, farmstead_pos)
            pygame.draw.circle(self.screen, FARMSTEAD_MARKER_COLOR, dot_pos, 5)
            pygame.draw.circle(self.screen, (7, 10, 16), dot_pos, 6, 1)

        for enemy_pos in self._enemy_positions(npc_manager):
            dot_pos = self._minimap_point(world, rect, enemy_pos)
            pygame.draw.circle(self.screen, (230, 60, 65), dot_pos, 3)

        label = self.small_font.render(world.level_name, True, (236, 240, 245))
        self.screen.blit(label, label.get_rect(topleft=(rect.x + 8, rect.y + 6)))

    def draw(self, world=None, npc_manager=None, weather=None):
        self.hotbar_ui.display_hot_bar()
        self.hotbar_ui.select_slot(self.get_selected_hotbar_index())
        self.draw_health_panel()
        self.draw_coin_panel()
        self.draw_weather_panel(weather)
        self.draw_minimap(world, npc_manager)
        self.draw_selected_overlay()

        if self.player.inventory.is_inv:
            self.inventory_ui.display_inventory()
            if self.inventory_ui.grabbing:
                self.inventory_ui.grab_item()
        self.draw_death_panel()
        self.draw_notification()

"""In-game HUD drawing for player tools, time, weather, and inventory status."""

import pygame

from ui.inventory import Inventory_UI, Hot_Bar_UI, load_item_icon
from inventory_item import Item
from utils import rp


class GameplayHUD:
    def __init__(self, player, screen):
        self.player = player
        self.screen = screen
        self.screen_w, self.screen_h = screen.get_size()
        self.font = pygame.font.Font(rp("font", "LycheeSoda.ttf"), 22)
        self.small_font = pygame.font.Font(rp("font", "LycheeSoda.ttf"), 16)

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

    def load_icon(self, name):
        icon = self.overlay_icons.get(name)
        if icon is not None:
            return icon

        icon = load_item_icon(name, (48, 48))
        if not icon:
            icon = pygame.image.load(rp("graphics", "overlay", f"{name}.png")).convert_alpha()
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
        if name in self.player.seed_inventory:
            return self.player.seed_inventory[name]
        if name in self.player.harvested_crops:
            return self.player.harvested_crops[name]
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
        if event.type == pygame.KEYDOWN and event.key in (pygame.K_i, pygame.K_RETURN):
            self.player.inventory.is_inv = not self.player.inventory.is_inv

        if self.player.inventory.is_inv and event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.inventory_ui.handle_click((1, event.pos))

    def get_selected_hotbar_index(self):
        tool_count = len(self.player.tools)
        if self.player.selected_tool in self.player.tools:
            return self.player.tools.index(self.player.selected_tool)
        if self.player.selected_seed in self.player.seeds:
            return tool_count + self.player.seeds.index(self.player.selected_seed)
        return 0

    def draw_selected_overlay(self):
        tool_icon = self.load_icon(self.player.selected_tool)
        seed_icon = self.load_icon(self.player.selected_seed)

        tool_rect = tool_icon.get_rect(midbottom=(self.screen_w - 64, self.screen_h - 42))
        seed_rect = seed_icon.get_rect(midbottom=(self.screen_w - 124, self.screen_h - 42))

        pygame.draw.rect(self.screen, (12, 18, 29), tool_rect.inflate(16, 16), border_radius=8)
        pygame.draw.rect(self.screen, (76, 145, 201), tool_rect.inflate(16, 16), 2, border_radius=8)
        pygame.draw.rect(self.screen, (12, 18, 29), seed_rect.inflate(16, 16), border_radius=8)
        pygame.draw.rect(self.screen, (209, 177, 87), seed_rect.inflate(16, 16), 2, border_radius=8)

        self.screen.blit(tool_icon, tool_rect)
        self.screen.blit(seed_icon, seed_rect)

        seed_count = self.font.render(str(self.player.seed_inventory.get(self.player.selected_seed, 0)), True, (236, 240, 245))
        self.screen.blit(seed_count, seed_count.get_rect(midtop=(seed_rect.centerx, seed_rect.bottom + 2)))

    def draw_life_panel(self):
        max_health = max(1, int(getattr(self.player, "max_health", 1)))
        health = max(0, min(max_health, int(getattr(self.player, "health", max_health))))
        heart_gap = 6
        icon_size = 30
        panel_w = (icon_size * max_health) + (heart_gap * (max_health - 1)) + 24
        panel_h = 48
        panel = pygame.Rect(self.screen_w - panel_w - 14, 14, panel_w, panel_h)

        pygame.draw.rect(self.screen, (7, 10, 16, 150), panel.move(0, 3), border_radius=8)
        pygame.draw.rect(self.screen, (18, 26, 38, 226), panel, border_radius=8)
        pygame.draw.rect(self.screen, (209, 177, 87), panel, 2, border_radius=8)

        start_x = panel.x + 12
        y = panel.y + (panel.height - icon_size) // 2
        for index in range(max_health):
            state = 1 if index < health else 3
            icon = self.load_life_icon(state)
            self.screen.blit(icon, (start_x + index * (icon_size + heart_gap), y))

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

        for enemy_pos in self._enemy_positions(npc_manager):
            dot_pos = self._minimap_point(world, rect, enemy_pos)
            pygame.draw.circle(self.screen, (230, 60, 65), dot_pos, 3)

        label = self.small_font.render(world.level_name, True, (236, 240, 245))
        self.screen.blit(label, label.get_rect(topleft=(rect.x + 8, rect.y + 6)))

    def draw(self, world=None, npc_manager=None):
        self.hotbar_ui.display_hot_bar()
        self.hotbar_ui.select_slot(self.get_selected_hotbar_index())
        self.draw_life_panel()
        self.draw_minimap(world, npc_manager)
        self.draw_selected_overlay()

        if self.player.inventory.is_inv:
            self.inventory_ui.display_inventory()
            if self.inventory_ui.grabbing:
                self.inventory_ui.grab_item()

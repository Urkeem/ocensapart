"""Shared runtime and UI constants for the active game."""

import pygame


FPS = 60
# Development overlays render changing text and collision rectangles every frame.
# Enable this only when inspecting chunks or collisions.
SHOW_DEBUG_OVERLAY = False
BASE_LAND_TILESET_FILE = "Tilesets/land.png"
PATH_TILESET_FILE = "Tilesets/path.png"
DEEP_OCEAN_TILESET_FILE = "Tilesets/ocean.png"
DOCK_TILESET_FILE = "Tilesets/dock.png"
FENCE_TILESET_FILE = "graphics/sprites/environment/fence/fence.png"
AUTOTILED_BIOMES = {1, 2, 3, 4, 6, 7, 9}
DEEP_OCEAN_THRESHOLD = 0.30
BACKGROUND_COLOR = (20, 20, 30)
PLAYER_COLOR = (230, 70, 70)
TEXT_COLOR = (255, 255, 255)
TILESET_SOURCE_TILE_SIZE = 32
PATH_SOURCE_TILE_SIZE = 32
DOCK_SOURCE_TILE_SIZE = 64
FENCE_SOURCE_TILE_SIZE = 32
WORLD_SCALE = 2

UI_BG = (11, 16, 26)
UI_PANEL = (22, 30, 45)
UI_PANEL_ALT = (30, 40, 60)
UI_ACCENT = (76, 145, 201)
UI_ACCENT_2 = (209, 177, 87)
UI_TEXT = (236, 240, 245)
UI_MUTED = (170, 180, 190)
UI_WARN = (135, 135, 145)

DEFAULT_CHUNK_SIZE = (24, 24)
DEFAULT_ACTIVE_RADIUS = 1
DEFAULT_TILE_SIZE = TILESET_SOURCE_TILE_SIZE * 2
DEFAULT_NPC_COUNT = 35

WORLD_HINT_KEYS = {
    pygame.K_SPACE,
    pygame.K_LCTRL,
    pygame.K_RCTRL,
    pygame.K_q,
    pygame.K_e,
    pygame.K_p,
}
WORLD_HINT_ACK_KEYS = {
    "select_resource_tool": {pygame.K_q},
    "break_resource": {pygame.K_SPACE},
    "collect_loose_item": {pygame.K_e, pygame.K_p},
    "select_fishing_rod": {pygame.K_q},
    "cast_fishing_line": {pygame.K_SPACE},
    "reel_fishing_line": {pygame.K_SPACE},
}

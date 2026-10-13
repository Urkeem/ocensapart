"""Central registry for sprite sheets and frame rectangles used by the game."""

from pathlib import Path
import pygame

from sprites import SpriteSheet
from utils import rp


CHARACTER_PART_FOLDERS = {
    "skin": "skins",
    "clothes": "clothes",
    "hair": "hair",
    "weapon": "weapons",
    # Offhand equipment uses the same authored 64px sheets. It remains an
    # internal option for now so guards can carry a sword and shield together.
    "offhand": "weapons",
}
CHARACTER_LAYER_ORDER = ("skin", "clothes", "hair")
# The tool sheet is authored against the same 64x64 frame grid as the
# character parts. Swinging tools share the axe/hoe body motion, while the
# fishing actions use their own cast, wait, and reel frames on that sheet.
TOOL_LAYER_ACTIONS = {
    "hoe", "axe", "water", "seed", "initial_cast", "cast", "fish", "reel_in", "reel"
}

NPC_FRAME_SIZE = 32
NPC_EXCLUDED_ROLES = {"cat", "dog"}
NPC_WALK_DIRECTIONS = ("down", "right", "up", "left")
NPC_EXTRA_ANIMATIONS = {
    "bard": {
        "bard_idle": (0, 160, 1),
        "singing": (0, 192, 4),
    },
    "dancer": {
        "dancer_idle": (0, 160, 1),
        "dancing": (0, 224, 3),
    },
    "merchant": {
        "sitting": (0, 160, 2),
    },
    "king": {
        "king_idle": (0, 224, 2),
    },
    "queen": {
        "queen_idle": (0, 224, 2),
    },
    "chef": {
        "drinking_right": (0, 160, 4),
        "drinking_left": (0, 192, 4),
    },
    "nun": {
        "praying_down": (0, 160, 2),
        "kneeling_prayer_up": (0, 192, 2),
    },
}
NPC_DEFAULT_IDLE_BY_ROLE = {
    "bard": "bard_idle",
    "dancer": "dancer_idle",
    "merchant": "sitting",
    "king": "king_idle",
    "queen": "queen_idle",
}
NPC_SPECIAL_STATES_BY_ROLE = {
    "bard": (("singing", "down"),),
    "dancer": (("dancing", "down"),),
    "chef": (
        ("drinking_right", "right"),
        ("drinking_left", "left"),
    ),
    "nun": (
        ("praying_down", "down"),
        ("kneeling_prayer_up", "up"),
    ),
}

DOORS = {
    "abandoned": (89, 149, 32, 43),
    "beachcabin": (33, 97, 32, 30),
    "fishermanhut": (31, 69, 32, 31),
    "hut": (31, 92, 36, 35),
    "simplehouse": (31, 92, 36, 35),
    "stonehut": (31, 92, 36, 35),
    "thatchhut": (31, 92, 36, 35),
    "woodstall": (25, 87, 96, 45),
    "blacksmith": (39, 129, 46, 31),
    "farmhouse": (29, 89, 32, 35),
    "merchanthouse1": (359, 151, 51, 62),
    "merchanthouse2": (76, 170, 47, 58),
    "merchanthouse3": (153, 216, 32, 15),
    "regular": (97, 183, 51, 71),
    "secondaryhouse": (18, 180, 132, 44),
    "secondaryhouse2": (157, 172, 83, 48),
    "bakerystewhouse": (133, 184, 32, 40),
    "castle": (232, 401, 78, 68),
    "countinghouse": (0, 160, 28, 39),
    "fort": (72, 401, 78, 68),
    "harbouroffice": (0, 117, 32, 74),
    "pawnshop": (111, 245, 32, 64),
    "portcouncilchamber": (99, 264, 38, 42),
    "tavern": (221, 191, 35, 54),
    "warehouse1": (122, 200, 39, 66),
    "warehouse2": (194, 141, 36, 66),
    "warehouse3": (72, 254, 24, 56)
}

class LoadAssets:
    def __init__(self):
        # SpriteSheet instances point at source images; the dictionaries below
        # describe sub-rectangles inside those sheets.
        self.font_path = "font/LycheeSoda.ttf"
        self.all_sprite_sheet = SpriteSheet(
            "graphics/game_ui", "all_ui.png")
        self.time_sprite_sheet = SpriteSheet(
            "graphics/game_ui", "weather_ui.png")
        self.weather_time_sprite_sheet = SpriteSheet(
            "graphics/game_ui", "weather_icons_big_ui.png")
        self.temp_sprite_sheet = SpriteSheet(
            "graphics/game_ui", "thermometer_ui.png")
        self.character_parts = self.load_character_parts()
        self.guard_parts = self.load_guard_parts()
        self.farm_tool_sheet = SpriteSheet("graphics", "character", "tools", "farm.png")
        self.character_options = {
            part_name: sorted(
                part_sheets.keys(),
                key=lambda value: (0, int(value)) if value.isdigit() else (1, value),
            )
            for part_name, part_sheets in self.character_parts.items()
        }
        self.default_character_customization = {
            "skin": self.character_options.get("skin", ["1"])[0] if self.character_options.get("skin") else None,
            "clothes": self.character_options.get("clothes", [None])[0] if self.character_options.get("clothes") else None,
            "hair": self.character_options.get("hair", [None])[0] if self.character_options.get("hair") else None,
            "weapon": None,
            "offhand": None,
        }
        self._character_frame_cache = {}
        self._guard_frame_cache = {}
        self.npc_profiles = self.load_npc_profiles()
        self._npc_frame_cache = {}
        self.all_trees_sprites = SpriteSheet("graphics/environment/trees", "all_trees.png")
        self.character_portrait_sprite_sheet = SpriteSheet("graphics/character", "Portraits.png")
        # self.market_sprite_sheet = SpriteSheet("graphics/environment/buildings", "market.png")
        self.environment_props1_sprite_sheet = SpriteSheet("graphics/environment", "Props.png")
        self.water_sprites = SpriteSheet("Tilesets/", "water.png")

        self.sprite_data = {
            "inv_bg": (434, 979, 168, 60),
            "slot": (10, 155, 28, 28),
            "player_frame": (357, 245, 38, 38),
            "progress_bar_bg": (534, 369, 35, 12),
            "progress_bar": (584, 371, 30, 8),
            "dialogue_panel": (114, 935, 124, 35)
        }
        self.character_portraits = {
            "p_0": (0, 0, 32, 32),
            "p_1": (32, 0, 32, 32),
            "p_2": (64, 0, 32, 32),
            "p_3": (96, 0, 32, 32),
            "p_4": (128, 0, 32, 32),
            "p_5": (160, 0, 32, 32),
            "p_6": (192, 0, 32, 32),
            "p_7": (224, 0, 32, 32),
            "p_8": (256, 0, 32, 32),
            "p_9": (288, 0, 32, 32),
        }

        self.time_frame_data = {
            "time_frame": (119, 7, 92, 50),
            "date_hour_frame": (263, 100, 51, 24),
            "time": (67, 103, 22, 34)
        }
        self.temp_frame_data = {
            "h1": (5, 3, 20, 42),
            "h2": (37, 3, 20, 42),
            "h3": (69, 3, 20, 42),
            "h4": (101, 3, 20, 42),
            "h5": (133, 3, 20, 42),
            "c1": (5, 51, 20, 42),
            "c2": (37, 51, 20, 42),
            "c3": (69, 51, 20, 42),
            "c4": (101, 51, 20, 42),
            "c5": (133, 51, 20, 42),
        }

        self.star_frames = {
            "1": (819, 707, 25, 24),
            "2": (851, 707, 25, 24)
        }
        self.life_frames = {
            "1": (820, 772, 24, 23),
            "2": (852, 772, 24, 23),
            "3": (884, 772, 24, 23)
        }

        self.weather_bg_anim = [(55, 295, 34, 34), (247, 295, 34, 34), (391, 295, 34, 34)]
        self.weather_anim = [
            (55, 151, 34, 34),
            (247, 151, 34, 34),
            (344, 151, 34, 34)
        ]
        self.time_ticker_anim = [
            (336, 1, 16, 13),
            (336, 34, 16, 13),
            (336, 66, 16, 13),
        ]

        self.character_animations = {
            # Base animations
            "down": [(0, 256, 64, 64), (64, 256, 64, 64), (128, 256, 64, 64), (192, 256, 64, 64), (256, 256, 64, 64), (320, 256, 64, 64)],
            "up": [(0, 320, 64, 64), (64, 320, 64, 64), (128, 320, 64, 64), (192, 320, 64, 64), (256, 320, 64, 64), (320, 320, 64, 64)],
            "left": [(0, 448, 64, 64), (64, 448, 64, 64), (128, 448, 64, 64),(192, 448, 64, 64), (256, 448, 64, 64), (320, 448, 64, 64)],
            "right": [(0, 384, 64, 64), (64, 384, 64, 64), (128, 384, 64, 64), (192, 384, 64, 64), (256, 384, 64, 64), (320, 384, 64, 64)],


            "down_idle": [(64, 768, 64, 64), (128, 768, 64, 64)],
            "up_idle": [(64, 832, 64, 64),(128, 832, 64, 64)],
            "left_idle": [(64, 960, 64, 64), (128, 960, 64, 64)],
            "right_idle": [(64, 896, 64, 64), (128, 896, 64, 64)],

            # Jump
            "down_jump": [(256, 0, 64, 64), (320, 0, 64, 64), (384, 0, 64, 64), (0, 0, 64, 64)],
            "up_jump": [(256, 64, 64, 64), (320, 64, 64, 64), (384, 64, 64, 64), (0, 64, 64, 64)],
            "right_jump": [(256, 128, 64, 64), (320, 128, 64, 64), (384, 128, 64, 64), (0, 128, 64, 64)],
            "left_jump": [(256, 192, 64, 64), (320, 192, 64, 64), (384, 192, 64, 64), (0, 192, 64, 64)],

            # Splint
            "down_splint": [(384, 256, 64, 64), (448, 256, 64, 64)],
            "up_splint": [(384, 320, 64, 64), (448, 320, 64, 64)],
            "right_splint": [(384, 384, 64, 64), (448, 384, 64, 64)],
            "left_splint": [(384, 448, 64, 64), (448, 448, 64, 64)],

            # Dead with spear
            "down_dead_spear": [(896, 768, 64, 64), (960, 768, 64, 64)],
            "up_dead_spear": [(896, 832, 64, 64), (960, 832, 64, 64)],
            "right_dead_spear": [(896, 896, 64, 64), (960, 896, 64, 64)],
            "left_dead_spear": [(896, 960, 64, 64), (960, 960, 64, 64)],

            # Dead with sword
            "down_dead_sword": [(1408, 1024, 64, 64), (1472, 1024, 64, 64)],
            "up_dead_sword": [(1408, 1088, 64, 64), (1472, 1088, 64, 64)],
            "right_dead_sword": [(1408, 1152, 64, 64), (1472, 1152, 64, 64)],
            "left_dead_sword": [(1408, 1216, 64, 64), (1472, 1216, 64, 64)],

            # Hurt with spear
            "down_hurt_spear": [(832, 768, 64, 64)],
            "up_hurt_spear": [(832, 832, 64, 64)],
            "right_hurt_spear": [(832, 896, 64, 64)],
            "left_hurt_spear": [(832, 960, 64, 64)],

            # Hurt with sword
            "down_hurt_sword": [(1408, 1024, 64, 64)],
            "up_hurt_sword": [(1408, 1088, 64, 64)],
            "right_hurt_sword": [(1408, 1152, 64, 64)],
            "left_hurt_sword": [(1408, 1216, 64, 64)],

             # draw and sheath/ parry / lunge / crouch with weapon
            "down_weapon_idle": [(1024, 0, 64, 64), (1088, 0, 64, 64), (1152, 0, 64, 64), (1216, 0, 64, 64)],
            "down_weapon_stealth_move":[(1280, 0, 64, 64), (1344, 0, 64, 64), (1408, 0, 64, 64), (1472, 0, 64, 64)],
            "down_weapon_retreat": [(1088, 256, 64, 64)],
            "down_weapon_lunge": [(1152, 256, 64, 64)],
            "down_crouch": [(1024, 256, 64, 64)],

            "down_spear_draw": [(512, 768, 64, 64), (576, 768, 64, 64), (640, 768, 64, 64)],
            "down_spear_parry": [(704, 768, 64, 64)],
            "down_spear_dodge": [(768, 768, 64, 64)],

            "down_sword_draw":[(1024, 1024, 64, 64), (1088, 1024, 64, 64), (1152, 1024, 64, 64)],
            "down_sword_parry": [(1216, 1024, 64, 64)],
            "down_sword_dodge": [(1280, 1024, 64, 64)],


            "up_weapon_idle": [(1024, 64, 64, 64), (1088, 64, 64, 64), (1152, 64, 64, 64), (1216, 64, 64, 64)],
            "up_weapon_stealth_move":[(1280, 64, 64, 64), (1344, 64, 64, 64), (1408, 64, 64, 64), (1472, 64, 64, 64)],
            "up_weapon_retreat": [(1088, 320, 64, 64)],
            "up_weapon_lunge": [(1152, 320, 64, 64)],
            "up_crouch": [(1024, 320, 64, 64)],

            "up_spear_draw": [(512, 832, 64, 64), (576, 832, 64, 64), (640, 832, 64, 64)],
            "up_spear_parry": [(704, 832, 64, 64)],
            "up_spear_dodge": [(768, 832, 64, 64)],

            "up_sword_draw": [(1024, 1088, 64, 64), (1088, 1088, 64, 64), (1152, 1088, 64, 64)],
            "up_sword_parry": [(1216, 1088, 64, 64)],
            "up_sword_dodge": [(1280, 1088, 64, 64)],

            "right_weapon_idle": [(1024, 128, 64, 64), (1088, 128, 64, 64), (1152, 128, 64, 64), (1216, 128, 64, 64)],
            "right_weapon_stealth_move": [(1280, 128, 64, 64), (1344, 128, 64, 64), (1408, 128, 64, 64), (1472, 128, 64, 64)],
            "right_weapon_retreat": [(1088, 384, 64, 64)],
            "right_weapon_lunge": [(1152, 384, 64, 64)],
            "right_weapon_crouch": [(1024, 384, 64, 64)],

            "right_spear_draw": [(512, 896, 64, 64), (576, 896, 64, 64), (640, 896, 64, 64)],
            "right_spear_parry": [(704, 896, 64, 64)],
            "right_spear_dodge": [(768, 896, 64, 64)],

            "right_sword_draw": [(1024, 1152, 64, 64), (1088, 1152, 64, 64), (1152, 1152, 64, 64)],
            "right_sword_parry": [(1216, 1152, 64, 64)],
            "right_sword_dodge": [(1280, 1152, 64, 64)],

            "left_weapon_idle": [(1024, 192, 64, 64), (1088, 192, 64, 64), (1152, 192, 64, 64), (1216, 192, 64, 64)],
            "left_weapon_stealth_move": [(1280, 192, 64, 64), (1344, 192, 64, 64), (1408, 192, 64, 64), (1472, 192, 64, 64)],
            "left_weapon_retreat": [(1088, 448, 64, 64)],
            "left_weapon_lunge": [(1152, 448, 64, 64)],
            "left_weapon_crouch": [(1024, 448, 64, 64)],

            "left_spear_draw": [(512, 960, 64, 64), (576, 960, 64, 64), (640, 960, 64, 64)],
            "left_spear_parry": [(704, 960, 64, 64)],
            "left_spear_dodge": [(768, 1024, 64, 64)],

            "left_sword_draw": [(1024, 1216, 64, 64), (1088, 1216, 64, 64), (1152, 1216, 64, 64)],
            "left_sword_parry": [(1216, 1216, 64, 64)],
            "left_sword_dodge": [(1280, 1216, 64, 64)],

            # Farming and Tool Animations
            "down_hoe": [(0, 1024, 64, 64), (64, 1024, 64, 64), (128, 1024, 64, 64), (192, 1024, 64, 64)],
            "up_hoe": [(0, 1088, 64, 64), (64, 1088, 64, 64), (128, 1088, 64, 64), (192, 1088, 64, 64)],
            "left_hoe": [(0, 1216, 64, 64), (64, 1216, 64, 64), (128, 1216, 64, 64), (192, 1216, 64, 64)],
            "right_hoe": [(0, 1152, 64, 64), (64, 1152, 64, 64), (128, 1152, 64, 64), (192, 1152, 64, 64)],

            "down_water": [(0, 1280, 64, 64), (64, 1280, 64, 64), (128, 1280, 64, 64), (192, 1280, 64, 64)],
            "up_water": [(0, 1344, 64, 64), (64, 1344, 64, 64), (128, 1344, 64, 64), (192, 1344, 64, 64)],
            "right_water": [(0, 1408, 64, 64), (64, 1408, 64, 64), (128, 1408, 64, 64), (192, 1408, 64, 64)],
            "left_water": [(0, 1472, 64, 64), (64, 1472, 64, 64), (128, 1472, 64, 64), (192, 1472, 64, 64)],

            "down_seed": [(256, 1024, 64, 64), (320, 1024, 64, 64), (384, 1024, 64, 64), (448, 1024, 64, 64)],
            "up_seed": [(256, 1088, 64, 64), (320, 1088, 64, 64), (384, 1088, 64, 64), (448, 1088, 64, 64)],
            "left_seed": [(256, 1216, 64, 64), (320, 1216, 64, 64), (384, 1216, 64, 64), (448, 1216, 64, 64)],
            "right_seed": [(256, 1152, 64, 64), (320, 1152, 64, 64), (384, 1152, 64, 64), (448, 1152, 64, 64)],

            "down_axe": [(0, 1024, 64, 64), (64, 1024, 64, 64), (128, 1024, 64, 64), (192, 1024, 64, 64)],
            "up_axe": [(0, 1088, 64, 64), (64, 1088, 64, 64), (128, 1088, 64, 64), (192, 1088, 64, 64)],
            "left_axe": [(0, 1216, 64, 64), (64, 1216, 64, 64), (128, 1216, 64, 64), (192, 1216, 64, 64)],
            "right_axe": [(0, 1152, 64, 64), (64, 1152, 64, 64), (128, 1152, 64, 64), (192, 1152, 64, 64)],

            # Fishing Animations
            # Initial cast: the player initializes the cast.
            # Cast: play the full cast, then enter fish.
            # Fish: wait here until a catch prompts the player to reel in.
            # Reel in: play one required reel-in, then return to fish for the
            # next randomized prompt.
            # Reel: after all required reel-ins, land the catch and return idle.
            "down_initial_cast": [(512, 0, 64, 64)],
            "down_cast": [(512, 0, 64, 64), (576, 0, 64, 64), (640, 0, 64, 64)],
            "down_fish": [(704, 0, 64, 64)],
            "down_reel_in": [(768, 0, 64, 64), (832, 0, 64, 64)],
            "down_reel": [(768, 0, 64, 64), (832, 0, 64, 64), (896, 0, 64, 64), (960, 0, 64, 64)],

            "up_initial_cast": [(512, 192, 64, 64)],
            "up_cast": [(512, 192, 64, 64), (576, 192, 64, 64), (640, 192, 64, 64)],
            "up_fish": [(704, 192, 64, 64)],
            "up_reel_in": [(768, 192, 64, 64), (832, 192, 64, 64)],
            "up_reel": [(768, 192, 64, 64), (832, 192, 64, 64), (896, 192, 64, 64), (960, 192, 64, 64)],

            "right_initial_cast": [(512, 256, 64, 64)],
            "right_cast": [(512, 256, 64, 64), (576, 256, 64, 64), (640, 256, 64, 64)],
            "right_fish": [(768, 256, 64, 64)],
            "right_reel_in": [(768, 320, 64, 64), (832, 320, 64, 64)],
            "right_reel": [(768, 320, 64, 64), (832, 320, 64, 64), (896, 320, 64, 64), (960, 320, 64, 64)],

            "left_initial_cast": [(512, 384, 64, 64)],
            "left_cast": [(512, 384, 64, 64), (576, 384, 64, 64), (704, 384, 64, 64)],
            "left_fish": [(832, 384, 64, 64)],
            "left_reel_in": [(704, 448, 64, 64), (832, 448, 64, 64)],
            "left_reel": [(704, 448, 64, 64), (832, 448, 64, 64), (896, 448, 64, 64), (960, 448, 64, 64)],




            # Arrow shooting animations
            "down_bow_shoot": [(1024, 768, 64, 64), (1088, 768, 64, 64), (1152, 768, 64, 64), (1216, 768, 64, 64), (1280, 768, 64, 64), (1344, 768, 64, 64), (1408, 768, 64, 64), (1472, 768, 64, 64)],
            "up_bow_shoot": [(1024, 832, 64, 64), (1088, 832, 64, 64), (1152, 832, 64, 64), (1216, 832, 64, 64),
                             (1280, 832, 64, 64), (1344, 832, 64, 64), (1408, 832, 64, 64), (1472, 832, 64, 64)],
            "right_bow_shoot": [(1024, 896, 64, 64), (1088, 896, 64, 64), (1152, 896, 64, 64), (1216, 896, 64, 64),
                                (1280, 896, 64, 64), (1344, 896, 64, 64), (1408, 896, 64, 64), (1472, 896, 64, 64)],
            "left_bow_shoot": [(1024, 960, 64, 64), (1088, 960, 64, 64), (1152, 960, 64, 64), (1216, 960, 64, 64),
                               (1280, 960, 64, 64), (1344, 960, 64, 64), (1408, 960, 64, 64), (1472, 960, 64, 64)],



            # Sword and Shield weapons
            "down_sword_slash1": [(512, 1024, 64, 64), (576, 1024, 64, 64), (640, 1024, 64, 64), (704, 1024, 64, 64)],
            "down_sword_slash2": [(768, 1024, 64, 64), (832, 1024, 64, 64), (896, 1024, 64, 64), (960, 1024, 64, 64)],
            "up_sword_slash1": [(512, 1088, 64, 64), (576, 1088, 64, 64), (640, 1088, 64, 64), (704, 1088, 64, 64)],
            "up_sword_slash2": [(768, 1088, 64, 64), (832, 1088, 64, 64), (896, 1088, 64, 64), (960, 1088, 64, 64)],
            "right_sword_slash1": [(512, 1152, 64, 64), (576, 1152, 64, 64), (640, 1152, 64, 64), (704, 1152, 64, 64)],
            "right_sword_slash2": [(768, 1152, 64, 64), (832, 1152, 64, 64), (896, 1152, 64, 64), (960, 1152, 64, 64)],
            "left_sword_slash1": [(512, 1216, 64, 64), (576, 1216, 64, 64), (640, 1216, 64, 64), (704, 1216, 64, 64)],
            "left_sword_slash2": [(768, 1216, 64, 64), (832, 1216, 64, 64), (896, 1216, 64, 64), (960, 1216, 64, 64)],

            # Extra Sword animations
            "down_sword_thrust": [(512, 1280, 64, 64), (576, 1280, 64, 64), (640, 1280, 64, 64), (704, 1280, 64, 64)],
            "up_sword_thrust": [(512, 1344, 64, 64), (576, 1344, 64, 64), (640, 1344, 64, 64), (704, 1344, 64, 64)],
            "right_sword_thrust": [(512, 1408, 64, 64), (576, 1408, 64, 64), (640, 1408, 64, 64), (704, 1408, 64, 64)],
            "left_sword_thrust": [(512, 1472, 64, 64), (576, 1472, 64, 64), (640, 1472, 64, 64), (704, 1472, 64, 64)],

            # these strictly requires a sword
            "down_shield_bash": [(768, 1280, 64, 64), (832, 1280, 64, 64), (896, 1280, 64, 64), (960, 1280, 64, 64)],
            "up_shield_bash": [(768, 1344, 64, 64), (832, 1344, 64, 64), (896, 1344, 64, 64), (960, 1344, 64, 64)],
            "right_shield_bash": [(768, 1408, 64, 64), (832, 1408, 64, 64), (896, 1408, 64, 64), (960, 1408, 64, 64)],
            "left_shield_bash": [(768, 1472, 64, 64), (832, 1472, 64, 64), (896, 1472, 64, 64), (960, 1472, 64, 64)],

            # Extra Spear Animations
            "down_spear_splash": [(1216, 256, 64, 64), (1280, 256, 64, 64), (1344, 256, 64, 64), (1408, 256, 64, 64)],
            "down_spear_thrust1": [(1216, 512, 64, 64), (1280, 512, 64, 64), (1344, 512, 64, 64)],
            "down_spear_thrust2": [(1408, 512, 64, 64), (1472, 512, 64, 64), (1536, 512, 64, 64)],

            "up_spear_splash": [(1216, 320, 64, 64), (1280, 320, 64, 64), (1344, 320, 64, 64), (1408, 320, 64, 64)],
            "up_spear_thrust1": [(1216, 576, 64, 64), (1280, 576, 64, 64), (1344, 576, 64, 64)],
            "up_spear_thrust2": [(1408, 576, 64, 64), (1472, 576, 64, 64), (1536, 576, 64, 64)],

            "right_spear_splash": [(1216, 384, 64, 64), (1280, 384, 64, 64), (1344, 384, 64, 64), (1408, 394, 64, 64)],
            "right_spear_thrust1": [(1216, 640, 64, 64), (1280, 640, 64, 64), (1344, 640, 64, 64)],
            "right_spear_thrust2": [(1408, 640, 64, 64), (1472, 640, 64, 64), (1536, 640, 64, 64)],

            "left_spear_splash": [(1216, 448, 64, 64), (1280, 448, 64, 64), (1344, 448, 64, 64), (1408, 448, 64, 64)],
            "left_spear_thrust1": [(1216, 704, 64, 64), (1280, 704, 64, 64), (1344, 704, 64, 64)],
            "left_spear_thrust2": [(1408, 704, 64, 64), (1472, 704, 64, 64), (1536, 704, 64, 64)],

        }

        # This identifies the draw order of the weapon, 0 -> behind, 1 -> front of the character
        self.weapon_draw_offset = {
            # Base Animations
            "down": [0, 0, 0, 0, 0, 0],
            "up": [1, 1 ,1 ,1 ,1 ,1],
            "right": [0, 1, 1, 1, 0, 0],
            "left": [0, 1, 1, 1, 0, 0],

            # Jump
            "down_jump": [0, 0, 0, 0],
            "up_jump": [1, 1, 1, 1],
            "right_jump": [0, 0, 0, 0],
            "left_jump": [0, 0, 0, 0],

            # splint
            "down_splint": [0, 0],
            "up_splint": [1, 1],
            "right_splint": [1, 0],
            "left_splint": [1, 0],

            # Sword and shield -> (Sword, Shield)
            "down_sword_draw": [(0,0), (1,1),(0,0)],
            "down_sword_pary": [(1, 0)],
            "down_sword_dodge": [(1, 1)],
            "down_sword_hurt": [(1, 0)],
            "down_sword_dead": [(0, 1), (0, 1)],
            "down_sword_idle": [(1,1), (1,1), (1,1), (1,1)],
            "down_sword_stealth_move": [(1,1), (1,1), (1,1), (1,1)],
            "down_sword_lunge": [(1,1)],
            "down_sword_crouch": [(1,1)],
            "down_sword_retreat": [(1,1)],
            "down_sword_slash1": [(0,1), (0,0), (0,0), (1,0)],
            "down_sword_slash2": [(0,0), (0,0), (0,1), (0,1)],
            "down_sword_thrust": [(1,1), (1,0), (0,0), (0,0)],
            "down_shield_bash": [(0,1), (0,1), (0,0), (1,0)],

            "up_sword_draw": [(1, 1), (0, 0), (0, 1)],
            "up_sword_pary": [(0, 1)],
            "up_sword_dodge": [(0, 0)],
            "up_sword_hurt": [(0, 1)],
            "up_sword_dead": [(0, 0), (0, 0)],
            "up_sword_idle": [(0, 0), (0, 0), (0, 0), (0, 0)],
            "up_sword_stealth_move": [(0, 0), (0, 0), (0, 0), (0, 0)],
            "up_sword_lunge": [(0, 0)],
            "up_sword_crouch": [(0, 0)],
            "up_sword_retreat": [(0, 0)],
            "up_sword_slash1": [(0,0), (0,0), (0,1), (0,1)],
            "up_sword_slash2": [(0,1), (0,1), (0,0), (0,0)],
            "up_sword_thrust": [(0,0), (0,0), (0,1), (0,1)],
            "up_shield_bash": [(0,0), (0,1), (0,1), (0,1)],


            "right_sword_draw": [(0, 0), (1, 0), (1, 0)],
            "right_sword_pary": [(0, 1)],
            "right_sword_dodge": [(1, 1)],
            "right_sword_hurt": [(1, 0)],
            "right_sword_dead": [(0, 0), (0, 0)],
            "right_sword_idle": [(1, 0), (1, 0), (1, 0), (1, 0)],
            "right_sword_stealth_move": [(1, 0), (1, 0), (1, 0), (1, 0)],
            "right_sword_lunge": [(1, 0)],
            "right_sword_crouch": [(1, 0)],
            "right_sword_retreat": [(1, 0)],
            "right_sword_slash1": [(0,0), (1,0), (0,0), (0,0)],
            "right_sword_slash2": [(0,0), (0,0), (0,0), (0,0)],
            "right_sword_thrust": [(1,0), (1,0), (0,0), (1,0)],
            "right_shield_bash": [(1,1), (1,0), (1,1), (1,1)],


            "left_sword_draw": [(0, 0), (1, 0), (1, 0)],
            "left_sword_pary": [(0, 1)],
            "left_sword_dodge": [(1, 1)],
            "left_sword_hurt": [(1, 0)],
            "left_sword_dead": [(0, 0), (0, 0)],
            "left_sword_idle": [(1, 0), (1, 0), (1, 0), (1, 0)],
            "left_sword_stealth_move": [(1, 0), (1, 0), (1, 0), (1, 0)],
            "left_sword_lunge": [(1, 0)],
            "left_sword_crouch": [(1, 0)],
            "left_sword_retreat": [(1, 0)],
            "left_sword_slash1": [(0,0), (1,0), (0,0), (1,0)],
            "left_sword_slash2": [(0,0), (0,0), (0,0), (0,0)],
            "left_sword_thrust": [(1,0), (1,0), (0,0), (1,0)],
            "left_shield_bash": [(1,1), (1,0), (1,1), (1,1)],

            # Spear Animations
            "down_spear_draw": [0, 1, 1],
            "down_spear_pary": [1],
            "down_spear_dodge": [1],
            "down_spear_hurt": [1],
            "down_spear_dead": [1,1],
            "down_stealth_idle": [1, 1, 1, 1],
            "down_stealth_move": [1, 1, 1, 1],
            "down_lunge": [1],
            "down_crouch": [1],
            "down_retreat": [1],
            "down_spear_splash": [0, 0, 0, 0],
            "down_spear_thrust1": [1, 1, 1],
            "down_spear_thrust2": [1, 1, 1],


            "up_spear_draw": [1, 0, 0],
            "up_spear_pary": [0],
            "up_spear_dodge": [0],
            "up_spear_hurt": [0],
            "up_spear_dead": [0,0],
            "up_stealth_idle": [0, 0, 0, 0],
            "up_stealth_move": [0, 0, 0, 0],
            "up_lunge": [1],
            "up_crouch": [1],
            "up_retreat": [1],
            "up_spear_splash": [1, 0, 0, 0],
            "up_spear_thrust1": [1, 0, 0],
            "up_spear_thrust2": [1, 0, 0],

            "right_spear_draw": [0, 1, 1],
            "right_spear_pary": [0],
            "right_spear_dodge": [1],
            "right_spear_hurt": [1],
            "right_spear_dead": [1, 1],
            "right_stealth_idle": [1, 1, 1, 1],
            "right_stealth_move": [1, 1, 1, 1],
            "right_lunge": [1],
            "right_crouch": [1],
            "right_retreat": [1],
            "right_spear_splash": [0, 0, 1, 1],
            "right_spear_thrust1": [1, 1, 1],
            "right_spear_thrust2": [1, 1, 1],

            "left_spear_draw": [0, 1, 1],
            "left_spear_pary": [0],
            "left_spear_dodge": [1],
            "left_spear_hurt": [1],
            "left_spear_dead": [1, 1],
            "left_idle": [1, 1, 1, 1],
            "left_move": [1, 1, 1, 1],
            "left_lunge": [1],
            "left_crouch": [1],
            "left_retreat": [1],
            "left_spear_splash": [0, 0, 1, 1],
            "left_spear_thrust1": [1, 1, 1],
            "left_spear_thrust2": [1, 1, 1],
        }
        self.character_furniture_regions = {
            "empty_shelves": (6, 39, 22, 79),
            "bed": (103, 98, 43, 47),
            "rug": (13, 194, 68, 40),
            "bookshelf": (216, 199, 52, 55),
            "stool1": (261, 265, 19, 19),
            "stool2": (261, 287, 19, 19),
            "table": (283, 259, 29, 49)
        }
        self.all_trees = {
            "palm": [(64, 0, 64, 75)],
            "pine": [(0, 234, 64, 82)],
            "oak": [(64, 153, 64, 78)],
            "mangrove": [(66, 264, 58, 51)],
            "birch": [(0, 78, 64, 78)],
            "cherry": [(0, 156, 64, 78)],
            "apple": [(0, 0, 64, 78)],
            "peach": [(64, 75, 64, 78)],
            "dead_tree": [(66, 264, 58, 51)],
            "stump": [(80, 231, 31, 28)]
        }
        self.tree_shades = {
            "tropical": [(546, 436, 192, 160)],
            "fruit": [(686, 546, 128, 224)],
            "tropicfruit": [(742, 426, 97, 54)]
        }
        self.buildings = {
            "stalls": [(11, 80, 64, 64)],
            "farms": [(480, 8, 32, 54)]
        }

        self.water_frames = {
            "1": (0, 0, 32, 32),
            "2": (32, 0, 32, 32),
            "3": (64, 0, 32, 32),
            "4": (128, 0, 32, 32),
            "5": (160, 0, 32, 32),
            "6": (192, 0, 32, 32),
            "7": (224, 0, 32, 32),
        }

        pass

    def load_character_parts(self):
        parts = {}
        folder_sheets = {}
        for part_name, folder in CHARACTER_PART_FOLDERS.items():
            if folder in folder_sheets:
                parts[part_name] = folder_sheets[folder]
                continue
            folder_path = Path(rp("graphics", "character", folder))
            part_sheets = {}
            if folder_path.exists():
                for path in sorted(folder_path.glob("*.png")):
                    part_sheets[path.stem] = SpriteSheet("graphics", "character", folder, path.name)
            folder_sheets[folder] = part_sheets
            parts[part_name] = part_sheets
        return parts

    def load_guard_parts(self):
        """Load the dedicated modular guard layers from the NPC asset tree."""
        guard_root = ("graphics", "sprites", "npcs", "guard")
        return {
            "skin": SpriteSheet(*guard_root, "skin", "1.png"),
            "outfit": SpriteSheet(*guard_root, "outfit", "1.png"),
            "hair": SpriteSheet(*guard_root, "hair", "1.png"),
            "sword": SpriteSheet(*guard_root, "weapons", "sword.png"),
            "shield": SpriteSheet(*guard_root, "weapons", "shield.png"),
        }

    def load_npc_profiles(self):
        """Catalog human NPC sheets without decoding every variant at startup."""
        root = Path(rp("graphics", "sprites", "npcs"))
        profiles = {}
        if not root.exists():
            return profiles

        for role_path in sorted(path for path in root.iterdir() if path.is_dir()):
            role = role_path.name.lower()
            if role in NPC_EXCLUDED_ROLES:
                continue
            for sheet_path in sorted(role_path.glob("*.png")):
                npc_id = f"{role}/{sheet_path.stem}"
                profiles[npc_id] = {
                    "id": npc_id,
                    "role": role,
                    "name": sheet_path.stem,
                    "sheet_path": (
                        "graphics",
                        "sprites",
                        "npcs",
                        role_path.name,
                        sheet_path.name,
                    ),
                    "sheet": None,
                }
        return profiles

    def get_npc_ids(self, role=None):
        npc_ids = self.npc_profiles.keys()
        if role is not None:
            npc_ids = (
                npc_id
                for npc_id in npc_ids
                if self.npc_profiles[npc_id]["role"] == role
            )
        return list(npc_ids)

    def get_npc_roles(self):
        return sorted({profile["role"] for profile in self.npc_profiles.values()})

    def get_npc_profile(self, npc_id):
        return self.npc_profiles[npc_id]

    @staticmethod
    def get_npc_animation_rects(role, animation_name):
        if animation_name in NPC_WALK_DIRECTIONS:
            row = NPC_WALK_DIRECTIONS.index(animation_name)
            return tuple(
                (frame * NPC_FRAME_SIZE, row * NPC_FRAME_SIZE, NPC_FRAME_SIZE, NPC_FRAME_SIZE)
                for frame in range(4)
            )

        if animation_name.endswith("_idle"):
            facing = animation_name.removesuffix("_idle")
            if facing in NPC_WALK_DIRECTIONS:
                row = NPC_WALK_DIRECTIONS.index(facing)
                return ((0, row * NPC_FRAME_SIZE, NPC_FRAME_SIZE, NPC_FRAME_SIZE),)

        extra = NPC_EXTRA_ANIMATIONS.get(role, {}).get(animation_name)
        if extra is None:
            raise KeyError(f"Unknown NPC animation {animation_name!r} for role {role!r}")
        start_x, start_y, frame_count = extra
        return tuple(
            (start_x + frame * NPC_FRAME_SIZE, start_y, NPC_FRAME_SIZE, NPC_FRAME_SIZE)
            for frame in range(frame_count)
        )

    def get_npc_frames(self, npc_id, animation_name):
        cache_key = (npc_id, animation_name)
        cached = self._npc_frame_cache.get(cache_key)
        if cached is not None:
            return cached

        profile = self.npc_profiles[npc_id]
        sheet = profile["sheet"]
        if sheet is None:
            sheet = SpriteSheet(*profile["sheet_path"])
            profile["sheet"] = sheet

        frames = tuple(
            sheet.get_sprite(*frame_rect)
            for frame_rect in self.get_npc_animation_rects(
                profile["role"],
                animation_name,
            )
        )
        self._npc_frame_cache[cache_key] = frames
        return frames

    def get_npc_idle_animation(self, npc_id, facing):
        role = self.npc_profiles[npc_id]["role"]
        return NPC_DEFAULT_IDLE_BY_ROLE.get(role, f"{facing}_idle")

    def get_npc_special_states(self, npc_id):
        role = self.npc_profiles[npc_id]["role"]
        return NPC_SPECIAL_STATES_BY_ROLE.get(role, ())

    @staticmethod
    def get_npc_animation_speed(animation_name):
        if animation_name in NPC_WALK_DIRECTIONS:
            return 7
        if animation_name == "dancing":
            return 7
        if animation_name in {"singing", "drinking_right", "drinking_left"}:
            return 5
        if animation_name in {"sitting", "king_idle", "queen_idle"}:
            return 2
        if animation_name in {"praying_down", "kneeling_prayer_up"}:
            return 3
        return 1

    def get_character_options(self):
        return {part_name: options[:] for part_name, options in self.character_options.items()}

    def normalize_character_customization(self, customization=None):
        normalized = dict(self.default_character_customization)
        if customization:
            normalized.update(customization)

        for part_name, selected in list(normalized.items()):
            if selected is None:
                continue
            if str(selected) not in self.character_parts.get(part_name, {}):
                normalized[part_name] = self.default_character_customization.get(part_name)
        return normalized

    def _character_cache_key(self, animation_name, customization):
        normalized = self.normalize_character_customization(customization)
        return (
            animation_name,
            normalized.get("skin"),
            normalized.get("clothes"),
            normalized.get("hair"),
            normalized.get("weapon"),
            normalized.get("offhand"),
        )

    def _draw_character_part(self, surface, part_name, part_id, frame_rect):
        if part_id is None:
            return
        sheet = self.character_parts.get(part_name, {}).get(str(part_id))
        if sheet is None:
            return
        surface.blit(sheet.get_sprite(*frame_rect), (0, 0))

    def _equipment_layer_flags(self, animation_name, frame_index, weapon_behind):
        layer_key = animation_name
        replacements = {
            "_weapon_idle": "_sword_idle",
            "_weapon_stealth_move": "_sword_stealth_move",
            "_weapon_lunge": "_sword_lunge",
            "_weapon_crouch": "_sword_crouch",
            "_weapon_retreat": "_sword_retreat",
            "_hurt_sword": "_sword_hurt",
            "_dead_sword": "_sword_dead",
        }
        for suffix, replacement in replacements.items():
            if layer_key.endswith(suffix):
                layer_key = layer_key[:-len(suffix)] + replacement
                break
        authored_order = getattr(self, "weapon_draw_offset", {}).get(layer_key)
        if authored_order:
            order = authored_order[min(frame_index, len(authored_order) - 1)]
            if isinstance(order, tuple):
                return order
            return order, order
        fallback = 0 if weapon_behind else 1
        return fallback, fallback

    def compose_character_frame(
        self,
        animation_name,
        frame_rect,
        customization,
        frame_index=0,
    ):
        _, _, width, height = frame_rect
        normalized = self.normalize_character_customization(customization)
        frame = pygame.Surface((width, height), pygame.SRCALPHA)
        facing = animation_name.split("_", 1)[0]
        weapon_behind = facing in {"up", "left"}
        weapon_id = normalized.get("weapon")
        offhand_id = normalized.get("offhand")

        equipment = (
            ("weapon", weapon_id),
            ("offhand", offhand_id),
        )
        layer_flags = self._equipment_layer_flags(
            animation_name,
            frame_index,
            weapon_behind,
        )
        for (part_name, part_id), layer_flag in zip(equipment, layer_flags):
            if layer_flag == 0:
                self._draw_character_part(frame, part_name, part_id, frame_rect)
        for part_name in CHARACTER_LAYER_ORDER:
            self._draw_character_part(frame, part_name, normalized.get(part_name), frame_rect)
        if any(animation_name.endswith(f"_{action}") for action in TOOL_LAYER_ACTIONS):
            frame.blit(self.farm_tool_sheet.get_sprite(*frame_rect), (0, 0))
        for (part_name, part_id), layer_flag in zip(equipment, layer_flags):
            if layer_flag == 1:
                self._draw_character_part(frame, part_name, part_id, frame_rect)
        return frame

    def get_character_frames(self, animation_name, customization=None):
        cache_key = self._character_cache_key(animation_name, customization)
        cached = self._character_frame_cache.get(cache_key)
        if cached is not None:
            return [frame.copy() for frame in cached]

        frame_data = self.character_animations[animation_name]
        frames = []

        for frame_index, frame_rect in enumerate(frame_data):
            frames.append(
                self.compose_character_frame(
                    animation_name,
                    frame_rect,
                    customization,
                    frame_index,
                )
            )

        self._character_frame_cache[cache_key] = [frame.copy() for frame in frames]
        return frames

    def get_guard_frames(self, animation_name):
        cached = self._guard_frame_cache.get(animation_name)
        if cached is not None:
            return [frame.copy() for frame in cached]

        frames = []
        frame_data = self.character_animations[animation_name]
        facing = animation_name.split("_", 1)[0]
        for frame_index, frame_rect in enumerate(frame_data):
            _, _, width, height = frame_rect
            frame = pygame.Surface((width, height), pygame.SRCALPHA)
            layer_flags = self._equipment_layer_flags(
                animation_name,
                frame_index,
                facing in {"up", "left"},
            )
            equipment = (
                (self.guard_parts["sword"], layer_flags[0]),
                (self.guard_parts["shield"], layer_flags[1]),
            )
            for sheet, layer_flag in equipment:
                if layer_flag == 0:
                    frame.blit(sheet.get_sprite(*frame_rect), (0, 0))
            for part_name in ("skin", "outfit", "hair"):
                frame.blit(self.guard_parts[part_name].get_sprite(*frame_rect), (0, 0))
            for sheet, layer_flag in equipment:
                if layer_flag == 1:
                    frame.blit(sheet.get_sprite(*frame_rect), (0, 0))
            frames.append(frame)

        self._guard_frame_cache[animation_name] = [frame.copy() for frame in frames]
        return frames


_SHARED_ASSETS = None


def get_shared_assets():
    """Return the process-wide asset registry used by all runtime systems."""
    global _SHARED_ASSETS
    if _SHARED_ASSETS is None:
        _SHARED_ASSETS = LoadAssets()
    return _SHARED_ASSETS

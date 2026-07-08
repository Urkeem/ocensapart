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
}
CHARACTER_LAYER_ORDER = ("skin", "clothes", "hair")


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
        }
        self._character_frame_cache = {}
        self.all_trees_sprites = SpriteSheet("graphics/environment/trees", "all_trees.png")
        self.character_portrait_sprite_sheet = SpriteSheet("graphics/character", "Portraits.png")
        # self.market_sprite_sheet = SpriteSheet("graphics/environment/buildings", "market.png")
        self.environment_props1_sprite_sheet = SpriteSheet("graphics/environment", "Props.png")
        self.water_sprites = SpriteSheet("Tilesets/", "water.png")

        self.sprite_data = {
            "inv_bg": (434, 979, 168, 60),
            "slot": (1, 155, 36, 28),
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

            # Dead
            "down_dead": [(896, 768, 64, 64), (960, 768, 64, 64)],
            "up_dead": [(896, 832, 64, 64), (960, 832, 64, 64)],
            "right_dead": [(896, 896, 64, 64), (960, 896, 64, 64)],
            "left_dead": [(896, 960, 64, 64), (960, 960, 64, 64)],

            # Hurt
            "down_hurt": [(832, 768, 64, 64)],
            "up_hurt": [(832, 832, 64, 64)],
            "right_hurt": [(832, 896, 64, 64)],
            "left_hurt": [(832, 960, 64, 64)],

            # idle / move / draw/ parry / lunge / retreat / crouch with weapon
            "down_weapon_idle": [(1024, 0, 64, 64), (1088, 0, 64, 64), (1152, 0, 64, 64), (1216, 0, 64, 64)],
            "down_weapon_move": [(1280, 0, 64, 64), (1344, 0, 64, 64), (1408, 0, 64, 64), (1472, 0, 64, 64)],
            "down_weapon_crouch": [(1024, 256, 64, 64)],
            "down_weapon_retreat": [(1152, 256, 64, 64), (1088, 256, 64, 64), (1024, 256, 64, 64)],
            "down_weapon_lunge": [(1024, 256, 64, 64),(1088, 256, 64, 64), (1152, 256, 64, 64)],
            "down_weapon_draw": [(512, 768, 64, 64), (576, 768, 64, 64), (640, 768, 64, 64)],
            "down_weapon_parry": [(704, 768, 64, 64)],
            "down_weapon_dodge": [(768, 768, 64, 64)],

            "up_weapon_idle": [(1024, 64, 64, 64), (1088, 64, 64, 64), (1152, 64, 64, 64), (1216, 64, 64, 64)],
            "up_weapon_move": [(1280, 64, 64, 64), (1344, 64, 64, 64), (1408, 64, 64, 64), (1472, 64, 64, 64)],
            "up_weapon_crouch": [(1024, 320, 64, 64)],
            "up_weapon_retreat": [(1088, 320, 64, 64)],
            "up_weapon_lunge": [(1152, 320, 64, 64)],
            "up_weapon_draw": [(512, 832, 64, 64), (576, 832, 64, 64), (640, 832, 64, 64)],
            "up_weapon_parry": [(704, 832, 64, 64)],
            "up_weapon_dodge": [(768, 832, 64, 64)],

            "right_weapon_idle": [(1024, 128, 64, 64), (1088, 128, 64, 64), (1152, 128, 64, 64), (1216, 128, 64, 64)],
            "right_weapon_move": [(1280, 128, 64, 64), (1344, 128, 64, 64), (1408, 128, 64, 64), (1472, 128, 64, 64)],
            "right_weapon_crouch": [(1024, 384, 64, 64)],
            "right_weapon_retreat": [(1088, 384, 64, 64)],
            "right_weapon_lunge": [(1152, 384, 64, 64)],
            "right_weapon_draw": [(512, 896, 64, 64), (576, 896, 64, 64), (640, 896, 64, 64)],
            "right_weapon_parry": [(704, 896, 64, 64)],
            "right_weapon_dodge": [(768, 896, 64, 64)],

            "left_weapon_idle": [(1024, 192, 64, 64), (1088, 192, 64, 64), (1152, 192, 64, 64), (1216, 192, 64, 64)],
            "left_weapon_move": [(1280, 192, 64, 64), (1344, 192, 64, 64), (1408, 192, 64, 64), (1472, 192, 64, 64)],
            "left_weapon_crouch": [(1024, 448, 64, 64)],
            "left_weapon_retreat": [(1088, 448, 64, 64)],
            "left_weapon_lunge": [(1152, 448, 64, 64)],
            "left_weapon_draw": [(512, 960, 64, 64), (576, 960, 64, 64), (640, 960, 64, 64)],
            "left_weapon_parry": [(704, 960, 64, 64)],
            "left_weapon_dodge": [(768, 960, 64, 64)],

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
            "down_initial_cast": [(512, 0, 64, 64)],
            "down_cast": [(512, 0, 64, 64), (576, 0, 64, 64), (640, 0, 64, 64)],
            "down_fish": [(704, 0, 64, 64), (768, 0, 64, 64)],
            "down_initial_reel": [(768, 0, 64, 64), (832, 0, 64, 64)],
            "down_reel": [(768, 0, 64, 64), (832, 0, 64, 64), (896, 0, 64, 64), (960, 0, 64, 64)],

            # Arrow shooting animations
            "down_bow_shoot": [(1024, 768, 64, 64), (1088, 768, 64, 64), (1152, 768, 64, 64), (1216, 768, 64, 64), (1280, 768, 64, 64), (1344, 768, 64, 64), (1408, 768, 64, 64), (1472, 768, 64, 64)],
            "up_bow_shoot": [(1024, 832, 64, 64), (1088, 832, 64, 64), (1152, 832, 64, 64), (1216, 832, 64, 64),
                             (1280, 832, 64, 64), (1344, 832, 64, 64), (1408, 832, 64, 64), (1472, 832, 64, 64)],
            "right_bow_shoot": [(1024, 896, 64, 64), (1088, 896, 64, 64), (1152, 896, 64, 64), (1216, 896, 64, 64),
                                (1280, 896, 64, 64), (1344, 896, 64, 64), (1408, 896, 64, 64), (1472, 896, 64, 64)],
            "left_bow_shoot": [(1024, 960, 64, 64), (1088, 960, 64, 64), (1152, 960, 64, 64), (1216, 960, 64, 64),
                               (1280, 960, 64, 64), (1344, 960, 64, 64), (1408, 960, 64, 64), (1472, 960, 64, 64)],



            # Sword and other weapons
            "down_sword": [(512, 1024, 64, 64), (576, 1024, 64, 64), (640, 1024, 64, 64), (704, 1024, 64, 64), (768, 1024, 64, 64), (832, 1024, 64, 64), (896, 1024, 64, 64), (960, 1024, 64, 64)],
            "up_sword": [(512, 1088, 64, 64), (576, 1088, 64, 64), (640, 1088, 64, 64), (704, 1088, 64, 64),
                           (768, 1088, 64, 64), (832, 1088, 64, 64), (896, 1088, 64, 64), (960, 1088, 64, 64)],
            "right_sword": [(512, 1152, 64, 64), (576, 1152, 64, 64), (640, 1152, 64, 64), (704, 1152, 64, 64),
                           (768, 1152, 64, 64), (832, 1152, 64, 64), (896, 1152, 64, 64), (960, 1152, 64, 64)],
            "left_sword": [(512, 1216, 64, 64), (576, 1216, 64, 64), (640, 1216, 64, 64), (704, 1216, 64, 64),
                           (768, 1216, 64, 64), (832, 1216, 64, 64), (896, 1216, 64, 64), (960, 1216, 64, 64)],

            # Other Sword animations
            "down_sword1": [(512, 1280, 64, 64), (576, 1280, 64, 64), (640, 1280, 64, 64), (704, 1280, 64, 64),
                           (768, 1280, 64, 64), (832, 1280, 64, 64), (896, 1280, 64, 64), (960, 1280, 64, 64)],
            "up_sword1": [(512, 1344, 64, 64), (576, 1344, 64, 64), (640, 1344, 64, 64), (704, 1344, 64, 64),
                           (768, 1344, 64, 64), (832, 1344, 64, 64), (896, 1344, 64, 64), (960, 1344, 64, 64)],
            "right_sword1": [(512, 1408, 64, 64), (576, 1408, 64, 64), (640, 1408, 64, 64), (704, 1408, 64, 64),
                           (768, 1408, 64, 64), (832, 1408, 64, 64), (896, 1408, 64, 64), (960, 1408, 64, 64)],
            "left_sword1": [(512, 1472, 64, 64), (576, 1472, 64, 64), (640, 1472, 64, 64), (704, 142, 64, 64),
                           (768, 1472, 64, 64), (832, 1472, 64, 64), (896, 1472, 64, 64), (960, 1472, 64, 64)],



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
        for part_name, folder in CHARACTER_PART_FOLDERS.items():
            folder_path = Path(rp("graphics", "character", folder))
            part_sheets = {}
            if folder_path.exists():
                for path in sorted(folder_path.glob("*.png")):
                    part_sheets[path.stem] = SpriteSheet("graphics", "character", folder, path.name)
            parts[part_name] = part_sheets
        return parts

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
        )

    def _draw_character_part(self, surface, part_name, part_id, frame_rect):
        if part_id is None:
            return
        sheet = self.character_parts.get(part_name, {}).get(str(part_id))
        if sheet is None:
            return
        surface.blit(sheet.get_sprite(*frame_rect), (0, 0))

    def compose_character_frame(self, animation_name, frame_rect, customization):
        _, _, width, height = frame_rect
        normalized = self.normalize_character_customization(customization)
        frame = pygame.Surface((width, height), pygame.SRCALPHA)
        facing = animation_name.split("_", 1)[0]
        weapon_behind = facing in {"up", "left"}

        if weapon_behind:
            self._draw_character_part(frame, "weapon", normalized.get("weapon"), frame_rect)
        for part_name in CHARACTER_LAYER_ORDER:
            self._draw_character_part(frame, part_name, normalized.get(part_name), frame_rect)
        if not weapon_behind:
            self._draw_character_part(frame, "weapon", normalized.get("weapon"), frame_rect)
        return frame

    def get_character_frames(self, animation_name, customization=None):
        cache_key = self._character_cache_key(animation_name, customization)
        cached = self._character_frame_cache.get(cache_key)
        if cached is not None:
            return [frame.copy() for frame in cached]

        frame_data = self.character_animations[animation_name]
        frames = []

        for frame_rect in frame_data:
            frames.append(self.compose_character_frame(animation_name, frame_rect, customization))

        self._character_frame_cache[cache_key] = [frame.copy() for frame in frames]
        return frames

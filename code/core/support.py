"""Asset import and geometry helpers shared by older gameplay modules."""

import os
from pathlib import Path
import pygame
from utils import rp   # <-- the helper we made earlier

IMG_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}


def import_file(*parts):
    """
    Load a single image by path parts relative to project root.
    Example: import_file("graphics", "player.png")
    """
    full_path = Path(rp(*parts))
    return pygame.image.load(str(full_path)).convert_alpha()


def import_folder(*parts):
    """
    Recursively load all images under a folder.
    Example: import_folder("graphics", "player", "run")
    """
    base_dir = Path(rp(*parts))
    surface_list = []
    for root, _, files in os.walk(base_dir):
        for name in files:
            if Path(name).suffix.lower() in IMG_EXTS:
                full_path = Path(root) / name
                surface_list.append(pygame.image.load(str(full_path)).convert_alpha())
    return surface_list


def import_folder_dict(*parts):
    """
    Recursively load images under a folder into a dict keyed by filename (without extension).
    Example: import_folder_dict("graphics", "ui", "icons")
    """
    base_dir = Path(rp(*parts))
    surface_dict = {}
    for root, _, files in os.walk(base_dir):
        for name in files:
            if Path(name).suffix.lower() in IMG_EXTS:
                full_path = Path(root) / name
                key = Path(name).stem  # filename without extension
                surface_dict[key] = pygame.image.load(str(full_path)).convert_alpha()
    return surface_dict


def change_tuple(tuple_a, tuple_b, operation):
    operation = str(operation)
    if operation == "+":
        q = tuple(a + b for a, b in zip(tuple_a, tuple_b))
        return q
    if operation == "-":
        q = tuple(a - b for a, b in zip(tuple_a, tuple_b))
        return q
    if operation == "*":
        q = tuple(a * b for a, b in zip(tuple_a, tuple_b))
        return q
    if operation == "/":
        q = tuple(a / b for a, b in zip(tuple_a, tuple_b))
        return q


class StaticCollider(pygame.sprite.Sprite):
    def __init__(self, rect, groups):
        super().__init__(*groups)
        self.rect = pygame.Rect(rect)   # used for collisions; no image needed
        self.hitbox = self.rect.copy()  # if you keep separate hitboxes


def tile_object_top_left(obj, alignment="bottom"):
    w, h = obj.image.get_width(), obj.image.get_height()
    if alignment == "bottom":         # bottom-center
        return obj.x - w / 2, obj.y - h
    elif alignment == "bottomleft":
        return obj.x, obj.y - h
    elif alignment == "center":
        return obj.x - w / 2, obj.y - h / 2
    else:
        # Fallback: assume Tiled stored x,y as top-left
        return obj.x, obj.y

"""Lazy shared asset caches used across gameplay systems."""

from assets import get_shared_assets


_WATER_FRAME_CACHE = None


def get_water_frames():
    # Get water sprites and load them
    global _WATER_FRAME_CACHE
    if _WATER_FRAME_CACHE is not None:
        return _WATER_FRAME_CACHE

    assets = get_shared_assets()
    frames = []
    for _, frame in sorted(assets.water_frames.items(), key=lambda item: int(item[0])):
        x, y, w, h = frame
        surf = assets.water_sprites.get_sprite(x, y, w, h).convert_alpha()
        frames.append(surf)

    _WATER_FRAME_CACHE = frames
    return _WATER_FRAME_CACHE



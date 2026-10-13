"""Temporary playable setup for the Phase 2 Morning Chores slice."""

from __future__ import annotations

from world.soil import PLANT_MAX_GROWTH_DAYS


def _plant_record(crop_id: str, *, mature: bool) -> dict:
    max_days = PLANT_MAX_GROWTH_DAYS.get(crop_id, 5)
    growth_days = max_days if mature else max(1, max_days // 2)
    return {
        "type": crop_id,
        "age": 1.0 if mature else growth_days / max_days,
        "growth_days": growth_days,
        "max_growth_days": max_days,
        "planted_at": 360.0,
        "planted_day": 1,
        "last_growth_day": 1,
        "last_watered_at": None,
        "last_watered_day": None,
        "dead": False,
    }


def ensure_morning_chores_test_scene(world, soil_layer, game_state):
    """Place five visible test crops near spawn once for a new Story Mode save.

    Phase 3 will replace this setup with the authored home and owned farm. These
    tiles make the Phase 2 quest completable now without waiting several days.
    """
    if game_state.flag("game.mode") != "story":
        return ()
    if game_state.flag("developer.morning_chores_scene_initialized", False):
        return tuple(
            tuple(tile)
            for tile in game_state.flag("developer.morning_chores_tiles", ())
        )

    spawn_x, spawn_y = world.get_spawn_position()
    spawn_tile = (int(spawn_x // world.tile_size), int(spawn_y // world.tile_size))
    candidates = []
    for radius in range(2, 11):
        ring = []
        for offset_y in range(-radius, radius + 1):
            for offset_x in range(-radius, radius + 1):
                if max(abs(offset_x), abs(offset_y)) != radius:
                    continue
                tile = (spawn_tile[0] + offset_x, spawn_tile[1] + offset_y)
                if soil_layer.can_till_at_tile(tile):
                    ring.append(tile)
        ring.sort(key=lambda tile: (tile[1], tile[0]))
        candidates.extend(ring)
        if len(candidates) >= 5:
            break
    if len(candidates) < 5:
        return ()

    selected = candidates[:5]
    crops = (("corn", False), ("tomato", False), ("corn", False), ("corn", True), ("tomato", True))
    touched_chunks = set()
    for world_tile, (crop_id, mature) in zip(selected, crops):
        chunk, (local_x, local_y) = soil_layer.get_chunk_and_local(world_tile)
        chunk.set_saved_tile("soil", local_x, local_y, 1)
        chunk.set_saved_tile("soil_water", local_x, local_y, 0)
        chunk.set_saved_tile("plant", local_x, local_y, _plant_record(crop_id, mature=mature))
        chunk.save_data["flags"].setdefault("player_soil_last_used", {})[(local_x, local_y)] = 360.0
        chunk.runtime["plant_objects"] = {}
        touched_chunks.add(chunk.coord)
    for chunk_coord in touched_chunks:
        world.invalidate_soil_chunk_and_neighbors(chunk_coord)

    game_state.set_flag("developer.morning_chores_tiles", selected)
    game_state.set_flag("developer.morning_chores_scene_initialized", True)
    return tuple(selected)

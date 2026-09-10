"""Versioned, atomic JSON save files for one voyage slot."""

from __future__ import annotations

import json
import re
from pathlib import Path

from inventory_item import Item
from utils import PROJECT_ROOT


SAVE_VERSION = 1
DEFAULT_SAVE_PATH = PROJECT_ROOT / "saves" / "voyage_slot_1.json"
TUPLE_VALUE_FIELDS = {
    "chunk",
    "local_tile",
    "world_tile",
    "world_pos",
    "footprint",
    "render_size",
    "local_rect",
    "yard_rect",
    "yard_gate_tile",
    "light_offset",
    "offset",
    "merchant_world_pos",
    "visitor_world_pos",
    "rest_world_pos",
}
TUPLE_KEY_PATTERN = re.compile(r"^\((-?\d+),\s*(-?\d+)\)$")


def _jsonable(value):
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _restore_json_value(value, field_name=None):
    """Restore tuple-shaped record fields converted to lists by JSON."""
    if isinstance(value, dict):
        return {
            key: _restore_json_value(item, key)
            for key, item in value.items()
        }
    if isinstance(value, list):
        restored = [_restore_json_value(item) for item in value]
        if field_name in TUPLE_VALUE_FIELDS:
            return tuple(restored)
        return restored
    return value


def _restore_flags(flags):
    restored = _restore_json_value(dict(flags or {}))
    activity = restored.get("player_soil_last_used")
    if isinstance(activity, dict):
        normalized = {}
        for key, value in activity.items():
            match = TUPLE_KEY_PATTERN.match(str(key))
            if match:
                normalized[(int(match.group(1)), int(match.group(2)))] = value
            else:
                # Keep unfamiliar keys without attempting unsafe evaluation.
                normalized[key] = value
        restored["player_soil_last_used"] = normalized
    return restored


def _serialize_chunk(chunk):
    save_data = chunk.save_data
    modified = [
        {
            "layer": layer,
            "x": x,
            "y": y,
            "value": _jsonable(value),
        }
        for (layer, x, y), value in save_data["modified_tiles"].items()
    ]
    prop_states = {}
    mutable_keys = ("health", "removed", "age", "harvestable", "death_handled")
    for prop in chunk.props:
        if not isinstance(prop, dict) or not prop.get("id"):
            continue
        state = {key: _jsonable(prop[key]) for key in mutable_keys if key in prop}
        if state:
            prop_states[str(prop["id"])] = state
    return {
        "modified_tiles": modified,
        "removed_props": _jsonable(save_data["removed_props"]),
        "placed_props": _jsonable(save_data["placed_props"]),
        "flags": _jsonable(save_data["flags"]),
        "prop_states": prop_states,
    }


def deserialize_chunk_states(states):
    restored = {}
    for coord_key, state in (states or {}).items():
        x_text, y_text = coord_key.split(",", 1)
        restored[(int(x_text), int(y_text))] = {
            "modified_tiles": {
                (entry["layer"], int(entry["x"]), int(entry["y"])): _restore_json_value(entry.get("value"))
                for entry in state.get("modified_tiles", ())
            },
            "removed_props": set(state.get("removed_props", ())),
            "placed_props": [
                _restore_json_value(record)
                for record in state.get("placed_props", ())
            ],
            "flags": _restore_flags(state.get("flags", {})),
            "prop_states": dict(state.get("prop_states", {})),
        }
    return restored


def _serialize_player(player):
    slots = []
    for slot in player.inventory.slots:
        item = slot.item
        if not item.name or slot.amount <= 0:
            continue
        slots.append({
            "name": item.name,
            "amount": slot.amount,
            "durability": item.durability,
            "max_durability": item.max_durability,
            "place": item.place,
            "placement_type": item.placement_type,
        })
    return {
        "position": [float(player.pos.x), float(player.pos.y)],
        "customization": _jsonable(player.customization),
        "health": int(player.health),
        "max_health": int(player.max_health),
        "coins": int(player.coins),
        "inventory": slots,
        "selected_item_name": player.inventory.selected_item_name,
        "tool_durability": _jsonable(player.tool_durability),
        "broken_tools": _jsonable(player.broken_tools),
        "selected_tool": player.selected_tool,
        "water_amount": int(player.water_amount),
        "seed_inventory": _jsonable(player.seed_inventory),
        "harvested_crops": _jsonable(player.harvested_crops),
        "selected_seed": player.selected_seed,
        "world_hint_seen": _jsonable(player.world_hint_seen),
    }


def restore_player(player, state):
    if not state:
        return
    position = state.get("position", player.pos)
    player.pos.update(position)
    player.rect.midbottom = (round(player.pos.x), round(player.pos.y))
    player.sync_collision_boxes()
    player.health = max(0, int(state.get("health", player.health)))
    player.max_health = max(1, int(state.get("max_health", player.max_health)))
    player.coins = max(0, int(state.get("coins", getattr(player, "coins", 0))))
    player.tool_durability.update({key: int(value) for key, value in state.get("tool_durability", {}).items()})
    player.broken_tools = set(state.get("broken_tools", ()))
    player.water_amount = max(0, min(player.water_capacity, int(state.get("water_amount", player.water_amount))))
    player.seed_inventory.update({key: int(value) for key, value in state.get("seed_inventory", {}).items()})
    player.harvested_crops.update({key: int(value) for key, value in state.get("harvested_crops", {}).items()})
    player.world_hint_seen = set(state.get("world_hint_seen", ()))

    selected_tool = state.get("selected_tool")
    if selected_tool in player.tools:
        player.selected_tool = selected_tool
        player.tool_index = player.tools.index(selected_tool)
        player._sync_equipped_tool(refresh=True)
    selected_seed = state.get("selected_seed")
    if selected_seed in player.seeds:
        player.selected_seed = selected_seed
        player.seed_index = player.seeds.index(selected_seed)

    for slot in player.inventory.slots:
        slot.remove_item(slot.item)
    for entry in state.get("inventory", ()):
        if entry.get("name") == "coin":
            player.coins += int(entry.get("amount", 0))
            continue
        item = Item(
            entry.get("name", ""),
            durability=entry.get("durability"),
            max_durability=entry.get("max_durability"),
            place=entry.get("place"),
            placement_type=entry.get("placement_type"),
        )
        player.inventory.add_item_to_slot(item, int(entry.get("amount", 1)))
    player.inventory.selected_item_name = state.get("selected_item_name")


def _npc_key(npc, index):
    stall = getattr(npc, "stall", None)
    if stall is not None:
        return f"merchant:{stall.stall_id}"
    return f"npc:{index}"


def _serialize_npcs(npc_manager):
    if npc_manager is None:
        return []
    records = []
    for index, npc in enumerate(npc_manager.npcs):
        record = {
            "key": _npc_key(npc, index),
            "position": [float(npc.pos.x), float(npc.pos.y)],
            "health": int(npc.health),
            "hostile": bool(getattr(npc, "hostile", False)),
            "daily_activity": getattr(npc, "daily_activity", None),
        }
        for name in ("home_pos", "work_pos", "social_pos"):
            value = getattr(npc, name, None)
            if value is not None:
                record[name] = [float(value.x), float(value.y)]
        if hasattr(npc, "offers"):
            record["offers"] = _jsonable(npc.offers)
        records.append(record)
    return records


def restore_npcs(npc_manager, states):
    if npc_manager is None:
        return
    by_key = {_npc_key(npc, index): npc for index, npc in enumerate(npc_manager.npcs)}
    for state in states or ():
        npc = by_key.get(state.get("key"))
        if npc is None:
            continue
        npc.pos.update(state.get("position", npc.pos))
        npc.rect.midbottom = (round(npc.pos.x), round(npc.pos.y))
        npc.collision_box.center = npc.rect.center
        npc.health = max(0, int(state.get("health", npc.health)))
        npc.hostile = bool(state.get("hostile", npc.hostile))
        npc.path.clear()
        npc.target_tile = None
        for name in ("home_pos", "work_pos", "social_pos"):
            if name in state and hasattr(npc, name):
                getattr(npc, name).update(state[name])
        if "offers" in state and hasattr(npc, "offers"):
            npc.offers = list(state["offers"])
        if hasattr(npc, "daily_activity"):
            npc.daily_activity = state.get("daily_activity")
        stall = getattr(npc, "stall", None)
        if stall is not None:
            stall.set_open(npc.health > 0 and npc.daily_activity == "work")


def _serialize_weather(weather):
    time = weather.time
    seasons = weather.seasons
    return {
        "time": float(time.time),
        "day": int(time.day),
        "season_index": int(seasons.current_season_index),
        "season_start_day": int(seasons.season_start_day),
        "season_length": int(seasons.season_length),
        "weather": seasons.weather,
        "weather_duration": int(seasons.weather_duration),
        "next_weather_hour": int(seasons.next_weather_hour),
    }


def restore_weather(weather, state):
    if not state:
        return
    weather.time.time = float(state.get("time", weather.time.time))
    weather.time.day = max(1, int(state.get("day", weather.time.day)))
    weather.time.hours = int(weather.time.time // 60)
    weather.time.minutes = int(weather.time.time % 60)
    seasons = weather.seasons
    seasons.current_season_index = int(state.get("season_index", seasons.current_season_index)) % len(seasons.seasons)
    seasons.current_season = seasons.seasons[seasons.current_season_index]
    seasons.current_day = weather.time.day
    seasons.season_start_day = int(state.get("season_start_day", seasons.season_start_day))
    seasons.season_length = int(state.get("season_length", seasons.season_length))
    seasons.weather = state.get("weather", seasons.weather)
    seasons.weather_duration = int(state.get("weather_duration", seasons.weather_duration))
    seasons.next_weather_hour = int(state.get("next_weather_hour", seasons.next_weather_hour)) % 24
    seasons.next_weather_time = seasons.next_weather_hour * 60


class SaveGameManager:
    def __init__(self, path=DEFAULT_SAVE_PATH):
        self.path = Path(path)

    @property
    def exists(self):
        return self.path.is_file()

    def capture(self, world_run, world, player, weather, npc_manager):
        chunks = {}
        for coord, chunk in world.loaded_chunks.items():
            state = _serialize_chunk(chunk)
            if any((state["modified_tiles"], state["removed_props"], state["placed_props"], state["flags"], state["prop_states"])):
                chunks[f"{coord[0]},{coord[1]}"] = state
        return {
            "version": SAVE_VERSION,
            "world_run": {
                "seed": int(world_run.seed),
                "current_index": int(world_run.current_index),
                "discovered_islands": sorted(world_run.discovered_islands),
            },
            "world": {"chunks": chunks},
            "player": _serialize_player(player),
            "weather": _serialize_weather(weather),
            "npcs": _serialize_npcs(npc_manager),
        }

    def save(self, world_run, world, player, weather, npc_manager):
        payload = self.capture(world_run, world, player, weather, npc_manager)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        temp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temp_path.replace(self.path)
        return self.path

    def load(self):
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        version = int(payload.get("version", 0))
        if version != SAVE_VERSION:
            raise ValueError(f"Unsupported save version {version}")
        return payload

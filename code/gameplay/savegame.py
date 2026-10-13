"""Versioned, atomic JSON save files for one voyage slot."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from inventory_item import Item
from gameplay.config import PLAYER_MAX_HEALTH
from gameplay.game_state import GameState
from utils import PROJECT_ROOT


SAVE_VERSION = 2
SAVE_DIRECTORY = PROJECT_ROOT / "saves"
DEFAULT_SAVE_PATH = SAVE_DIRECTORY / "save_1.json"
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
DEFAULT_SAVE_NAME_PATTERN = re.compile(r"^save_(\d+)$", re.IGNORECASE)
INVALID_FILENAME_PATTERN = re.compile(r"[^\w\-. ]+", re.UNICODE)


@dataclass(frozen=True)
class SaveSlot:
    """Lightweight startup-menu information for one save file."""

    path: Path
    name: str
    saved_at: str = ""
    mode: str = "voyage"
    seed: int = 0
    day: int = 1
    location_id: str = "player_farm"
    valid: bool = True
    error: str = ""


def _display_name_from_path(path):
    words = path.stem.replace("_", " ").strip()
    return words.title() if words else "Saved Game"


def _safe_filename(name):
    cleaned = INVALID_FILENAME_PATTERN.sub("", str(name or "")).strip(" .")
    cleaned = re.sub(r"\s+", "_", cleaned)
    cleaned = cleaned[:60].rstrip(" ._")
    return cleaned or "save"


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
        "equipment": _jsonable(getattr(player, "equipment_state", {})),
        "selected_tool": player.selected_tool,
        "selected_weapon": getattr(player, "selected_weapon", "sword"),
        "selection_slot": getattr(player, "selected_selection_slot", "tool"),
        "water_amount": int(player.water_amount),
        "seed_inventory": _jsonable(player.seed_inventory),
        "harvested_crops": _jsonable(player.harvested_crops),
        "selected_seed": player.selected_seed,
        "selected_consumable": getattr(player, "selected_consumable", None),
        "hotbar_slot_index": int(getattr(player, "hotbar_slot_index", 0)),
        "world_hint_seen": _jsonable(player.world_hint_seen),
    }


def normalize_saved_player_health(saved_health, saved_max_health):
    """Raise legacy health caps while preserving the player's health ratio."""
    saved_max_health = max(1, int(saved_max_health))
    saved_health = max(0, min(saved_max_health, int(saved_health)))
    restored_max = max(PLAYER_MAX_HEALTH, saved_max_health)
    if saved_max_health < PLAYER_MAX_HEALTH:
        saved_health = round(restored_max * (saved_health / saved_max_health))
    return max(0, min(restored_max, saved_health)), restored_max


def restore_player(player, state):
    if not state:
        return
    position = state.get("position", player.pos)
    player.pos.update(position)
    player.rect.midbottom = (round(player.pos.x), round(player.pos.y))
    player.sync_collision_boxes()
    player.health, player.max_health = normalize_saved_player_health(
        state.get("health", player.health),
        state.get("max_health", player.max_health),
    )
    player.coins = max(0, int(state.get("coins", getattr(player, "coins", 0))))
    equipment = state.get("equipment")
    if equipment and hasattr(player, "equipment_state"):
        from data.equipment import EQUIPMENT_DEFINITIONS, normalize_equipment_state

        player.equipment_state = {
            equipment_id: normalize_equipment_state(
                equipment_id,
                equipment.get(equipment_id),
            )
            for equipment_id in EQUIPMENT_DEFINITIONS
        }
        player.sync_equipment_compatibility()
    else:
        player.tool_durability.update({key: int(value) for key, value in state.get("tool_durability", {}).items()})
        player.broken_tools = set(state.get("broken_tools", ()))
        if hasattr(player, "import_legacy_equipment_state"):
            player.import_legacy_equipment_state()
    player.water_amount = max(0, min(player.water_capacity, int(state.get("water_amount", player.water_amount))))
    player.seed_inventory.update({key: int(value) for key, value in state.get("seed_inventory", {}).items()})
    player.harvested_crops.update({key: int(value) for key, value in state.get("harvested_crops", {}).items()})
    player.world_hint_seen = set(state.get("world_hint_seen", ()))

    selected_tool = state.get("selected_tool")
    # Migrate old combined-slot saves by moving a combat item into the new
    # weapon slot while retaining the default resource tool.
    legacy_weapon = selected_tool if selected_tool in getattr(player, "weapons", ()) else None
    if selected_tool in player.tools:
        player.selected_tool = selected_tool
        player.tool_index = player.tools.index(selected_tool)
    selected_weapon = state.get("selected_weapon", legacy_weapon)
    if selected_weapon in getattr(player, "weapons", ()):
        player.selected_weapon = selected_weapon
        player.weapon_index = player.weapons.index(selected_weapon)
        player._sync_equipped_weapon(refresh=True)
    selection_slot = state.get("selection_slot")
    if selection_slot in getattr(player, "selection_slots", ()):
        player.selected_selection_slot = selection_slot
        player.selection_slot_index = player.selection_slots.index(selection_slot)
        player._sync_equipped_weapon(refresh=True)
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
    selected_consumable = state.get("selected_consumable")
    if selected_consumable and player.inventory.count_item(selected_consumable):
        player.selected_consumable = selected_consumable
        player.inventory.hotbar_item_name = selected_consumable
    player.hotbar_slot_index = max(0, min(4, int(state.get("hotbar_slot_index", 0))))


def _npc_key(npc, index):
    save_id = getattr(npc, "save_id", None)
    if save_id:
        return str(save_id)
    story_id = getattr(npc, "story_id", None)
    if story_id:
        return f"story:{story_id}"
    stall = getattr(npc, "stall", None)
    if stall is not None:
        return f"merchant:{stall.stall_id}"
    return f"npc:{index}"


def _serialize_npcs(npc_manager):
    if npc_manager is None:
        return []
    records = []
    for index, npc in enumerate(npc_manager.npcs):
        if getattr(npc, "managed_by_encounter", False):
            continue
        record = {
            "key": _npc_key(npc, index),
            "visual_id": getattr(npc, "npc_id", None),
            "position": [float(npc.pos.x), float(npc.pos.y)],
            "health": int(npc.health),
            "hostile": bool(getattr(npc, "hostile", False)),
            "daily_activity": getattr(npc, "daily_activity", None),
            "location_id": getattr(npc, "location_id", "player_farm"),
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
    by_key = {}
    for index, npc in enumerate(npc_manager.npcs):
        by_key[_npc_key(npc, index)] = npc
        # Version-1 saves used list positions. Keep those keys readable while
        # all new saves use the actor's stable save_id.
        by_key.setdefault(f"npc:{index}", npc)
    for state in states or ():
        npc = by_key.get(state.get("key"))
        if npc is None:
            continue
        npc.pos.update(state.get("position", npc.pos))
        npc.rect.midbottom = (round(npc.pos.x), round(npc.pos.y))
        npc.collision_box.center = npc.rect.center
        npc.health = max(0, int(state.get("health", npc.health)))
        npc.hostile = bool(state.get("hostile", npc.hostile))
        npc.location_id = str(state.get("location_id", getattr(npc, "location_id", "player_farm")))
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
    def __init__(self, path=None, save_directory=None):
        self.path = Path(path) if path is not None else None
        if save_directory is not None:
            self.save_directory = Path(save_directory)
        elif self.path is not None:
            self.save_directory = self.path.parent
        else:
            self.save_directory = SAVE_DIRECTORY
        self.current_name = ""

    @property
    def exists(self):
        if self.path is not None:
            return self.path.is_file()
        return bool(self.list_saves())

    def list_saves(self):
        """Return every JSON save, newest first, without rejecting old slots."""
        if not self.save_directory.is_dir():
            return []

        slots = []
        for path in self.save_directory.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                metadata = payload.get("save", {})
                game_state = payload.get("game_state", {})
                flags = game_state.get("flags", {}) if isinstance(game_state, dict) else {}
                weather = payload.get("weather", {})
                name = str(metadata.get("name") or _display_name_from_path(path))
                slots.append(
                    SaveSlot(
                        path=path,
                        name=name,
                        saved_at=str(metadata.get("saved_at") or ""),
                        mode=str(flags.get("game.mode", "voyage")),
                        seed=int(payload.get("world_run", {}).get("seed", 0)),
                        day=max(1, int(weather.get("day", 1))),
                        location_id=str(game_state.get("current_location_id", "player_farm")),
                    )
                )
            except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
                slots.append(
                    SaveSlot(
                        path=path,
                        name=_display_name_from_path(path),
                        valid=False,
                        error=str(error),
                    )
                )
        return sorted(
            slots,
            key=lambda slot: (
                slot.path.stat().st_mtime if slot.path.exists() else 0,
                slot.name.casefold(),
            ),
            reverse=True,
        )

    def next_default_name(self):
        """Choose the next numerical save name without filling old gaps."""
        highest = 0
        for slot in self.list_saves():
            for candidate in (slot.name, slot.path.stem):
                match = DEFAULT_SAVE_NAME_PATTERN.fullmatch(str(candidate).strip())
                if match:
                    highest = max(highest, int(match.group(1)))
        return f"save_{highest + 1}"

    def _select_save_target(self, save_name=None):
        requested_name = str(save_name or "").strip()
        if requested_name:
            candidate = self.save_directory / f"{_safe_filename(requested_name)}.json"
            if candidate.exists() and candidate != self.path:
                suffix = 2
                base = _safe_filename(requested_name)
                while (self.save_directory / f"{base}_{suffix}.json").exists():
                    suffix += 1
                candidate = self.save_directory / f"{base}_{suffix}.json"
                requested_name = f"{requested_name} ({suffix})"
            self.current_name = requested_name
            self.path = candidate
        elif self.path is None:
            self.current_name = self.next_default_name()
            self.path = self.save_directory / f"{self.current_name}.json"
        elif not self.current_name:
            self.current_name = self._name_from_existing_save(self.path)
        return self.path, self.current_name

    @staticmethod
    def _name_from_existing_save(path):
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
            return str(payload.get("save", {}).get("name") or _display_name_from_path(Path(path)))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return _display_name_from_path(Path(path))

    def capture(self, world_run, world, player, weather, npc_manager, game_state=None):
        game_state = game_state or getattr(player, "game_state", None) or GameState()
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
                "world_kind": getattr(world_run, "world_kind", "island"),
            },
            "world": {"chunks": chunks},
            "player": _serialize_player(player),
            "weather": _serialize_weather(weather),
            "npcs": _serialize_npcs(npc_manager),
            "game_state": _jsonable(game_state.to_dict()),
        }

    def save(
        self,
        world_run,
        world,
        player,
        weather,
        npc_manager,
        game_state=None,
        save_name=None,
    ):
        previous_path = self.path
        path, display_name = self._select_save_target(save_name)
        payload = self.capture(
            world_run,
            world,
            player,
            weather,
            npc_manager,
            game_state,
        )
        created_at = ""
        if path.is_file():
            try:
                created_at = str(
                    json.loads(path.read_text(encoding="utf-8"))
                    .get("save", {})
                    .get("created_at", "")
                )
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                created_at = ""
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        payload["save"] = {
            "name": display_name,
            "created_at": created_at or timestamp,
            "saved_at": timestamp,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(path.suffix + ".tmp")
        temp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temp_path.replace(path)
        if previous_path is not None and previous_path != path and previous_path.is_file():
            previous_path.unlink()
        return path

    def load(self, path=None):
        if path is not None:
            self.path = Path(path)
        if self.path is None:
            saves = self.list_saves()
            if not saves:
                raise FileNotFoundError("No saved games were found.")
            self.path = saves[0].path
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        version = int(payload.get("version", 0))
        if version == 1:
            payload = self._migrate_v1(payload)
        elif version != SAVE_VERSION:
            raise ValueError(f"Unsupported save version {version}")
        payload["game_state"] = GameState.from_dict(payload.get("game_state")).to_dict()
        self.current_name = str(
            payload.get("save", {}).get("name") or _display_name_from_path(self.path)
        )
        return payload

    @staticmethod
    def _migrate_v1(payload):
        migrated = dict(payload)
        migrated["version"] = SAVE_VERSION
        migrated.setdefault("game_state", GameState().to_dict())
        return migrated

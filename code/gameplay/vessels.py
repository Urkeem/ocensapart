"""Runtime ownership, input, persistence, and interactions for vessels."""

from __future__ import annotations

import pygame

from entities.vessel import PirateShip, PlayerBoat
from gameplay.interactions import InteractionTarget


class VesselManager:
    def __init__(self, world, player, game_state, event_dispatcher=None, controller_input=None):
        self.world = world
        self.player = player
        self.game_state = game_state
        self.event_dispatcher = event_dispatcher
        self.controller_input = controller_input or getattr(player, "controller_input", None)
        boat_record = game_state.transports.get("player_boat", {})
        ship_record = game_state.transports.get("pirate_ship", {})
        boat_position = boat_record.get("position") or self._find_shoreline_water() or tuple(player.pos)
        ship_position = ship_record.get("position") or boat_position
        self.player_boat = PlayerBoat(boat_position, game_state, event_dispatcher)
        self.pirate_ship = PirateShip(ship_position, game_state, event_dispatcher)
        self.last_message = ""
        self.message_callback = None
        self._restore(boat_record, ship_record)

    @property
    def vessels(self):
        return self.player_boat, self.pirate_ship

    def _find_shoreline_water(self):
        tile_size = self.world.tile_size
        chunk_width, chunk_height = self.world.chunk_size
        player_tile = (int(self.player.pos.x // tile_size), int(self.player.pos.y // tile_size))

        def is_loaded_land(tile):
            chunk_coord = (tile[0] // chunk_width, tile[1] // chunk_height)
            neighbor_chunk = self.world.loaded_chunks.get(chunk_coord)
            if neighbor_chunk is None:
                return False
            index = neighbor_chunk.get_index(tile[0] % chunk_width, tile[1] % chunk_height)
            return neighbor_chunk.layers["terrain"][index] != -1

        candidates = []
        for chunk in self.world.loaded_chunks.values():
            width, height = chunk.chunk_size
            for local_y in range(height):
                for local_x in range(width):
                    index = chunk.get_index(local_x, local_y)
                    if chunk.layers["terrain"][index] != -1:
                        continue
                    tile = chunk.get_world_tile(local_x, local_y)
                    if self.world.get_water_locality(tile) != "ocean":
                        continue
                    if not any(
                        is_loaded_land((tile[0] + dx, tile[1] + dy))
                        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
                    ):
                        continue
                    distance = abs(tile[0] - player_tile[0]) + abs(tile[1] - player_tile[1])
                    candidates.append((distance, tile))
        if not candidates:
            return None
        _, tile = min(candidates)
        return ((tile[0] + 0.5) * tile_size, (tile[1] + 0.7) * tile_size)

    def _restore(self, boat_record, ship_record):
        self.player_boat.animator.direction = boat_record.get("direction", "down")
        self.player_boat.shore_anchor = boat_record.get("shore_anchor")
        self.player_boat.location_id = boat_record.get("location_id", "player_farm")
        self.pirate_ship.animator.direction = ship_record.get("direction", "down")
        self.pirate_ship.docked_at = ship_record.get("docked_at")
        self.pirate_ship.travel_destination = ship_record.get("travel_destination")
        self.pirate_ship.location_id = ship_record.get("location_id", "player_farm")
        if boat_record.get("mounted") and self.player_boat.unlocked:
            self.player_boat.mounted_player = self.player
            self.player.mounted_vessel = self.player_boat
            self.player.hidden_by_vessel = True
            self.player_boat._attach_player()

    def _show(self, message):
        self.last_message = str(message)
        if self.message_callback is not None:
            self.message_callback(self.last_message)

    def unlock(self, vessel_id):
        if vessel_id not in {"player_boat", "pirate_ship"}:
            raise KeyError(f"Unknown vessel {vessel_id!r}")
        record = self.game_state.transports.setdefault(vessel_id, {})
        changed = not bool(record.get("unlocked"))
        record["unlocked"] = True
        self.game_state.unlock(f"transport.{vessel_id}")
        return changed

    def _movement_direction(self):
        keys = pygame.key.get_pressed()
        keyboard = pygame.Vector2(
            int(keys[pygame.K_d] or keys[pygame.K_RIGHT]) - int(keys[pygame.K_a] or keys[pygame.K_LEFT]),
            int(keys[pygame.K_s] or keys[pygame.K_DOWN]) - int(keys[pygame.K_w] or keys[pygame.K_UP]),
        )
        controller = self.controller_input.movement_vector() if self.controller_input is not None else pygame.Vector2()
        if controller.length_squared() > 0:
            return controller
        return keyboard.normalize() if keyboard.length_squared() > 0 else keyboard

    def update(self, dt, *, controls_enabled=True):
        direction = self._movement_direction() if controls_enabled and self.player_boat.mounted else pygame.Vector2()
        self.player_boat.update_controlled(dt, direction, self.world)
        self.pirate_ship.update(dt)
        self.player_boat.persist()
        self.pirate_ship.persist()

    def _mount(self):
        success, reason = self.player_boat.mount(self.player, self.world)
        if not success:
            self._show(reason)
        else:
            self.player_boat.persist()
        return success

    def _dismount(self):
        success, reason = self.player_boat.dismount(self.world)
        if not success:
            self._show(reason)
        return success

    def interaction_targets(self, player, max_distance):
        if self.player_boat.mounted:
            yield InteractionTarget(
                "player-boat-dismount",
                "vessel",
                self.player_boat,
                tuple(player.feet_collision_box.center),
                priority=20,
                prompt="Step ashore",
                action=self._dismount,
            )
            return
        if self.player_boat.location_id == self.game_state.current_location_id:
            yield InteractionTarget(
                "player-boat-mount",
                "vessel",
                self.player_boat,
                tuple(self.player_boat.pos),
                priority=8,
                prompt="Board boat",
                action=self._mount,
            )

    def visible_vessels(self, current_location_id):
        return tuple(
            vessel
            for vessel in self.vessels
            if vessel.location_id == current_location_id
            and (vessel is self.player_boat or self.pirate_ship.unlocked)
        )

    def collision_objects(self, current_location_id):
        return tuple(
            vessel
            for vessel in self.visible_vessels(current_location_id)
            if vessel is not self.player_boat or not self.player_boat.mounted
        )

    def set_context(self, world):
        self.world = world

"""Shared vessel animation plus player-boat and story-ship actors."""

from __future__ import annotations

import pygame

from data.content_manifest import FrameSequenceSpec, SheetSpec, VESSEL_ASSETS
from gameplay.events import VesselDocked, VesselMounted, publish_from
from utils import rp


def _load_image(path):
    image = pygame.image.load(rp(*path.split("/")))
    return image.convert_alpha() if pygame.display.get_surface() is not None else image


class VesselAnimator:
    """Load manifest animations lazily and keep wind overlays frame-locked."""

    def __init__(self, vessel_id, *, fps=9.0, display_scale=1.0):
        self.spec = VESSEL_ASSETS[vessel_id]
        self.vessel_id = vessel_id
        self.fps = float(fps)
        self.display_scale = float(display_scale)
        self.direction = "down"
        self.state = "idle"
        self.frame_index = 0.0
        self._frames = {}
        self._scaled = {}
        self._flipped = {}

    def _resolve(self, direction=None, state=None):
        direction = direction or self.direction
        state = state or self.state
        requested = f"{direction}_{state}"
        if requested in self.spec.animations:
            return requested, False
        if requested in self.spec.horizontal_flip:
            return self.spec.horizontal_flip[requested], True
        sideways = f"sideways_{state}"
        if direction == "right" and sideways in self.spec.animations:
            return sideways, False
        raise KeyError(f"No {self.vessel_id!r} animation for {requested!r}")

    def _load_frames(self, animation_id):
        cached = self._frames.get(animation_id)
        if cached is not None:
            return cached
        animation = self.spec.animations[animation_id]
        if isinstance(animation, FrameSequenceSpec):
            frames = tuple(_load_image(path) for path in animation.paths)
        elif isinstance(animation, SheetSpec):
            sheet = _load_image(animation.path)
            frames = tuple(sheet.subsurface(pygame.Rect(rect)).copy() for rect in animation.frame_rects())
        else:
            raise TypeError(f"Unsupported vessel animation spec {type(animation).__name__}")
        self._frames[animation_id] = frames
        return frames

    def _prepared_frame(self, animation_id, index, flipped):
        key = (animation_id, index, flipped, self.display_scale)
        cached = (self._flipped if flipped else self._scaled).get(key)
        if cached is not None:
            return cached
        frame = self._load_frames(animation_id)[index]
        if flipped:
            frame = pygame.transform.flip(frame, True, False)
        if self.display_scale != 1.0:
            frame = pygame.transform.smoothscale(
                frame,
                (
                    max(1, round(frame.get_width() * self.display_scale)),
                    max(1, round(frame.get_height() * self.display_scale)),
                ),
            )
        (self._flipped if flipped else self._scaled)[key] = frame
        return frame

    def set_motion(self, direction, sailing):
        if direction in {"up", "down", "left", "right"}:
            self.direction = direction
        next_state = "sailing" if sailing else "idle"
        if next_state != self.state:
            self.state = next_state
            self.frame_index = 0.0

    def update(self, dt):
        animation_id, _ = self._resolve()
        count = len(self._load_frames(animation_id))
        self.frame_index = (self.frame_index + max(0.0, float(dt)) * self.fps) % count

    @property
    def synchronized_frame_number(self):
        animation_id, _ = self._resolve()
        return int(self.frame_index) % len(self._load_frames(animation_id))

    def current_layers(self):
        animation_id, flipped = self._resolve()
        frame_number = self.synchronized_frame_number
        base = self._prepared_frame(animation_id, frame_number, flipped)
        overlay_id = self.spec.synchronized_overlays.get(animation_id)
        if overlay_id is None:
            return (base,)
        overlay_frames = self._load_frames(overlay_id)
        overlay = self._prepared_frame(overlay_id, frame_number % len(overlay_frames), flipped)
        return base, overlay

    def compose(self):
        layers = self.current_layers()
        if len(layers) == 1:
            return layers[0]
        composed = layers[0].copy()
        composed.blit(layers[1], (0, 0))
        return composed


class VesselActor:
    def __init__(self, vessel_id, position, *, fps, display_scale):
        self.vessel_id = vessel_id
        self.save_id = f"vessel:{vessel_id}"
        self.managed_by_vessel = True
        self.location_id = "player_farm"
        self.is_alive = False
        self.can_take_damage = False
        self.pos = pygame.Vector2(position)
        self.animator = VesselAnimator(vessel_id, fps=fps, display_scale=display_scale)
        self.image = self.animator.compose()
        self.rect = self.image.get_rect(midbottom=(round(self.pos.x), round(self.pos.y)))
        self.collision_box = pygame.Rect(0, 0, 56, 34)
        self.collision_box.midbottom = self.rect.midbottom

    @property
    def sort_y(self):
        return self.rect.bottom

    @property
    def center(self):
        return self.rect.center

    def _sync_image(self):
        midbottom = (round(self.pos.x), round(self.pos.y))
        self.image = self.animator.compose()
        self.rect = self.image.get_rect(midbottom=midbottom)
        self.collision_box.midbottom = midbottom

    def update(self, dt):
        self.animator.update(dt)
        self._sync_image()

    def serialize(self):
        return {
            "unlocked": False,
            "position": [float(self.pos.x), float(self.pos.y)],
            "location_id": self.location_id,
            "direction": self.animator.direction,
            "state": self.animator.state,
        }


class PlayerBoat(VesselActor):
    SPEED = 190.0

    def __init__(self, position, game_state=None, event_dispatcher=None):
        self.game_state = game_state
        self.event_dispatcher = event_dispatcher
        self.mounted_player = None
        self.shore_anchor = None
        super().__init__("player_boat", position, fps=10.0, display_scale=0.38)

    @property
    def unlocked(self):
        if self.game_state is None:
            return True
        record = self.game_state.transports.get(self.vessel_id, {})
        return bool(record.get("unlocked")) or "transport.player_boat" in self.game_state.progression.unlocks

    @property
    def mounted(self):
        return self.mounted_player is not None

    def _tile_for(self, position, world):
        return int(position[0] // world.tile_size), int(position[1] // world.tile_size)

    def _is_water(self, position, world):
        return world.get_water_locality(self._tile_for(position, world)) is not None

    def can_occupy(self, position, world):
        sample = max(8, world.tile_size // 4)
        return all(
            self._is_water((position[0] + dx, position[1] + dy), world)
            for dx, dy in ((0, 0), (-sample, 0), (sample, 0), (0, -sample), (0, sample))
        )

    def mount(self, player, world):
        if not self.unlocked:
            return False, "The boat is still locked. Find a way to secure it first."
        if self.mounted:
            return True, ""
        if pygame.Vector2(player.feet_collision_box.center).distance_to(self.pos) > 112:
            return False, "Move closer to the boat to board it."
        if not self.can_occupy(self.pos, world):
            return False, "The boat must be launched from a shoreline anchor."
        self.mounted_player = player
        player.mounted_vessel = self
        player.hidden_by_vessel = True
        self._attach_player()
        publish_from(
            self,
            VesselMounted(
                event_id=self.game_state.next_event_id("vessel_mounted") if self.game_state else "vessel_mounted:1",
                vessel_id=self.vessel_id,
            ),
        )
        return True, ""

    def _land_at(self, tile, world):
        point = pygame.Vector2((tile[0] + 0.5) * world.tile_size, (tile[1] + 0.82) * world.tile_size)
        terrain_getter = getattr(world, "get_world_terrain_tile", None)
        if world.get_water_locality(tile) is not None:
            return None
        if terrain_getter is not None and terrain_getter(*tile) == -1:
            return None
        return point

    def nearby_shore_anchor(self, world):
        tile_x, tile_y = self._tile_for(self.pos, world)
        candidates = (
            (tile_x, tile_y + 1),
            (tile_x + 1, tile_y),
            (tile_x - 1, tile_y),
            (tile_x, tile_y - 1),
            (tile_x + 1, tile_y + 1),
            (tile_x - 1, tile_y + 1),
            (tile_x + 1, tile_y - 1),
            (tile_x - 1, tile_y - 1),
        )
        return next((point for tile in candidates if (point := self._land_at(tile, world)) is not None), None)

    def dismount(self, world):
        if not self.mounted:
            return False, "You are not aboard the boat."
        anchor = self.nearby_shore_anchor(world)
        if anchor is None:
            return False, "Sail beside a shoreline before leaving the boat."
        player = self.mounted_player
        self.mounted_player = None
        player.mounted_vessel = None
        player.hidden_by_vessel = False
        player.pos.update(anchor)
        player.rect.midbottom = (round(anchor.x), round(anchor.y))
        player.sync_collision_boxes()
        self.shore_anchor = tuple(anchor)
        self.persist()
        return True, ""

    def _attach_player(self):
        if self.mounted_player is None:
            return
        player = self.mounted_player
        player.pos.update(self.pos)
        player.rect.midbottom = (round(self.pos.x), round(self.pos.y))
        player.direction.update(0, 0)
        player.sync_collision_boxes()

    def move(self, direction, dt, world):
        direction = pygame.Vector2(direction)
        sailing = direction.length_squared() > 0
        if sailing:
            direction = direction.normalize()
            if abs(direction.x) > abs(direction.y):
                facing = "right" if direction.x > 0 else "left"
            else:
                facing = "down" if direction.y > 0 else "up"
            candidate = self.pos + direction * self.SPEED * max(0.0, float(dt))
            if self.can_occupy(candidate, world):
                self.pos.update(candidate)
            self.animator.set_motion(facing, True)
            if self.mounted_player is not None:
                self.mounted_player.facing = facing
        else:
            self.animator.set_motion(self.animator.direction, False)
        self.animator.update(dt)
        self._sync_image()
        self._attach_player()

    def update_controlled(self, dt, direction, world):
        if self.mounted:
            self.move(direction, dt, world)
        else:
            self.animator.set_motion(self.animator.direction, False)
            super().update(dt)

    def allows_sea_fishing(self):
        if not self.mounted:
            return False
        if self.game_state is None:
            return True
        return self.unlocked and self.game_state.progression.fishing_points >= 150

    def persist(self):
        if self.game_state is None:
            return
        unlocked = self.unlocked
        record = self.serialize()
        record.update({"unlocked": unlocked, "mounted": self.mounted, "shore_anchor": self.shore_anchor})
        self.game_state.transports[self.vessel_id] = record


class PirateShip(VesselActor):
    def __init__(self, position, game_state=None, event_dispatcher=None):
        self.game_state = game_state
        self.event_dispatcher = event_dispatcher
        self.docked_at = None
        self.travel_destination = None
        super().__init__("pirate_ship", position, fps=8.0, display_scale=0.30)
        self.collision_box.size = (128, 72)
        self.collision_box.midbottom = self.rect.midbottom

    @property
    def unlocked(self):
        if self.game_state is None:
            return True
        return bool(self.game_state.transports.get(self.vessel_id, {}).get("unlocked")) or "transport.pirate_ship" in self.game_state.progression.unlocks

    def dock(self, location_id, position=None):
        if position is not None:
            self.pos.update(position)
        self.docked_at = location_id
        self.travel_destination = None
        self.location_id = location_id
        self.animator.set_motion(self.animator.direction, False)
        self.persist()
        publish_from(
            self,
            VesselDocked(
                event_id=self.game_state.next_event_id("vessel_docked") if self.game_state else "vessel_docked:1",
                vessel_id=self.vessel_id,
                location_id=location_id,
            ),
        )

    def begin_travel(self, destination, direction="right"):
        if not self.unlocked:
            return False, "Pirate's ship has not joined the rescue yet."
        self.docked_at = None
        self.travel_destination = destination
        self.animator.set_motion(direction, True)
        self.persist()
        return True, ""

    def update(self, dt):
        self.animator.set_motion(self.animator.direction, self.travel_destination is not None)
        super().update(dt)

    def persist(self):
        if self.game_state is None:
            return
        record = self.serialize()
        record.update(
            {
                "unlocked": self.unlocked,
                "docked_at": self.docked_at,
                "travel_destination": self.travel_destination,
            }
        )
        self.game_state.transports[self.vessel_id] = record

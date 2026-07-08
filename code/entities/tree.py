"""Tree visuals, fruit particles, chopping, drops, and ecology integration."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from random import Random
from typing import Any, Optional

import pygame
from math import sin

from assets import LoadAssets
from inventory_item import Item
from sprites import AnimatedWorldObject, WorldObject
from core.support import import_file, rp


@dataclass(frozen=True)
class TreeVisualProfile:
    species: str
    base_name: str
    sprite_sheet_name: str
    collision_inflate: tuple[float, float]
    collision_offset_y: int
    canopy_offsets: tuple[tuple[int, int], ...]
    fruit_chance: float = 0.0
    default_health: int = 5
    wood_drop: int = 3


TREE_VISUALS: dict[str, TreeVisualProfile] = {
    "palm": TreeVisualProfile(
        "palm", "palm", "all_trees_sprites", (-0.9, -0.9), 25,
        ((-14, -110), (10, -96), (24, -122)),
        fruit_chance=0.55,
        default_health=4,
        wood_drop=3,
    ),
    "oak": TreeVisualProfile(
        "oak", "oak", "all_trees_sprites", (-0.8, -0.9), 25,
        ((-20, -118), (10, -130), (28, -108), (-2, -96)),
        fruit_chance=0.35,
        default_health=6,
        wood_drop=5,
    ),
    "birch": TreeVisualProfile(
        "birch", "birch", "all_trees_sprites", (-0.8, -0.9), 25,
        ((-16, -104), (14, -114), (0, -88)),
        fruit_chance=0.25,
        default_health=4,
        wood_drop=3,
    ),
    "pine": TreeVisualProfile(
        "pine", "pine", "all_trees_sprites", (-0.8, -0.9), 25,
        ((-12, -124), (4, -106), (18, -138)),
        fruit_chance=0.15,
        default_health=5,
        wood_drop=4,
    ),
    "mangrove": TreeVisualProfile(
        "mangrove", "mangrove", "all_trees_sprites", (-0.8, -0.9), 25,
        ((-10, -108), (18, -100), (0, -90)),
        fruit_chance=0.25,
        default_health=4,
        wood_drop=3,
    ),
    "dead_tree": TreeVisualProfile(
        "dead_tree", "dead_tree", "all_trees_sprites", (-0.8, -0.9), 25,
        (),
        fruit_chance=0.0,
        default_health=2,
        wood_drop=1,
    ),
    "apple": TreeVisualProfile(
        "apple", "apple", "all_trees_sprites", (-0.8, -0.9), 25,
        ((-12, -124), (4, -106), (18, -138)),
        fruit_chance=0.80,
        default_health=4,
        wood_drop=3,
    ),
    "peach": TreeVisualProfile(
        "peach", "peach", "all_trees_sprites", (-0.8, -0.9), 25,
        ((-12, -124), (4, -106), (18, -138)),
        fruit_chance=0.80,
        default_health=4,
        wood_drop=3,
    ),
    "cherry": TreeVisualProfile(
        "cherry", "cherry", "all_trees_sprites", (-0.8, -0.9), 25,
        ((-12, -124), (4, -106), (18, -138)),
        fruit_chance=0.80,
        default_health=4,
        wood_drop=3,
    ),
}


# --------------------------------------------------
# Global caches
# --------------------------------------------------

_CACHED_ASSETS: Optional[LoadAssets] = None
_FRAME_CACHE: dict[tuple[str, tuple[int, int]], list[pygame.Surface]] = {}
_IMAGE_CACHE: dict[tuple[str, str, str], pygame.Surface] = {}
_SOUND_CACHE: dict[str, pygame.mixer.Sound] = {}


def get_assets() -> LoadAssets:
    global _CACHED_ASSETS
    if _CACHED_ASSETS is None:
        _CACHED_ASSETS = LoadAssets()
    return _CACHED_ASSETS


def get_cached_image(folder: str, filename: str, cache_group: str = "default") -> pygame.Surface:
    key = (cache_group, folder, filename)
    image = _IMAGE_CACHE.get(key)
    if image is None:
        image = import_file(folder, filename).convert_alpha()
        _IMAGE_CACHE[key] = image
    return image


def get_cached_sound(path: str) -> pygame.mixer.Sound:
    sound = _SOUND_CACHE.get(path)
    if sound is None:
        sound = pygame.mixer.Sound(path)
        _SOUND_CACHE[path] = sound
    return sound


class FruitCanopyParticle(WorldObject):
    def __init__(
        self,
        tree: "Tree",
        surf: pygame.Surface,
        offset: tuple[int, int],
        *,
        sway_speed: float = 1.8,
        sway_amount: float = 2.0
    ):
        self.tree = tree
        self.base_offset = pygame.math.Vector2(offset)
        self.local_offset = pygame.math.Vector2(offset)
        self.sway_speed = float(sway_speed)
        self.sway_amount = float(sway_amount)
        self.elapsed = 0.0
        self.visible = True

        super().__init__(self._world_pos(), surf, anchor="center")
        self.collision_box = self.rect.copy().inflate(-self.rect.width * 0.6, -self.rect.height * 0.6)

    def _world_pos(self) -> tuple[int, int]:
        return (
            int(self.tree.rect.midbottom[0] + self.local_offset.x),
            int(self.tree.rect.midbottom[1] + self.local_offset.y),
        )

    @property
    def sort_y(self):
        return self.tree.sort_y + 1

    def update(self, dt):
        self.elapsed += dt
        self.local_offset.x = self.base_offset.x + (self.sway_amount * sin(self.elapsed * self.sway_speed))
        self.rect = self._make_rect(self._world_pos())
        self.tick_opacity(dt)


class FruitPickupParticle(WorldObject):
    def __init__(
        self,
        pos,
        surf,
        target_position,
        player=None,
        on_collect=None,
        duration=2500,
        launch_time=0.55,
        g=1400.0,
        speed_to_player=700.0,
        arrive_radius=10.0,
        chase_player=True
    ):
        super().__init__(pos, surf, anchor="center")
        self.player = player
        self.pos = pygame.math.Vector2(pos)
        self.t0 = pygame.math.Vector2(target_position)
        self.t1 = pygame.math.Vector2(player.rect.center) if player is not None else pygame.math.Vector2(target_position)
        self.phase = 0
        self.g = float(g)
        self.speed_to_player = float(speed_to_player)
        self.arrive_radius = float(arrive_radius)
        self.chase_player = bool(chase_player)
        self.on_collect = on_collect
        self.start_time = pygame.time.get_ticks()
        self.duration = duration
        self.alive = True

        t = max(0.1, float(launch_time))
        d = self.t0 - self.pos
        self.vel = pygame.math.Vector2(d.x / t, (d.y - 0.5 * self.g * t * t) / t)
        self.rect.center = (round(self.pos.x), round(self.pos.y))

    def collect(self):
        if self.on_collect is not None:
            self.on_collect()
        self.alive = False

    @staticmethod
    def move_towards(pos, target, speed, dt):
        p = pygame.math.Vector2(pos)
        t = pygame.math.Vector2(target)
        d = t - p
        dist = d.length()
        if dist == 0:
            return p
        step = speed * dt
        if dist <= step:
            return t
        return p + d * (step / dist)

    def update(self, dt):
        if not self.alive:
            return

        if self.player is not None:
            player_hitbox = getattr(self.player, "collision_box", self.player.rect)
            if player_hitbox.colliderect(self.rect):
                self.collect()
                return

        if pygame.time.get_ticks() - self.start_time > self.duration:
            self.alive = False
            return

        if self.phase == 0:
            self.vel.y += self.g * dt
            self.pos += self.vel * dt
            if self.pos.distance_to(self.t0) <= self.arrive_radius:
                self.phase = 1
        else:
            if self.chase_player and self.player is not None:
                self.t1 = pygame.math.Vector2(self.player.rect.center)
            self.pos = self.move_towards(self.pos, self.t1, self.speed_to_player, dt)
            if self.pos.distance_to(self.t1) <= self.arrive_radius:
                self.collect()
                return

        self.rect.center = (round(self.pos.x), round(self.pos.y))

        if self.player is not None:
            player_hitbox = getattr(self.player, "collision_box", self.player.rect)
            if player_hitbox.colliderect(self.rect) or self.pos.distance_to(self.player.rect.center) <= (self.arrive_radius * 2):
                self.collect()
                return

        self.tick_opacity(dt)


class Tree(AnimatedWorldObject):
    FRUITS = [
        "Golden Apple", "Green Apple", "Red Apple", "Orange", "Green Fig",
        "Purple Fig", "Black Grapes", "Green Grapes", "Purple Grapes", "Yellow Grapes",
    ]
    TROPICAL_FRUITS = ["Cocoa Beans", "Avocado", "Mango", "Melon", "Pear"]

    def __init__(
        self,
        pos,
        groups,
        base_name: str,
        tile_pos,
        path_find,
        c_s,
        show: bool = True,
        *,
        tree_data: Optional[dict[str, Any]] = None,
        scale=(2, 2),
        animation_speed: float = 6.0
    ):
        self.assets = get_assets()
        self.sprite_groups = groups
        self.path_find = path_find
        self.c_s = c_s
        self.show = show
        self.name = "tree"
        self.pos = pos
        self.tree_scale = (float(scale[0]), float(scale[1]))
        self.tree_tile_pos = tile_pos
        self.tree_data = tree_data or {}
        self.fruit_rng = Random(self._stable_fruit_seed())

        species = self.tree_data.get("species", base_name)
        profile = TREE_VISUALS.get(species, TREE_VISUALS.get(base_name, TREE_VISUALS["oak"]))
        self.tree_species = species
        self.tree_name = profile.base_name
        self.tree_type = f"{self.tree_name}_tree"
        self.max_health = min(6, int(profile.default_health))
        self.health = max(0, min(self.max_health, int(self.tree_data.get("health", self.max_health))))
        self.tree_data["health"] = self.health
        self.wood_drop = max(0, int(self.tree_data.get("wood_drop", profile.wood_drop)))
        self.alive = self.health > 0
        self.death_handled = False
        self.drops_collected = False

        frames = self._build_frames(profile, scale)
        super().__init__(pos, frames, anchor="midbottom", animation_speed=animation_speed, loop=True)

        self._setup_collision(profile)
        self._setup_drops(profile)
        self.child_particles: list[FruitCanopyParticle] = []
        self.active_pickup_particles: list[FruitPickupParticle] = []
        if self.alive:
            self._spawn_canopy_fruits(profile)
        else:
            self._become_stump()
            self.drops_collected = True
        self.axe_sound = get_cached_sound(rp("audio", "axe.mp3"))

    def _stable_fruit_seed(self) -> int:
        parts = (
            self.tree_data.get("chunk"),
            self.tree_data.get("world_tile"),
            self.tree_data.get("species"),
        )
        digest = hashlib.sha256("|".join(map(str, parts)).encode("utf-8")).hexdigest()
        return int(digest[:16], 16)

    @classmethod
    def from_tree_record(cls, tree_record, groups, path_find, c_s, show=True):
        return cls(
            pos=tuple(tree_record["world_pos"]),
            groups=groups,
            base_name=tree_record["species"],
            tile_pos=tuple(tree_record["world_tile"]),
            path_find=path_find,
            c_s=c_s,
            show=show,
            tree_data=tree_record,
        )

    def _build_frames(self, profile: TreeVisualProfile, scale) -> list[pygame.Surface]:
        scale_key = (int(scale[0]), int(scale[1]))
        cache_key = (profile.species, scale_key)

        cached = _FRAME_CACHE.get(cache_key)
        if cached is not None:
            return cached

        sprite_sheet = getattr(self.assets, profile.sprite_sheet_name)
        frame_key = self.tree_name if self.tree_name in self.assets.all_trees else next(iter(self.assets.all_trees.keys()))
        frame_data = self.assets.all_trees[frame_key]

        frames: list[pygame.Surface] = []
        for frame in frame_data:
            surf = sprite_sheet.get_sprite(*frame)
            scaled = pygame.transform.scale(
                surf,
                (int(frame[2] * scale[0]), int(frame[3] * scale[1]))
            ).convert_alpha()
            frames.append(scaled)

        _FRAME_CACHE[cache_key] = frames
        return frames

    def _build_stump_frame(self) -> pygame.Surface:
        scale_key = (
            max(1, round(self.tree_scale[0])),
            max(1, round(self.tree_scale[1])),
        )
        cache_key = ("stump", scale_key)

        cached = _FRAME_CACHE.get(cache_key)
        if cached is not None:
            return cached[0]

        frame_key = "stump" if "stump" in self.assets.all_trees else self.tree_name
        frame = self.assets.all_trees[frame_key][0]
        surf = self.assets.all_trees_sprites.get_sprite(*frame)
        stump = pygame.transform.scale(
            surf,
            (int(frame[2] * scale_key[0]), int(frame[3] * scale_key[1]))
        ).convert_alpha()

        _FRAME_CACHE[cache_key] = [stump]
        return stump

    def _become_stump(self):
        if self.death_handled:
            return

        self.death_handled = True
        stump_frame = self._build_stump_frame()
        self.frames = [stump_frame]
        self.index = 0
        self.image_base = stump_frame
        self._refresh_image()
        self.mask = pygame.mask.from_surface(self.image_base)
        self.collision_box = pygame.Rect(0, 0, 0, 0)
        for particle in self.child_particles:
            particle.visible = False
        self.child_particles.clear()

    def _setup_collision(self, profile: TreeVisualProfile):
        inflate_x = self.rect.width * profile.collision_inflate[0]
        inflate_y = self.rect.height * profile.collision_inflate[1]
        self.collision_box = self.rect.copy().inflate(inflate_x, inflate_y)
        self.collision_box.centery += profile.collision_offset_y

    def _setup_drops(self, profile: TreeVisualProfile):
        self.wood_icon = get_cached_image("graphics/stumps", "wood.png", "icon")

        self.fruit_name, self.fruit_count = self._choose_fruit(profile)

        if self.fruit_name:
            self.fruit_surf = get_cached_image("graphics/fruiticons", f"{self.fruit_name}.png", "fruit")
        else:
            self.fruit_surf = None

    def _choose_fruit(self, profile: TreeVisualProfile) -> tuple[str, int]:
        if not profile.canopy_offsets or self.fruit_rng.random() > profile.fruit_chance:
            return ("", 0)

        if profile.species == "palm":
            return ("Coconut", self.fruit_rng.randint(1, 3))
        if profile.species in {"oak", "birch", "fruit", "tropicfruit", "apple", "peach", "cherry"}:
            return (
                self.FRUITS[self.fruit_rng.randint(0, len(self.FRUITS) - 1)],
                self.fruit_rng.randint(2, 4),
            )
        if profile.species in {"pine", "mangrove", "tropical"}:
            return (
                self.TROPICAL_FRUITS[self.fruit_rng.randint(0, len(self.TROPICAL_FRUITS) - 1)],
                self.fruit_rng.randint(1, 3),
            )
        return ("", 0)

    def _spawn_canopy_fruits(self, profile: TreeVisualProfile):
        if self.fruit_surf is None or self.fruit_count <= 0:
            return
        for offset in profile.canopy_offsets[: self.fruit_count]:
            self.child_particles.append(FruitCanopyParticle(self, self.fruit_surf, offset))

    def _add_inventory_items(self, player_inventory, name, surf, amount):
        if player_inventory is None or amount <= 0:
            return
        for _ in range(amount):
            try:
                player_inventory.add_item_to_slot(
                    Item(
                        name,
                        surf,
                        True,
                        player_inventory.craft_system.return_craft_product(name)
                    )
                )
            except (IndexError, AttributeError):
                return

    def collect_drops(self, player=None, player_inventory=None):
        if self.drops_collected:
            return
        self.drops_collected = True
        self._add_inventory_items(player_inventory, "wood", self.wood_icon, self.wood_drop)
        if self.fruit_count <= 0:
            for fruit_particle in self.child_particles:
                fruit_particle.visible = False

    def _spawn_fruit_pickups(self, player, player_inventory, amount):
        for _ in range(amount):
            if player is not None:
                player_target = pygame.math.Vector2(player.rect.center)
                tree_origin = pygame.math.Vector2(self.rect.center)
                direction = player_target - tree_origin
                if direction.length_squared() == 0:
                    direction = pygame.math.Vector2(0, 1)
                else:
                    direction = direction.normalize()

                travel_distance = min(110.0, max(48.0, tree_origin.distance_to(player_target) * 0.35))
                target = direction * travel_distance
                target_position = (
                    self.rect.centerx + target.x,
                    self.rect.centery + target.y,
                )
            else:
                target_position = self.rect.center
            on_collect = None
            if player_inventory is not None:
                on_collect = lambda inv=player_inventory, name=self.fruit_name, surf=self.fruit_surf: self._add_inventory_items(inv, name, surf, 1)

            self.active_pickup_particles.append(
                FruitPickupParticle(
                    self.rect.center,
                    self.fruit_surf,
                    target_position,
                    player=player,
                    on_collect=on_collect,
                    chase_player=True,
                )
            )

    def drop_single_fruit(self, player=None, player_inventory=None):
        if self.fruit_count <= 0 or self.fruit_name is None or self.fruit_surf is None:
            return

        self._spawn_fruit_pickups(player, player_inventory, 1)
        self.fruit_count -= 1
        if self.child_particles:
            self.child_particles.pop().visible = False

    def damage(self, player=None, player_inventory=None):
        if not self.alive:
            return
        self.axe_sound.play()
        self.health = max(0, self.health - 1)
        self.tree_data["health"] = self.health
        self.drop_single_fruit(player, player_inventory)

        if self.health <= 0:
            self.alive = False
            for particle in self.child_particles:
                particle.visible = False
            self.collect_drops(player, player_inventory)
            self._become_stump()

    def check_death(self):
        if self.health <= 0 and not self.death_handled:
            self._become_stump()

    def tree_visibility(self, path_find, chunk_size, near_chunks):
        if near_chunks is None or path_find is None:
            self.show = True
            return
        npc_chunk_key = path_find.get_chunk_key_from_world(*self.tree_tile_pos, chunk_size)
        self.show = npc_chunk_key in near_chunks

    def update(self, dt, player_group=None, dimmed_alpha=120, near_chunks=None, time=None):
        self.tree_visibility(self.path_find, self.c_s, near_chunks)
        if not self.show:
            return

        if self.alive:
            self.animate(dt)
        self.tick_opacity(dt)
        self.check_death()

        for fruit_particle in self.child_particles:
            if fruit_particle.visible:
                fruit_particle.set_target_opacity(self.target_opacity)
                fruit_particle.update(dt)

        alive_particles = []
        for particle in self.active_pickup_particles:
            particle.update(dt)
            if particle.alive:
                alive_particles.append(particle)
        self.active_pickup_particles = alive_particles

    def iter_attached_objects(self):
        for fruit_particle in self.child_particles:
            if fruit_particle.visible:
                yield fruit_particle
        for particle in self.active_pickup_particles:
            if particle.alive:
                yield particle

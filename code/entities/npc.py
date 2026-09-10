"""Wandering NPC behavior and per-chunk NPC lifecycle management."""

from __future__ import annotations

import random

import pygame

from pathfinding import ChunkPathfinder
from sprites import AnimatedWorldObject


_NPC_FRAME_CACHE = {}
_NPC_MASK_CACHE = {}
FEATURED_NPC_ROLES = (
    "bard",
    "dancer",
    "merchant",
    "king",
    "queen",
    "chef",
    "nun",
)


def get_frame_mask(frame):
    key = id(frame)
    mask = _NPC_MASK_CACHE.get(key)
    if mask is None:
        mask = pygame.mask.from_surface(frame)
        _NPC_MASK_CACHE[key] = mask
    return mask


class WanderingNPC(AnimatedWorldObject):
    def __init__(
        self,
        pos,
        assets,
        pathfinder,
        npc_id=None,
        speed=72,
        visual_scale=2,
        rng=None,
    ):
        self.assets = assets
        self.pathfinder = pathfinder
        available_ids = assets.get_npc_ids()
        self.npc_id = npc_id or (available_ids[0] if available_ids else None)
        self.role = (
            assets.get_npc_profile(self.npc_id)["role"]
            if self.npc_id is not None
            else "villager"
        )
        self.rng = rng or random.Random()
        self.facing = "down"
        self.special_animation = None
        self.special_timer = 0.0
        self.status = self.get_resting_animation()
        self.last_status = self.status
        self.speed = speed
        self.visual_scale = visual_scale
        self.direction = pygame.Vector2()
        self.pos = pygame.Vector2(pos)
        self.path = []
        self.target_tile = None
        self.route_stall_timer = 0.0
        self.wait_timer = self.rng.uniform(0.6, 1.8)
        self.max_health = 3
        self.health = self.max_health
        self.knockback_velocity = pygame.Vector2()
        self.knockback_timer = 0.0
        self.knockback_duration = 0.18
        self.half_health_effect_shown = False
        self.death_effect_shown = False
        self.is_enemy = False
        self.hostile = False
        self.faction = "civilian"

        shared_frames = self.get_scaled_frames(self.status)
        super().__init__(
            pos=pos,
            frames=shared_frames,
            anchor="midbottom",
            animation_speed=6,
            loop=True,
        )
        # AnimatedWorldObject defensively converts every supplied frame. NPC
        # art is immutable, so retain the process-wide scaled frames instead of
        # keeping one converted copy of every animation frame per NPC.
        self.frames = shared_frames
        self.image_base = shared_frames[0]
        self.image = shared_frames[0]
        self.rect = self.image.get_rect(midbottom=pos)
        self.mask = get_frame_mask(self.image_base)
        self.animation_speed = self.get_animation_speed(self.status)
        self.name = "npc"
        self.collision_box = self.rect.copy().inflate(-self.rect.width * 0.5, -self.rect.height * 0.35)
        self.begin_rest()

    @property
    def center(self):
        return self.rect.center

    @property
    def sort_y(self):
        return self.rect.bottom

    @property
    def is_alive(self):
        return self.health > 0

    def take_damage(self, amount=1, *, effects=None, source=None):
        if amount <= 0 or not self.is_alive:
            return False
        self.health = max(0, self.health - int(amount))
        self.apply_knockback(source)
        if effects is not None:
            effects.spawn("blood", self.rect.center)
        if (
            self.health > 0
            and self.health <= self.max_health / 2
            and not self.half_health_effect_shown
        ):
            self.half_health_effect_shown = True
            if effects is not None:
                effects.spawn(
                    "confusion",
                    self.rect.center,
                    follow=self,
                    offset=(0, -self.rect.height * 0.35),
                )
        if self.health <= 0:
            self.direction.update(0, 0)
            self.target_tile = None
            self.path.clear()
            if not self.death_effect_shown and effects is not None:
                effects.spawn("death", self.rect.center)
            self.death_effect_shown = True
        return True

    def apply_knockback(self, source, strength=235, duration=None):
        if source is None:
            return False
        source_center = None
        feet_box = getattr(source, "feet_collision_box", None)
        if feet_box is not None:
            source_center = feet_box.center
        elif hasattr(source, "center"):
            source_center = source.center
        elif hasattr(source, "rect"):
            source_center = source.rect.center
        if source_center is None:
            return False

        delta = pygame.Vector2(self.rect.center) - pygame.Vector2(source_center)
        if delta.length_squared() == 0:
            delta = -pygame.Vector2(getattr(source, "direction", (0, 1)))
        if delta.length_squared() == 0:
            delta.update(0, 1)
        self.knockback_velocity = delta.normalize() * max(0.0, float(strength))
        self.knockback_timer = max(
            0.01,
            float(self.knockback_duration if duration is None else duration),
        )
        return True

    def advance_knockback(self, dt):
        if self.knockback_timer <= 0:
            return False
        active_dt = min(max(0.0, float(dt)), self.knockback_timer)
        self.pos += self.knockback_velocity * active_dt
        self.rect.midbottom = (round(self.pos.x), round(self.pos.y))
        self.collision_box.center = self.rect.center
        self.knockback_timer = max(0.0, self.knockback_timer - dt)
        self.knockback_velocity *= max(0.0, 1.0 - dt * 7.0)
        if self.knockback_timer <= 0:
            self.knockback_velocity.update(0, 0)
        return True

    def get_scaled_frames(self, status):
        cache_key = (
            id(self.assets),
            self.npc_id,
            status,
            float(self.visual_scale),
        )
        cached = _NPC_FRAME_CACHE.get(cache_key)
        if cached is not None:
            return cached

        if self.npc_id is None:
            frames = self.assets.get_character_frames(status)
        else:
            frames = self.assets.get_npc_frames(self.npc_id, status)
        if self.visual_scale == 1:
            scaled_frames = tuple(frames)
        else:
            scaled_frames = tuple(
                pygame.transform.scale(
                    frame,
                    (
                        int(frame.get_width() * self.visual_scale),
                        int(frame.get_height() * self.visual_scale),
                    ),
                )
                for frame in frames
            )
        _NPC_FRAME_CACHE[cache_key] = scaled_frames
        return scaled_frames

    def get_animation_speed(self, status):
        if self.npc_id is None:
            return 6
        return self.assets.get_npc_animation_speed(status)

    def get_resting_animation(self):
        if self.npc_id is None:
            return f"{self.facing}_idle"
        return self.assets.get_npc_idle_animation(self.npc_id, self.facing)

    def refresh_animation_set(self):
        if self.status == self.last_status:
            return
        self.frames = self.get_scaled_frames(self.status)
        self.index = 0
        self.animation_finished = False
        self.image_base = self.frames[0]
        anchor = self.rect.midbottom
        self.image = self.image_base
        self.rect = self.image.get_rect(midbottom=anchor)
        self.mask = get_frame_mask(self.image_base)
        self.animation_speed = self.get_animation_speed(self.status)
        self.last_status = self.status

    def animate(self, dt):
        if self.animation_finished and not self.loop:
            return
        self.index += self.animation_speed * dt
        if self.loop:
            self.index %= len(self.frames)
        elif self.index >= len(self.frames):
            self.index = len(self.frames) - 1
            self.animation_finished = True
        frame = self.frames[int(self.index)]
        if frame is self.image_base:
            return
        anchor = self.rect.midbottom
        self.image_base = frame
        self.image = frame
        self.rect = frame.get_rect(midbottom=anchor)
        self.mask = get_frame_mask(frame)

    def update_status(self):
        if self.direction.length_squared() > 0:
            if abs(self.direction.x) > abs(self.direction.y):
                self.facing = "right" if self.direction.x > 0 else "left"
            else:
                self.facing = "down" if self.direction.y > 0 else "up"
            next_status = self.facing
        elif self.special_timer > 0 and self.special_animation is not None:
            next_status = self.special_animation
        else:
            next_status = self.get_resting_animation()

        if next_status != self.status:
            self.status = next_status
            self.refresh_animation_set()

    def begin_rest(self):
        self.target_tile = None
        self.path.clear()
        self.route_stall_timer = 0.0
        self.direction.update(0, 0)
        self.special_animation = None
        self.special_timer = 0.0
        self.wait_timer = self.rng.uniform(0.8, 2.4)

        if self.npc_id is None:
            return
        special_states = self.assets.get_npc_special_states(self.npc_id)
        if special_states and self.rng.random() < 0.75:
            self.special_animation, self.facing = self.rng.choice(special_states)
            self.special_timer = self.rng.uniform(2.0, 4.8)

    def choose_wander_path(self):
        self.special_animation = None
        self.special_timer = 0.0
        start = self.pathfinder.world_to_tile(self.rect.midbottom)
        goal = self.find_wander_goal(start)
        if goal is None:
            self.begin_rest()
            return

        path = self.pathfinder.find_full_path(start, goal)
        if len(path) <= 1:
            self.begin_rest()
            return

        self.path = path[1:]
        self.set_next_target()

    def find_wander_goal(self, start):
        for _ in range(24):
            offset_x = self.rng.randint(-18, 18)
            remaining = 18 - abs(offset_x)
            offset_y = self.rng.randint(-remaining, remaining)
            goal = (start[0] + offset_x, start[1] + offset_y)
            if goal != start and self.pathfinder.is_walkable(goal):
                return goal
        return None

    def set_next_target(self):
        if not self.path:
            self.begin_rest()
            return
        tile = self.path.pop(0)
        self.target_tile = pygame.Vector2(self.pathfinder.tile_to_world_center(tile))

    def move(self, dt):
        if self.target_tile is None:
            self.direction.update(0, 0)
            return

        delta = self.target_tile - self.pos
        if delta.length() <= max(2, self.speed * dt):
            self.pos.update(self.target_tile)
            self.rect.midbottom = (round(self.pos.x), round(self.pos.y))
            self.collision_box.center = self.rect.center
            self.set_next_target()
            return

        self.direction = delta.normalize()
        self.pos += self.direction * self.speed * dt
        self.rect.midbottom = (round(self.pos.x), round(self.pos.y))
        self.collision_box.center = self.rect.center

    def update(self, dt):
        if not self.is_alive:
            self.direction.update(0, 0)
            self.tick_opacity(dt)
            return
        if self.target_tile is None:
            if self.special_timer > 0:
                self.special_timer = max(0.0, self.special_timer - dt)
            else:
                self.wait_timer -= dt
                if self.wait_timer <= 0:
                    self.choose_wander_path()

        previous_pos = pygame.Vector2(self.pos)
        self.move(dt)
        if self.target_tile is None:
            self.route_stall_timer = 0.0
        elif self.pos.distance_squared_to(previous_pos) < 0.0001:
            self.route_stall_timer += dt
            if self.route_stall_timer >= 2.0:
                self.begin_rest()
        else:
            self.route_stall_timer = 0.0
        self.update_status()
        self.animate(dt)
        self.tick_opacity(dt)


class GuardNPC(WanderingNPC):
    """Sword-and-shield guard composed from the dedicated NPC guard sheets."""

    AGGRO_RADIUS = 300
    ATTACK_RANGE = 76

    def __init__(self, pos, assets, pathfinder, visual_scale=2, rng=None):
        self.combat_action = None
        self.combat_action_timer = 0.0
        self.attack_cooldown = 0.0
        self.slash_index = 0
        super().__init__(
            pos,
            assets,
            pathfinder,
            npc_id=None,
            speed=78,
            visual_scale=visual_scale,
            rng=rng,
        )
        self.role = "guard"
        self.name = "guard"
        self.faction = "guard"
        self.max_health = 8
        self.health = self.max_health
        self.hostile = False
        self.is_enemy = False

    def get_scaled_frames(self, status):
        cache_key = (
            id(self.assets),
            "guard",
            status,
            float(self.visual_scale),
        )
        cached = _NPC_FRAME_CACHE.get(cache_key)
        if cached is not None:
            return cached
        frames = self.assets.get_guard_frames(status)
        if self.visual_scale == 1:
            scaled_frames = tuple(frames)
        else:
            scaled_frames = tuple(
                pygame.transform.scale(
                    frame,
                    (
                        int(frame.get_width() * self.visual_scale),
                        int(frame.get_height() * self.visual_scale),
                    ),
                )
                for frame in frames
            )
        _NPC_FRAME_CACHE[cache_key] = scaled_frames
        return scaled_frames

    def get_resting_animation(self):
        return f"{self.facing}_weapon_idle"

    def get_animation_speed(self, status):
        return 8 if "slash" in status or "bash" in status else 6

    def take_damage(self, amount=1, *, effects=None, source=None):
        if source is not None:
            self.hostile = True
            self.is_enemy = True
            self.faction = "enemy"
        damaged = super().take_damage(amount, effects=effects, source=source)
        if damaged and self.is_alive:
            self.combat_action = "hurt_sword"
            self.combat_action_timer = 0.18
        return damaged

    def _face_delta(self, delta):
        if abs(delta.x) > abs(delta.y):
            self.facing = "right" if delta.x > 0 else "left"
        else:
            self.facing = "down" if delta.y > 0 else "up"

    def update(self, dt, player=None, effects=None):
        self.attack_cooldown = max(0.0, self.attack_cooldown - dt)
        self.combat_action_timer = max(0.0, self.combat_action_timer - dt)

        if not self.is_alive:
            next_status = f"{self.facing}_dead_sword"
            if next_status != self.status:
                self.status = next_status
                self.loop = False
                self.refresh_animation_set()
            self.advance_knockback(dt)
            self.animate(dt)
            self.tick_opacity(dt)
            return

        self.direction.update(0, 0)
        next_status = self.get_resting_animation()
        knocked_back = self.knockback_timer > 0
        if knocked_back:
            self.advance_knockback(dt)
        elif self.hostile and player is not None and player.is_alive:
            delta = pygame.Vector2(player.feet_collision_box.center) - self.pos
            distance = delta.length()
            if distance > 0:
                self._face_delta(delta)
            if distance <= self.AGGRO_RADIUS:
                if distance > self.ATTACK_RANGE:
                    self.direction = delta.normalize()
                    self.pos += self.direction * self.speed * dt
                    self.rect.midbottom = (round(self.pos.x), round(self.pos.y))
                    self.collision_box.center = self.rect.center
                    next_status = f"{self.facing}_weapon_stealth_move"
                elif self.combat_action_timer <= 0 and self.attack_cooldown <= 0:
                    self.slash_index = 1 - self.slash_index
                    self.combat_action = f"sword_slash{self.slash_index + 1}"
                    self.combat_action_timer = 0.48
                    self.attack_cooldown = 1.15
                    player.take_damage(1, effects=effects, source=self)

        if self.combat_action_timer > 0 and self.combat_action is not None:
            next_status = f"{self.facing}_{self.combat_action}"
        else:
            self.combat_action = None

        if next_status != self.status:
            self.status = next_status
            self.refresh_animation_set()
        self.animate(dt)
        self.tick_opacity(dt)


class NPCManager:
    def __init__(self, world, assets, count=4):
        self.world = world
        self.assets = assets
        self.pathfinder = ChunkPathfinder(world)
        self.npcs = []
        self.market_stall_ids = set()
        self.rng = random.Random(f"{world.seed}:npc-population")
        self.spawn_initial(count)

    def choose_npc_ids(self, count):
        selected = []
        for role in FEATURED_NPC_ROLES:
            role_ids = self.assets.get_npc_ids(role)
            if role_ids:
                selected.append(self.rng.choice(role_ids))

        remaining_roles = [
            role
            for role in self.assets.get_npc_roles()
            if role not in FEATURED_NPC_ROLES
        ]
        self.rng.shuffle(remaining_roles)
        for role in remaining_roles:
            if len(selected) >= count:
                break
            role_ids = self.assets.get_npc_ids(role)
            if role_ids:
                selected.append(self.rng.choice(role_ids))

        remaining_ids = [
            npc_id
            for npc_id in self.assets.get_npc_ids()
            if npc_id not in selected
        ]
        self.rng.shuffle(remaining_ids)
        selected.extend(remaining_ids[:max(0, count - len(selected))])
        return selected[:count]

    def spawn_initial(self, count):
        from entities.market import ensure_chunk_market_stalls
        from entities.scheduled_npc import MerchantNPC, ScheduledNPC

        spawn = self.world.get_spawn_position()
        spawn_tile = self.pathfinder.world_to_tile(spawn)
        candidates = []

        market_stalls = []
        for chunk in self.world.loaded_chunks.values():
            market_stalls.extend(ensure_chunk_market_stalls(chunk))

        merchant_roles = ("merchant", "woman", "man", "old_woman", "old_man")
        merchant_ids = []
        for role in merchant_roles:
            merchant_ids.extend(self.assets.get_npc_ids(role))
        if not merchant_ids:
            merchant_ids = self.assets.get_npc_ids()
        for index, stall in enumerate(market_stalls):
            if not merchant_ids:
                break
            npc_id = merchant_ids[index % len(merchant_ids)]
            self.npcs.append(
                MerchantNPC(
                    stall.record["merchant_world_pos"],
                    self.assets,
                    self.pathfinder,
                    stall=stall,
                    npc_id=npc_id,
                    rng=random.Random(f"{self.world.seed}:merchant:{stall.stall_id}"),
                )
            )
            self.market_stall_ids.add(stall.stall_id)

        for chunk in self.world.loaded_chunks.values():
            for local_y in range(chunk.chunk_size[1]):
                for local_x in range(chunk.chunk_size[0]):
                    world_tile = chunk.get_world_tile(local_x, local_y)
                    if self.pathfinder.heuristic(spawn_tile, world_tile) > 16:
                        continue
                    if self.pathfinder.is_walkable(world_tile):
                        candidates.append(world_tile)

        if not candidates:
            for chunk in self.world.loaded_chunks.values():
                for local_y in range(chunk.chunk_size[1]):
                    for local_x in range(chunk.chunk_size[0]):
                        world_tile = chunk.get_world_tile(local_x, local_y)
                        if self.pathfinder.is_walkable(world_tile):
                            candidates.append(world_tile)

        guard_candidates = [
            tile
            for tile in candidates
            if 3 <= self.pathfinder.heuristic(spawn_tile, tile) <= 8
        ]
        if guard_candidates:
            guard_tile = min(
                guard_candidates,
                key=lambda tile: self.pathfinder.heuristic(spawn_tile, tile),
            )
            candidates.remove(guard_tile)
            self.npcs.append(
                GuardNPC(
                    self.pathfinder.tile_to_world_center(guard_tile),
                    self.assets,
                    self.pathfinder,
                    rng=random.Random(f"{self.world.seed}:npc:guard"),
                )
            )

        self.rng.shuffle(candidates)
        npc_ids = self.choose_npc_ids(max(0, count - len(self.npcs)))
        social_points = [
            pygame.Vector2(stall.record["visitor_world_pos"])
            for stall in market_stalls
        ]
        for index, (tile, npc_id) in enumerate(zip(candidates, npc_ids)):
            home_pos = self.pathfinder.tile_to_world_center(tile)
            work_tile = None
            for _ in range(20):
                candidate = (
                    tile[0] + self.rng.randint(-10, 10),
                    tile[1] + self.rng.randint(-10, 10),
                )
                if self.pathfinder.is_walkable(candidate):
                    work_tile = candidate
                    break
            work_pos = self.pathfinder.tile_to_world_center(work_tile or tile)
            social_pos = min(
                social_points or [pygame.Vector2(work_pos)],
                key=lambda point: point.distance_squared_to(home_pos),
            )
            self.npcs.append(
                ScheduledNPC(
                    home_pos,
                    self.assets,
                    self.pathfinder,
                    npc_id=npc_id,
                    home_pos=home_pos,
                    work_pos=work_pos,
                    social_pos=social_pos,
                    rng=random.Random(
                        f"{self.world.seed}:npc:{index}:{npc_id}"
                    ),
                )
            )

    def update(self, dt, player=None, effects=None, game_time=None):
        from entities.scheduled_npc import ScheduledNPC

        self.spawn_new_market_merchants()
        for npc in self.npcs:
            if isinstance(npc, GuardNPC):
                npc.update(dt, player=player, effects=effects)
            elif isinstance(npc, ScheduledNPC):
                npc.update(dt, game_time=game_time)
            else:
                npc.update(dt)

    def spawn_new_market_merchants(self):
        """Staff markets that streamed in after the initial NPC population."""
        from entities.market import ensure_chunk_market_stalls
        from entities.scheduled_npc import MerchantNPC, ScheduledNPC

        merchant_ids = []
        for role in ("merchant", "woman", "man", "old_woman", "old_man"):
            merchant_ids.extend(self.assets.get_npc_ids(role))
        if not merchant_ids:
            merchant_ids = self.assets.get_npc_ids()
        if not merchant_ids:
            return 0

        spawned = []
        for chunk in self.world.loaded_chunks.values():
            for stall in ensure_chunk_market_stalls(chunk):
                if stall.stall_id in self.market_stall_ids:
                    continue
                npc_id = merchant_ids[len(self.market_stall_ids) % len(merchant_ids)]
                merchant = MerchantNPC(
                    stall.record["merchant_world_pos"],
                    self.assets,
                    self.pathfinder,
                    stall=stall,
                    npc_id=npc_id,
                    rng=random.Random(f"{self.world.seed}:merchant:{stall.stall_id}"),
                )
                self.npcs.append(merchant)
                self.market_stall_ids.add(stall.stall_id)
                spawned.append(merchant)

        if spawned:
            social_points = [pygame.Vector2(npc.stall.record["visitor_world_pos"]) for npc in self.npcs if isinstance(npc, MerchantNPC)]
            for npc in self.npcs:
                if isinstance(npc, ScheduledNPC) and not isinstance(npc, MerchantNPC):
                    npc.social_pos = min(
                        social_points,
                        key=lambda point: point.distance_squared_to(npc.home_pos),
                    )
        return len(spawned)

    def find_talk_target(self, player, max_distance=112):
        from entities.scheduled_npc import MerchantNPC

        player_center = pygame.Vector2(player.feet_collision_box.center)
        nearby = [
            npc
            for npc in self.npcs
            if isinstance(npc, MerchantNPC)
            and npc.is_available
            and player_center.distance_to(npc.rect.midbottom) <= max_distance
        ]
        if not nearby:
            return None
        return min(
            nearby,
            key=lambda npc: player_center.distance_squared_to(npc.rect.midbottom),
        )

    def visible_npcs(self, visible_chunks):
        visible_chunk_keys = {coord for coord, _, _, _ in visible_chunks}
        for npc in self.npcs:
            if self.world.world_to_chunk(npc.rect.center) in visible_chunk_keys:
                yield npc

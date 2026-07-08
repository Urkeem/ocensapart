"""Player movement, tools, seed planting, pickups, and collision behavior."""

import pygame
from ui.inventory import Inventory
from inventory_item import Item
from sprites import AnimatedWorldObject
from swimming import SwimVisual
from utils import rp


class Player(AnimatedWorldObject):
    def __init__(
        self,
        pos,
        assets,
        initial_status="down_idle",
        speed=100,
        size=None,
        visual_scale=1,
        soil_layer=None,
        customization=None,
    ):
        self.assets = assets
        self.customization = self.assets.normalize_character_customization(customization)
        self.status = initial_status
        self.last_status = self.status
        self.direction = pygame.Vector2()
        self.pos = pygame.Vector2(pos)
        self.speed = speed
        self.visual_scale = visual_scale
        self.soil_layer = soil_layer
        self.tools = ["hoe", "axe", "water", "fishing rod"]
        self.tool_index = 0
        self.selected_tool = self.tools[self.tool_index]
        self.seeds = ["corn", "tomato"]
        self.seed_index = 0
        self.selected_seed = self.seeds[self.seed_index]
        self.seed_inventory = {"corn": 5, "tomato": 5}
        self.harvested_crops = {"corn": 0, "tomato": 0}
        self.inventory = Inventory(20)
        self.max_health = 5
        self.health = self.max_health
        self.invulnerable_timer = 0.0
        self.invulnerable_duration = 0.75
        self.facing = "down"
        self.action_timer = 0.0
        self.tool_cooldown = 0.0
        self.seed_cooldown = 0.0
        self.tool_switch_cooldown = 0.0
        self.seed_switch_cooldown = 0.0
        self.pickup_cooldown = 0.0
        self.fishing_active = False
        self.fishing_has_bite = False
        self.fishing_timer = 0.0
        self.fishing_bite_time = 0.0
        self.fishing_target_tile = None
        self.fishing_bobber_pos = None
        self.fishing_message = ""
        self.fish_icon = None
        self.world_hint_seen = set()
        self.world_hint_elapsed = 0.0
        self.rock_drop_callback = None
        self.swim_visual = SwimVisual(visual_scale)
        self.feet_collision_offset = pygame.Vector2(0, -16)

        super().__init__(
            pos=pos,
            frames=self.get_scaled_frames(self.status),
            anchor="midbottom",
            animation_speed=6,
            loop=True
        )

        self.name = "player"
        self.collision_box = self.rect.copy().inflate(-self.rect.width * 0.5, -self.rect.height * 0.35)
        self.feet_collision_box = self._make_feet_collision_box()
        if self.soil_layer is not None:
            self.swim_visual.bind_world(self.soil_layer.world)

    @property
    def center(self):
        return self.rect.center

    @property
    def sort_y(self):
        return self.rect.bottom

    def get_scaled_frames(self, status):
        frames = self.assets.get_character_frames(status, self.customization)
        if self.visual_scale == 1:
            return frames

        scaled_frames = []
        for frame in frames:
            scaled_frames.append(
                pygame.transform.scale(
                    frame,
                    (
                        int(frame.get_width() * self.visual_scale),
                        int(frame.get_height() * self.visual_scale),
                    )
                )
            )
        return scaled_frames

    def set_customization(self, customization):
        self.customization = self.assets.normalize_character_customization(customization)
        self.frames = self.get_scaled_frames(self.status)
        self.index = 0
        self.image_base = self.frames[0]
        self._refresh_image()

    def get_target_pos(self):
        return pygame.Vector2(self.rect.center)

    def _make_feet_collision_box(self):
        width = max(4, int(self.rect.width * 0.2))
        height = max(4, int(self.rect.height * 0.08))
        collision_box = pygame.Rect(0, 0, width, height)
        collision_box.midbottom = self._feet_collision_midbottom()
        return collision_box

    def _feet_collision_midbottom(self):
        return (
            self.rect.midbottom[0] + self.feet_collision_offset.x,
            self.rect.midbottom[1] + self.feet_collision_offset.y,
        )

    def sync_collision_boxes(self):
        self.collision_box.center = self.rect.center
        self.feet_collision_box.midbottom = self._feet_collision_midbottom()

    def get_collision_box_for(self, obj):
        if getattr(obj, "prop_type", "") == "rock":
            return self.feet_collision_box
        return self.collision_box

    def switch_tool(self):
        self.tool_index = (self.tool_index + 1) % len(self.tools)
        self.selected_tool = self.tools[self.tool_index]

    def switch_seed(self):
        self.seed_index = (self.seed_index + 1) % len(self.seeds)
        self.selected_seed = self.seeds[self.seed_index]

    @property
    def is_alive(self):
        return self.health > 0

    def take_damage(self, amount=1):
        if amount <= 0 or self.invulnerable_timer > 0 or not self.is_alive:
            return False

        self.health = max(0, self.health - int(amount))
        self.invulnerable_timer = self.invulnerable_duration
        return True

    def heal(self, amount=1):
        if amount <= 0 or not self.is_alive:
            return False

        previous = self.health
        self.health = min(self.max_health, self.health + int(amount))
        return self.health != previous

    def get_facing_offset(self):
        if self.facing == "up":
            return 0, -1
        if self.facing == "left":
            return -1, 0
        if self.facing == "right":
            return 1, 0
        return 0, 1

    def get_facing_world_tile(self, distance=1):
        if self.soil_layer is None:
            return None

        world = self.soil_layer.world
        current_tile = (
            int(self.feet_collision_box.centerx // world.tile_size),
            int(self.feet_collision_box.centery // world.tile_size),
        )
        offset_x, offset_y = self.get_facing_offset()
        return (
            current_tile[0] + offset_x * distance,
            current_tile[1] + offset_y * distance,
        )

    def get_world_terrain_at_tile(self, world_tile):
        if self.soil_layer is None or world_tile is None:
            return None

        world = self.soil_layer.world
        chunk_w, chunk_h = world.chunk_size
        chunk_coord = (world_tile[0] // chunk_w, world_tile[1] // chunk_h)
        chunk = world.loaded_chunks.get(chunk_coord)
        if chunk is None:
            return None

        local_x = world_tile[0] % chunk_w
        local_y = world_tile[1] % chunk_h
        if not chunk.in_bounds(local_x, local_y):
            return None
        return chunk.layers["terrain"][chunk.get_index(local_x, local_y)]

    def can_fish_at_tile(self, world_tile):
        return self.get_world_terrain_at_tile(world_tile) == -1

    def get_fish_icon(self):
        if self.fish_icon is None:
            self.fish_icon = pygame.image.load(rp("graphics", "icons", "fish_hook.png")).convert_alpha()
            self.fish_icon = pygame.transform.scale(self.fish_icon, (32, 32))
        return self.fish_icon

    def add_fish_to_inventory(self):
        self.inventory.add_item_to_slot(
            Item(
                "fish",
                self.get_fish_icon(),
                True,
                self.inventory.craft_system.return_craft_product("fish"),
            )
        )

    def start_fishing(self):
        target_tile = None
        for distance in (1, 2):
            candidate_tile = self.get_facing_world_tile(distance=distance)
            if self.can_fish_at_tile(candidate_tile):
                target_tile = candidate_tile
                break

        if target_tile is None:
            self.fishing_message = "Face water to fish"
            return False

        world = self.soil_layer.world
        self.fishing_active = True
        self.fishing_has_bite = False
        self.fishing_timer = 0.0
        self.fishing_bite_time = 1.2 + (pygame.time.get_ticks() % 1800) / 1000.0
        self.fishing_target_tile = target_tile
        self.fishing_bobber_pos = (
            target_tile[0] * world.tile_size + world.tile_size // 2,
            target_tile[1] * world.tile_size + world.tile_size // 2,
        )
        self.fishing_message = "Waiting..."
        return True

    def reel_fishing_line(self):
        if not self.fishing_active:
            return False

        caught = self.fishing_has_bite
        if caught:
            self.add_fish_to_inventory()
            self.fishing_message = "Caught fish"
        else:
            self.fishing_message = "Too soon"

        self.fishing_active = False
        self.fishing_has_bite = False
        self.fishing_target_tile = None
        self.fishing_bobber_pos = None
        return caught

    def use_fishing_rod(self):
        if self.fishing_active:
            self.reel_fishing_line()
            return
        self.start_fishing()

    def use_tool(self):
        if self.soil_layer is None:
            return

        target_pos = self.get_target_pos()
        if self.selected_tool == "hoe":
            self.soil_layer.till_at(target_pos)
        elif self.selected_tool == "water":
            self.soil_layer.water_at(target_pos)
        elif self.selected_tool == "fishing rod":
            self.use_fishing_rod()
        elif self.selected_tool == "axe":
            tile_size = self.soil_layer.world.tile_size
            target_area = self.feet_collision_box.inflate(tile_size, tile_size)
            for chunk in self.soil_layer.world.loaded_chunks.values():
                for rock in chunk.runtime.get("environment_objects", {}).values():
                    if getattr(rock, "prop_type", "") == "rock" and rock.alive and target_area.colliderect(rock.collision_box):
                        result = rock.damage()
                        if result and result.get("broken") and self.rock_drop_callback is not None:
                            self.rock_drop_callback(chunk, rock, result.get("drops", 0))
                        return
                for tree in chunk.runtime.get("tree_objects", {}).values():
                    if tree.alive and target_area.colliderect(tree.collision_box):
                        tree.damage(self, self.inventory)
                        return

    def use_seed(self):
        if self.soil_layer is None:
            return
        if self.seed_inventory.get(self.selected_seed, 0) <= 0:
            return

        if self.soil_layer.plant_seed_at(self.get_target_pos(), self.selected_seed):
            self.seed_inventory[self.selected_seed] -= 1

    def update_timers(self, dt):
        self.action_timer = max(0.0, self.action_timer - dt)
        self.tool_cooldown = max(0.0, self.tool_cooldown - dt)
        self.seed_cooldown = max(0.0, self.seed_cooldown - dt)
        self.tool_switch_cooldown = max(0.0, self.tool_switch_cooldown - dt)
        self.seed_switch_cooldown = max(0.0, self.seed_switch_cooldown - dt)
        self.pickup_cooldown = max(0.0, self.pickup_cooldown - dt)
        self.invulnerable_timer = max(0.0, self.invulnerable_timer - dt)
        if self.fishing_active:
            self.fishing_timer += dt
            if not self.fishing_has_bite and self.fishing_timer >= self.fishing_bite_time:
                self.fishing_has_bite = True
                self.fishing_message = "Bite! Space"

    def handle_input(self):
        keys = pygame.key.get_pressed()
        if keys[pygame.K_q] and self.tool_switch_cooldown <= 0:
            self.switch_tool()
            self.tool_switch_cooldown = 0.2

        if keys[pygame.K_e] and self.seed_switch_cooldown <= 0:
            self.switch_seed()
            self.seed_switch_cooldown = 0.2

        if keys[pygame.K_SPACE] and self.tool_cooldown <= 0:
            self.use_tool()
            self.action_timer = 0.35
            self.tool_cooldown = 0.35
            self.direction.x = 0
            self.direction.y = 0
            return

        if (keys[pygame.K_LCTRL] or keys[pygame.K_RCTRL]) and self.seed_cooldown <= 0:
            self.use_seed()
            self.action_timer = 0.35
            self.seed_cooldown = 0.35
            self.direction.x = 0
            self.direction.y = 0
            return

        if self.action_timer > 0:
            self.direction.x = 0
            self.direction.y = 0
            return

        self.direction.x = (keys[pygame.K_d] or keys[pygame.K_RIGHT]) - (keys[pygame.K_a] or keys[pygame.K_LEFT])
        self.direction.y = (keys[pygame.K_s] or keys[pygame.K_DOWN]) - (keys[pygame.K_w] or keys[pygame.K_UP])

        if self.direction.length_squared() > 0:
            self.direction = self.direction.normalize()

    def update_status(self):
        if self.action_timer > 0:
            if self.selected_tool == "fishing rod" or self.fishing_active:
                self.status = "down_fish" if self.fishing_has_bite else "down_cast"
                return
            if self.seed_cooldown > 0 and self.seed_cooldown >= self.tool_cooldown:
                self.status = f"{self.facing}_seed"
            else:
                self.status = f"{self.facing}_{self.selected_tool}"
            return

        if self.fishing_active:
            self.status = "down_fish" if self.fishing_has_bite else "down_cast"
            return

        if self.direction.length_squared() == 0:
            if not self.status.endswith("_idle"):
                self.status = self.status.split("_")[0] + "_idle"
            return

        if abs(self.direction.x) > abs(self.direction.y):
            self.status = "right" if self.direction.x > 0 else "left"
        else:
            self.status = "down" if self.direction.y > 0 else "up"
        self.facing = self.status

    def refresh_animation_set(self):
        if self.status == self.last_status:
            return

        self.frames = self.get_scaled_frames(self.status)
        self.index = 0
        self.image_base = self.frames[0]
        self._refresh_image()
        self.collision_box = self.rect.copy().inflate(-self.rect.width * 0.5, -self.rect.height * 0.35)
        self.feet_collision_box = self._make_feet_collision_box()
        self.last_status = self.status

    def move(self, dt, collision_objects=None):
        if collision_objects is None:
            collision_objects = []

        self.pos.x += self.direction.x * self.speed * dt
        self.rect.midbottom = (round(self.pos.x), round(self.pos.y))
        self.sync_collision_boxes()

        for obj in collision_objects:
            player_collision_box = self.get_collision_box_for(obj)
            if hasattr(obj, "collision_box") and player_collision_box.colliderect(obj.collision_box):
                if self.direction.x > 0:
                    player_collision_box.right = obj.collision_box.left
                elif self.direction.x < 0:
                    player_collision_box.left = obj.collision_box.right
                self.rect.centerx = player_collision_box.centerx
                self.pos.x = self.rect.midbottom[0]
                self.sync_collision_boxes()

        self.pos.y += self.direction.y * self.speed * dt
        self.rect.midbottom = (round(self.pos.x), round(self.pos.y))
        self.sync_collision_boxes()

        for obj in collision_objects:
            player_collision_box = self.get_collision_box_for(obj)
            if hasattr(obj, "collision_box") and player_collision_box.colliderect(obj.collision_box):
                if self.direction.y > 0:
                    player_collision_box.bottom = obj.collision_box.top
                elif self.direction.y < 0:
                    player_collision_box.top = obj.collision_box.bottom
                if player_collision_box is self.feet_collision_box:
                    self.rect.bottom = player_collision_box.bottom
                else:
                    self.rect.centery = player_collision_box.centery
                self.pos.y = self.rect.midbottom[1]
                self.sync_collision_boxes()

    def update(self, dt, collision_objects=None):
        self.update_timers(dt)
        self.handle_input()
        self.update_status()
        self.refresh_animation_set()
        self.move(dt, collision_objects)
        self.animate(dt)
        self.swim_visual.update(self, dt)
        self.tick_opacity(dt)

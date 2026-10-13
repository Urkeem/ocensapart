"""In-game HUD drawing for player tools, time, weather, and inventory status."""

import pygame

from gameplay.controls import (
    AXIS_HOTBAR,
    AXIS_INVENTORY,
    BUTTON_CANCEL,
    BUTTON_CONFIRM,
    BUTTON_DPAD_LEFT,
    BUTTON_DPAD_RIGHT,
    BUTTON_CONSUME,
    get_controller_input,
)
from ui.inventory import Inventory_UI, Hot_Bar_UI, load_item_icon
from ui.quest_journal import QuestJournalUI
from inventory_item import Item
from gameplay.events import (
    EncounterCompleted,
    EncounterFailed,
    EncounterWaveCompleted,
    EnemyLootGranted,
    ProgressionUpdated,
    QuestStateChanged,
)
from gameplay.fishing import fish_species, next_fish_unlocks
from gameplay.game_state import experience_to_reach_level
from data.crops import crop_definition, next_crop_unlocks
from data.locations import LOCATION_CONNECTIONS, LOCATION_DEFINITIONS
from data.story import STORY_NPC_PLACEMENTS
from utils import rp


HOME_MARKER_COLOR = (82, 170, 255)
# Kept as a public palette alias for farm-generation tests and extensions;
# only the player's home marker is drawn on the minimap now.
FARMSTEAD_MARKER_COLOR = HOME_MARKER_COLOR
QUEST_MARKER_COLOR = (255, 214, 76)
NEARBY_ENEMY_RADIUS = 560


class GameplayHUD:
    def __init__(self, player, screen):
        self.player = player
        self.screen = screen
        self.screen_w, self.screen_h = screen.get_size()
        accessibility = getattr(getattr(player, "game_state", None), "accessibility", None)
        text_scale = getattr(accessibility, "text_scale", 1.0)
        self.high_contrast = bool(getattr(accessibility, "high_contrast", False))
        self.font = pygame.font.Font(rp("font", "LycheeSoda.ttf"), round(22 * text_scale))
        self.small_font = pygame.font.Font(rp("font", "LycheeSoda.ttf"), round(16 * text_scale))
        self.death_title_font = pygame.font.Font(rp("font", "LycheeSoda.ttf"), round(50 * text_scale))

        self.inventory_ui = Inventory_UI(
            player.inventory,
            screen,
            (self.screen_w // 2, self.screen_h // 2),
            player,
        )
        self.hotbar_ui = Hot_Bar_UI(
            player.inventory,
            screen,
            (self.screen_w // 2, int(self.screen_h * 0.92)),
        )

        self.overlay_icons = {}
        self.life_icons = {}
        self.minimap_size = 170
        self.minimap_padding = 14
        self.death_options = ("Exit", "Revive")
        self.death_selection = 1
        self.death_exit_requested = False
        self.death_button_rects = []
        self.notification_text = ""
        self.notification_until = 0
        self.notification_queue = []
        self._progression_unsubscribe = None
        self.quest_journal = None
        self._last_trust_npc = "wife"
        self._minimap_cache_key = None
        self._minimap_cache_surface = None

    @property
    def journal_open(self):
        return bool(self.quest_journal and self.quest_journal.open)

    def set_quest_system(self, quest_system):
        self.quest_journal = QuestJournalUI(self.screen, self.player, quest_system)

    def bind_progression_events(self, dispatcher, effects=None):
        if self._progression_unsubscribe is not None:
            self._progression_unsubscribe()

        def on_progression(event):
            if event.track == "trust" and event.source_id in STORY_NPC_PLACEMENTS:
                self._last_trust_npc = event.source_id
            source = (
                crop_definition(event.source_id)
                if event.track == "farming"
                else fish_species(event.source_id)
                if event.track == "fishing"
                else None
            )
            label = source.display_name if source is not None and hasattr(source, "display_name") else source.name if source is not None else event.source_id
            reward_label = (
                "XP"
                if event.track == "experience"
                else f"{event.track.replace('_', ' ').title()} points"
            )
            self.show_notification(f"+{event.amount} {reward_label}: {label}")
            for unlock_id in event.unlocked_ids:
                self.show_notification(self._unlock_message(unlock_id), duration_ms=3000)
            if effects is not None:
                effects.spawn(
                    "points_reward",
                    self.player.center,
                    follow=self.player,
                    offset=(0, -48),
                )

        unsubscribes = [
            dispatcher.subscribe(ProgressionUpdated, on_progression),
            dispatcher.subscribe(
                EnemyLootGranted,
                lambda event: self.show_notification(
                    f"Loot: {event.count} {event.item_id.replace('_', ' ').title()}"
                ),
            ),
            dispatcher.subscribe(
                EncounterWaveCompleted,
                lambda event: self.show_notification(f"Wave {event.wave} cleared"),
            ),
            dispatcher.subscribe(
                EncounterCompleted,
                lambda event: self.show_notification("Defense won - return to your Wife"),
            ),
            dispatcher.subscribe(
                EncounterFailed,
                lambda event: self.show_notification("Defense failed - recover to retry"),
            ),
            dispatcher.subscribe(
                QuestStateChanged,
                lambda event: self.show_notification(
                    f"Quest complete: {event.quest_id.replace('.', ' - ').replace('_', ' ').title()}",
                    duration_ms=3200,
                )
                if event.new_status == "completed"
                else None,
            ),
        ]

        def unsubscribe_all():
            for unsubscribe in unsubscribes:
                unsubscribe()

        self._progression_unsubscribe = unsubscribe_all

    def close(self):
        if self._progression_unsubscribe is not None:
            self._progression_unsubscribe()
            self._progression_unsubscribe = None

    @staticmethod
    def _unlock_message(unlock_id):
        if unlock_id.startswith("crop."):
            crop = crop_definition(unlock_id.removeprefix("crop."))
            return f"Crop unlocked: {crop.display_name if crop else unlock_id} seeds"
        if unlock_id.startswith("fishing.locality."):
            locality = unlock_id.rsplit(".", 1)[-1]
            return f"{'Sea' if locality == 'ocean' else locality.title()} fishing unlocked"
        if unlock_id.startswith("fish."):
            fish = fish_species(unlock_id.removeprefix("fish."))
            return f"Fish unlocked: {fish.name if fish else unlock_id}"
        return f"Unlocked: {unlock_id.replace('.', ' ').title()}"

    def load_icon(self, name):
        icon = self.overlay_icons.get(name)
        if icon is not None:
            return icon

        icon = load_item_icon(name, (48, 48))
        if not icon:
            try:
                crop_sheet = pygame.image.load(
                    rp("graphics", "environment", "crops", f"{name}.png")
                ).convert_alpha()
                icon = crop_sheet.subsurface((16, 16, 16, 16)).copy()
                icon = pygame.transform.scale(icon, (48, 48))
            except (FileNotFoundError, ValueError, pygame.error):
                icon = pygame.image.load(
                    rp("graphics", "overlay", f"{name}.png")
                ).convert_alpha()
                icon = pygame.transform.scale(icon, (48, 48))
        self.overlay_icons[name] = icon
        return icon

    def load_life_icon(self, state):
        icon = self.life_icons.get(state)
        if icon is not None:
            return icon

        frame = self.player.assets.life_frames[str(state)]
        icon = self.player.assets.all_sprite_sheet.get_sprite(*frame).convert_alpha()
        icon = pygame.transform.scale(icon, (30, 30))
        self.life_icons[state] = icon
        return icon

    def populate_inventory(self):
        pass

    def get_count(self, name):
        return None

    def sync_counts(self):
        for slot in self.player.inventory.slots:
            name = slot.item.name
            if not name:
                continue
            count = self.get_count(name)
            if count is not None:
                slot.amount = count

    def handle_event(self, event):
        if self.quest_journal is not None:
            handled = self.quest_journal.handle_event(event)
            if handled:
                return True
        controller_input = getattr(self.player, "controller_input", get_controller_input())
        if not self.player.is_alive:
            self.player.inventory.is_inv = False
            if not self.player.death_animation_complete:
                return
            axis_button = controller_input.menu_navigation_button(event)
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_LEFT, pygame.K_a):
                    self.death_selection = 0
                elif event.key in (pygame.K_RIGHT, pygame.K_d):
                    self.death_selection = 1
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    self.activate_death_option()
            elif event.type == pygame.CONTROLLERBUTTONDOWN:
                if event.button == BUTTON_DPAD_LEFT:
                    self.death_selection = 0
                elif event.button == BUTTON_DPAD_RIGHT:
                    self.death_selection = 1
                elif event.button == BUTTON_CONFIRM:
                    self.activate_death_option()
            elif axis_button == BUTTON_DPAD_LEFT:
                self.death_selection = 0
            elif axis_button == BUTTON_DPAD_RIGHT:
                self.death_selection = 1
            elif event.type == pygame.MOUSEMOTION:
                for index, rect in enumerate(self.death_button_rects):
                    if rect.collidepoint(event.pos):
                        self.death_selection = index
                        break
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for index, rect in enumerate(self.death_button_rects):
                    if rect.collidepoint(event.pos):
                        self.death_selection = index
                        self.activate_death_option()
                        break
            return
        if event.type == pygame.KEYDOWN and event.key == pygame.K_v:
            restored = self.player.consume_food()
            self.show_notification(f"Ate food: +{restored:g} stamina" if restored else "No usable food or stamina is full")
            return True
        if event.type == pygame.CONTROLLERBUTTONDOWN and event.button == BUTTON_CONSUME:
            food_name = (
                self.inventory_ui.focused_inventory_food()
                if self.player.inventory.is_inv
                else self.player.selected_hotbar_food()
            )
            if food_name is not None:
                self.player.select_consumable(food_name)
                restored = self.player.consume_food(food_name)
                self.player._consume_button_lock = True
                self.player.tool_cooldown = max(self.player.tool_cooldown, 0.2)
                self.show_notification(
                    f"Ate food: +{restored:g} stamina"
                    if restored
                    else "Stamina is already full"
                )
                return True
            if self.player.inventory.is_inv:
                self.show_notification("The selected item cannot be eaten")
                return True
        hotbar_requested = (
            (event.type == pygame.KEYDOWN and event.key == pygame.K_h)
            or controller_input.is_axis_pressed(event, AXIS_HOTBAR)
        )
        if hotbar_requested:
            slot_index = self.player.cycle_hotbar_slot()
            slot = self.player.inventory.slots[slot_index]
            label = slot.item.name.replace("_", " ").title() if slot.item.name else "Empty slot"
            self.show_notification(f"Hotbar {slot_index + 1}: {label}")
            return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            slot_index = self.hotbar_ui.slot_at(event.pos)
            if slot_index is not None and not self.player.inventory.is_inv:
                self.player.activate_hotbar_slot(slot_index)
                return True
        keyboard_toggle = (
            event.type == pygame.KEYDOWN
            and event.key in (pygame.K_i, pygame.K_RETURN)
        )
        controller_toggle = controller_input.is_axis_pressed(event, AXIS_INVENTORY)
        if keyboard_toggle or controller_toggle:
            self.player.inventory.is_inv = not self.player.inventory.is_inv
            return

        if (
            self.player.inventory.is_inv
            and event.type == pygame.CONTROLLERBUTTONDOWN
        ):
            if event.button == BUTTON_CANCEL:
                self.player.inventory.is_inv = False
                self.player.seed_cooldown = max(self.player.seed_cooldown, 0.2)
                # Prevent the same Circle press from becoming a combat dodge
                # later in the session event pipeline.
                self.player.action_lock_timer = max(self.player.action_lock_timer, 0.1)
            else:
                self.inventory_ui.handle_controller_button(event.button)
            return


        if self.player.inventory.is_inv:
            axis_button = controller_input.menu_navigation_button(event)
            if axis_button is not None:
                self.inventory_ui.handle_controller_button(axis_button)
                return

        if self.player.inventory.is_inv and event.type == pygame.MOUSEBUTTONDOWN and event.button in (1, 3):
            restored = self.inventory_ui.handle_click((event.button, event.pos))
            if event.button == 3:
                self.show_notification(
                    f"Ate food: +{restored:g} stamina"
                    if restored
                    else "That item is not edible or stamina is full"
                )
            return True

    def activate_death_option(self):
        option = self.death_options[self.death_selection]
        if option == "Revive":
            self.player.revive()
            self.death_selection = 1
        else:
            self.death_exit_requested = True

    def draw_death_panel(self):
        if getattr(self.player, "recovery_active", False) or not self.player.death_animation_complete:
            return

        shade = pygame.Surface((self.screen_w, self.screen_h), pygame.SRCALPHA)
        shade.fill((3, 5, 10, 190))
        self.screen.blit(shade, (0, 0))

        panel = pygame.Rect(0, 0, 430, 220)
        panel.center = (self.screen_w // 2, self.screen_h // 2)
        pygame.draw.rect(self.screen, (7, 10, 16, 190), panel.move(0, 5), border_radius=14)
        pygame.draw.rect(self.screen, (24, 28, 39), panel, border_radius=14)
        pygame.draw.rect(self.screen, (154, 49, 49), panel, 3, border_radius=14)

        title = self.death_title_font.render("YOU DIED", True, (236, 226, 218))
        self.screen.blit(title, title.get_rect(midtop=(panel.centerx, panel.y + 24)))

        button_size = (150, 52)
        gap = 22
        start_x = panel.centerx - (button_size[0] * 2 + gap) // 2
        button_y = panel.y + 118
        self.death_button_rects = [
            pygame.Rect(start_x + index * (button_size[0] + gap), button_y, *button_size)
            for index in range(2)
        ]
        for index, (label, rect) in enumerate(zip(self.death_options, self.death_button_rects)):
            selected = index == self.death_selection
            fill = (126, 43, 43) if selected else (37, 44, 58)
            border = (239, 185, 94) if selected else (103, 116, 135)
            pygame.draw.rect(self.screen, fill, rect, border_radius=8)
            pygame.draw.rect(self.screen, border, rect, 2, border_radius=8)
            text = self.font.render(label, True, (244, 244, 242))
            self.screen.blit(text, text.get_rect(center=rect.center))

        hint = self.small_font.render(
            "Left / Right to choose    Enter / Cross to confirm",
            True,
            (177, 186, 199),
        )
        self.screen.blit(hint, hint.get_rect(midbottom=(panel.centerx, panel.bottom - 12)))

    def get_selected_hotbar_index(self):
        return int(getattr(self.player, "hotbar_slot_index", 0))

    def draw_selected_overlay(self):
        placeable = self.player.inventory.get_selected_placeable()
        active_name = placeable.name if placeable is not None else self.player.selected_tool
        tool_icon = self.load_icon(active_name)
        seed_icon = self.load_icon(self.player.selected_seed)
        weapon_icon = self.load_icon(getattr(self.player, "selected_weapon", "sword"))

        weapon_rect = weapon_icon.get_rect(midbottom=(self.screen_w - 64, self.screen_h - 42))
        tool_rect = tool_icon.get_rect(midbottom=(self.screen_w - 124, self.screen_h - 42))
        seed_rect = seed_icon.get_rect(midbottom=(self.screen_w - 184, self.screen_h - 42))

        selected_slot = getattr(self.player, "selected_selection_slot", "tool")
        slot_specs = (
            ("seed", seed_rect, (209, 177, 87)),
            ("tool", tool_rect, (76, 145, 201)),
            ("weapon", weapon_rect, (201, 92, 92)),
        )
        for slot_name, rect, color in slot_specs:
            panel = rect.inflate(16, 16)
            pygame.draw.rect(self.screen, (12, 18, 29), panel, border_radius=8)
            pygame.draw.rect(
                self.screen,
                (244, 236, 174) if selected_slot == slot_name else color,
                panel,
                4 if selected_slot == slot_name else 2,
                border_radius=8,
            )

        self.screen.blit(tool_icon, tool_rect)
        self.screen.blit(seed_icon, seed_rect)
        self.screen.blit(weapon_icon, weapon_rect)

        if placeable is not None:
            tool_status = str(self.player.inventory.count_item(placeable.name))
        else:
            durability = self.player.tool_durability.get(self.player.selected_tool, 0)
            maximum = self.player.tool_max_durability.get(self.player.selected_tool, 0)
            tool_status = f"{durability}/{maximum}"
            if self.player.selected_tool == "water":
                tool_status = f"{self.player.water_amount}/{self.player.water_capacity}  {tool_status}"
        status_text = self.small_font.render(tool_status, True, (236, 240, 245))
        self.screen.blit(
            status_text,
            status_text.get_rect(midtop=(tool_rect.centerx, tool_rect.bottom + 2)),
        )

        seed_count = self.font.render(str(self.player.seed_inventory.get(self.player.selected_seed, 0)), True, (236, 240, 245))
        self.screen.blit(seed_count, seed_count.get_rect(midtop=(seed_rect.centerx, seed_rect.bottom + 2)))

        weapon_name = getattr(self.player, "selected_weapon", "sword")
        weapon_status = self.small_font.render(
            f"{self.player.tool_durability.get(weapon_name, 0)}/{self.player.tool_max_durability.get(weapon_name, 0)}",
            True,
            (236, 240, 245),
        )
        self.screen.blit(weapon_status, weapon_status.get_rect(midtop=(weapon_rect.centerx, weapon_rect.bottom + 2)))

    def show_notification(self, text, duration_ms=2400):
        now = pygame.time.get_ticks()
        if self.notification_text and now < self.notification_until:
            self.notification_queue.append((str(text), int(duration_ms)))
            return
        self.notification_text = str(text)
        self.notification_until = now + int(duration_ms)

    def draw_progression_panel(self):
        state = getattr(self.player, "game_state", None)
        if state is None:
            return
        panel = pygame.Rect(self.screen_w - 224, 152, 210, 66)
        pygame.draw.rect(self.screen, (9, 14, 21, 210), panel, border_radius=8)
        pygame.draw.rect(self.screen, (99, 151, 102), panel, 2, border_radius=8)
        farming = state.progression.farming_points
        fishing = state.progression.fishing_points
        label = self.small_font.render(
            f"Farming {farming}     Fishing {fishing}",
            True,
            (229, 239, 220),
        )
        self.screen.blit(label, (panel.x + 10, panel.y + 8))
        crop_next = next_crop_unlocks(state, limit=1)
        fish_next = next_fish_unlocks(state, limit=1)
        crop_text = "All crops unlocked" if not crop_next else f"Next crop: {crop_next[0].unlock_at_farming_points}"
        fish_text = "All fish unlocked" if not fish_next else f"Next fish: {fish_next[0].unlock_at_fishing_points}"
        detail = self.small_font.render(
            f"{crop_text}  |  {fish_text}",
            True,
            (177, 198, 180),
        )
        self.screen.blit(detail, (panel.x + 10, panel.y + 36))

    def draw_health_panel(self):
        max_health = max(1, int(getattr(self.player, "max_health", 1)))
        health = max(0, min(max_health, int(getattr(self.player, "health", max_health))))
        panel = pygame.Rect(14, 14, 270, 58)

        pygame.draw.rect(self.screen, (7, 10, 16, 150), panel.move(0, 3), border_radius=8)
        pygame.draw.rect(self.screen, (18, 26, 38, 226), panel, border_radius=8)
        pygame.draw.rect(self.screen, (209, 177, 87), panel, 2, border_radius=8)
        hp_label = self.font.render("HP", True, (242, 236, 224))
        self.screen.blit(hp_label, hp_label.get_rect(midleft=(panel.x + 14, panel.centery)))
        bar = pygame.Rect(panel.x + 58, panel.y + 15, 190, 28)
        pygame.draw.rect(self.screen, (53, 24, 29), bar, border_radius=7)
        fill_width = round(bar.width * (health / max_health))
        if fill_width > 0:
            pygame.draw.rect(
                self.screen,
                (194, 48, 58),
                pygame.Rect(bar.x, bar.y, fill_width, bar.height),
                border_radius=7,
            )
        pygame.draw.rect(self.screen, (113, 124, 141), bar, 2, border_radius=7)
        value = self.small_font.render(f"{health}/{max_health}", True, (250, 244, 236))
        self.screen.blit(value, value.get_rect(center=bar.center))

    def draw_stamina_panel(self):
        state = getattr(self.player, "game_state", None)
        if state is None or not getattr(self.player, "stamina_enabled", False):
            return
        panel = pygame.Rect(14, 76, 270, 42)
        pygame.draw.rect(self.screen, (9, 14, 21, 200), panel, border_radius=8)
        pygame.draw.rect(self.screen, (209, 177, 87), panel, 2, border_radius=8)
        bar = pygame.Rect(panel.x + 82, panel.y + 10, 172, 22)
        pygame.draw.rect(self.screen, (45, 39, 24), bar, border_radius=6)
        ratio = max(0.0, min(1.0, state.stamina / max(1.0, state.max_stamina)))
        if ratio:
            pygame.draw.rect(self.screen, (225, 174, 58), pygame.Rect(bar.x, bar.y, round(bar.width * ratio), bar.height), border_radius=6)
        label = self.small_font.render("Stamina", True, (240, 230, 205))
        self.screen.blit(label, label.get_rect(midleft=(panel.x + 10, panel.centery)))
        value = self.small_font.render(f"{round(state.stamina)}/{round(state.max_stamina)}", True, (251, 243, 220))
        self.screen.blit(value, value.get_rect(center=bar.center))

    def _draw_progress_bar(self, rect, label, value_text, ratio, fill_color):
        pygame.draw.rect(self.screen, (9, 14, 21), rect, border_radius=8)
        pygame.draw.rect(self.screen, (91, 105, 124), rect, 2, border_radius=8)
        label_surface = self.small_font.render(label, True, (236, 240, 245))
        self.screen.blit(label_surface, label_surface.get_rect(midleft=(rect.x + 10, rect.centery)))
        bar = pygame.Rect(rect.x + 116, rect.y + 9, rect.width - 130, rect.height - 18)
        pygame.draw.rect(self.screen, (28, 33, 44), bar, border_radius=6)
        fill_width = round(bar.width * max(0.0, min(1.0, float(ratio))))
        if fill_width:
            pygame.draw.rect(
                self.screen,
                fill_color,
                pygame.Rect(bar.x, bar.y, fill_width, bar.height),
                border_radius=6,
            )
        pygame.draw.rect(self.screen, (113, 124, 141), bar, 1, border_radius=6)
        value = self.small_font.render(value_text, True, (250, 244, 236))
        self.screen.blit(value, value.get_rect(center=bar.center))

    def _trust_subject(self, npc_manager, state):
        candidates = [
            npc
            for npc in getattr(npc_manager, "npcs", ())
            if getattr(npc, "story_id", None) in STORY_NPC_PLACEMENTS
            and getattr(npc, "is_alive", True)
        ]
        if candidates:
            player_pos = pygame.Vector2(self.player.center)
            nearby = [
                npc
                for npc in candidates
                if player_pos.distance_squared_to(npc.rect.midbottom) <= 520 * 520
            ]
            location_matches = [
                npc
                for npc in candidates
                if getattr(npc, "location_id", None) == state.current_location_id
            ]
            pool = nearby or location_matches
            if pool:
                subject = min(pool, key=lambda npc: player_pos.distance_squared_to(npc.rect.midbottom))
                self._last_trust_npc = subject.story_id
                return subject.story_id
        if self._last_trust_npc in STORY_NPC_PLACEMENTS:
            return self._last_trust_npc
        if state.relationships:
            return max(state.relationships, key=lambda npc_id: state.relationships[npc_id].trust)
        return "wife"

    def draw_experience_and_trust(self, npc_manager=None):
        state = getattr(self.player, "game_state", None)
        if state is None:
            return
        progression = state.progression
        level = max(1, int(progression.level))
        start_xp = experience_to_reach_level(level)
        next_xp = experience_to_reach_level(level + 1)
        earned = max(0, int(progression.experience) - start_xp)
        needed = max(1, next_xp - start_xp)
        self._draw_progress_bar(
            pygame.Rect(14, 122, 270, 40),
            f"Level {level}",
            f"{earned}/{needed} XP",
            earned / needed,
            (83, 139, 219),
        )

        npc_id = self._trust_subject(npc_manager, state)
        relationship = state.relationships.get(npc_id)
        trust = max(0, int(relationship.trust if relationship is not None else 0))
        tier = relationship.tier.title() if relationship is not None else "Unknown"
        npc_name = STORY_NPC_PLACEMENTS.get(npc_id, {}).get(
            "name",
            npc_id.replace("_", " ").title(),
        )
        self._draw_progress_bar(
            pygame.Rect(14, 166, 270, 40),
            f"{npc_name} Trust",
            f"{trust}/100  {tier}",
            trust / 100,
            (178, 93, 177),
        )

    def draw_coin_panel(self):
        panel = pygame.Rect(self.screen_w - 174, 14, 160, 54)
        pygame.draw.rect(self.screen, (7, 10, 16, 150), panel.move(0, 3), border_radius=8)
        pygame.draw.rect(self.screen, (18, 26, 38, 226), panel, border_radius=8)
        pygame.draw.rect(self.screen, (209, 177, 87), panel, 2, border_radius=8)
        icon = self.load_icon("coin")
        icon = pygame.transform.scale(icon, (34, 34))
        self.screen.blit(icon, icon.get_rect(midleft=(panel.x + 12, panel.centery)))
        amount = self.font.render(str(self.player.coins), True, (247, 224, 139))
        self.screen.blit(amount, amount.get_rect(midleft=(panel.x + 58, panel.centery)))

    def draw_weather_panel(self, weather):
        if weather is None:
            return
        panel = pygame.Rect(self.screen_w - 224, 78, 210, 66)
        pygame.draw.rect(self.screen, (7, 10, 16, 150), panel.move(0, 3), border_radius=8)
        pygame.draw.rect(self.screen, (18, 26, 38, 226), panel, border_radius=8)
        pygame.draw.rect(self.screen, (76, 145, 201), panel, 2, border_radius=8)
        title = self.font.render(
            f"{weather.time.formatted()}  {weather.weather}",
            True,
            (236, 240, 245),
        )
        subtitle = self.small_font.render(
            f"{weather.current_season}  Day {weather.time.day}",
            True,
            (190, 204, 214),
        )
        self.screen.blit(title, (panel.x + 12, panel.y + 8))
        self.screen.blit(subtitle, (panel.x + 12, panel.y + 37))

    def draw_notification(self):
        now = pygame.time.get_ticks()
        if self.notification_text and now >= self.notification_until:
            if self.notification_queue:
                self.notification_text, duration = self.notification_queue.pop(0)
                self.notification_until = now + duration
            else:
                self.notification_text = ""
        if not self.notification_text:
            return
        text = self.small_font.render(self.notification_text, True, (244, 240, 225))
        rect = text.get_rect(midtop=(self.screen_w // 2, 18)).inflate(24, 14)
        pygame.draw.rect(self.screen, (18, 26, 38), rect, border_radius=8)
        pygame.draw.rect(self.screen, (209, 177, 87), rect, 2, border_radius=8)
        self.screen.blit(text, text.get_rect(center=rect.center))

    def _minimap_rect(self):
        return pygame.Rect(
            self.screen_w - self.minimap_size - self.minimap_padding,
            max(self.minimap_padding, self.screen_h - self.minimap_size - 112),
            self.minimap_size,
            self.minimap_size,
        )

    def _minimap_tile_bounds(self, world):
        chunk_w, chunk_h = world.chunk_size
        low_offset = -(world.level_size_chunks // 2)
        high_offset = low_offset + world.level_size_chunks
        min_chunk_x = world.spawn_chunk[0] + low_offset
        min_chunk_y = world.spawn_chunk[1] + low_offset
        max_chunk_x = world.spawn_chunk[0] + high_offset
        max_chunk_y = world.spawn_chunk[1] + high_offset
        return (
            min_chunk_x * chunk_w,
            min_chunk_y * chunk_h,
            max_chunk_x * chunk_w,
            max_chunk_y * chunk_h,
        )

    def _minimap_point(self, world, rect, world_pixel_pos):
        min_x, min_y, max_x, max_y = self._minimap_tile_bounds(world)
        tile_x = world_pixel_pos[0] / world.tile_size
        tile_y = world_pixel_pos[1] / world.tile_size
        width = max(1, max_x - min_x)
        height = max(1, max_y - min_y)
        return (
            rect.x + int(((tile_x - min_x) / width) * rect.width),
            rect.y + int(((tile_y - min_y) / height) * rect.height),
        )

    def _enemy_positions(self, npc_manager):
        if npc_manager is None:
            return []
        positions = []
        for npc in getattr(npc_manager, "npcs", []):
            is_enemy = (
                getattr(npc, "is_enemy", False)
                or getattr(npc, "hostile", False)
                or getattr(npc, "faction", None) == "enemy"
                or getattr(npc, "name", "") == "enemy"
            )
            npc_pos = (
                npc.center
                if hasattr(npc, "center")
                else npc.rect.center
                if hasattr(npc, "rect")
                else None
            )
            if (
                is_enemy
                and npc_pos is not None
                and getattr(npc, "is_alive", True)
                and getattr(npc, "location_id", "player_farm")
                == getattr(getattr(self.player, "game_state", None), "current_location_id", "player_farm")
                and pygame.Vector2(npc_pos).distance_squared_to(self.player.center)
                <= NEARBY_ENEMY_RADIUS * NEARBY_ENEMY_RADIUS
            ):
                positions.append(npc_pos)
        return positions

    def _home_position(self, world):
        state = getattr(self.player, "game_state", None)
        if state is None or state.current_location_id != "player_farm":
            return None
        position = state.flag("player_farm.exterior_spawn", None)
        if position is not None:
            return position
        farms = self._farmstead_positions(world)
        return farms[0] if farms else None

    @staticmethod
    def _dialogue_target_ids(node_filter):
        node_ids = node_filter if isinstance(node_filter, (tuple, list, set, frozenset)) else (node_filter,)
        return {
            str(node_id).split(".", 1)[0]
            for node_id in node_ids
            if node_id
        }

    def _needed_villager_ids(self):
        if self.quest_journal is None:
            return set()
        quest_system = self.quest_journal.quest_system
        wanted_ids = set()
        for quest_id, definition in quest_system.definitions.items():
            state = quest_system.game_state.quests.get(quest_id, {})
            status = state.get("status")
            if status == "available":
                wanted_ids.add(definition.get("giver"))
            elif status == "ready_to_turn_in":
                wanted_ids.add(definition.get("turn_in"))
            elif status == "active":
                for objective in definition.get("objectives", ()):
                    if objective.get("event") != "DialogueCompleted":
                        continue
                    if int(state.get("objectives", {}).get(objective["id"], 0)) >= int(objective.get("required", 1)):
                        continue
                    wanted_ids.update(
                        self._dialogue_target_ids(
                            objective.get("filters", {}).get("node_id")
                        )
                    )
        wanted_ids.discard(None)
        return wanted_ids

    @staticmethod
    def _first_location_step(origin_id, destination_id):
        if origin_id == destination_id:
            return origin_id
        queue = [(origin_id, None)]
        visited = {origin_id}
        while queue:
            location_id, first_step = queue.pop(0)
            for connection in LOCATION_CONNECTIONS.get(location_id, ()):
                target_id = connection["target"]
                if target_id in visited:
                    continue
                step = target_id if first_step is None else first_step
                if target_id == destination_id:
                    return step
                visited.add(target_id)
                queue.append((target_id, step))
        return None

    def _location_route_position(self, current_location, target_location):
        state = self.quest_journal.quest_system.game_state
        if current_location == "player_farm" and target_location == "player_house_interior":
            return state.flag("player_farm.exterior_spawn", None)
        first_step = self._first_location_step(current_location, target_location)
        if first_step is None:
            return None
        connections = LOCATION_CONNECTIONS.get(current_location, ())
        connection = next(
            (item for item in connections if item["target"] == first_step),
            None,
        )
        if connection is None:
            return None
        base = pygame.Vector2(
            state.flag(
                f"location.{current_location}.spawn",
                state.flag("player_farm.exterior_spawn", self.player.center),
            )
        )
        index = connections.index(connection)
        offset = pygame.Vector2(
            connection.get("offset", ((index * 2 - len(connections) + 1) * 128, -112))
        )
        return tuple(base + offset)

    def _needed_villager_positions(self, npc_manager, world=None):
        if npc_manager is None or self.quest_journal is None:
            return ()
        quest_system = self.quest_journal.quest_system
        wanted_ids = self._needed_villager_ids()
        location_id = getattr(quest_system.game_state, "current_location_id", "player_farm")
        positions = []
        seen = set()
        for npc in getattr(npc_manager, "npcs", ()):
            story_id = getattr(npc, "story_id", None)
            if (
                story_id not in wanted_ids
                or story_id in seen
                or not getattr(npc, "is_alive", True)
                or getattr(npc, "location_id", "player_farm") != location_id
            ):
                continue
            position = getattr(npc, "center", getattr(getattr(npc, "rect", None), "center", None))
            if position is not None:
                positions.append(position)
                seen.add(story_id)
        for story_id in sorted(wanted_ids - seen):
            target_location = quest_system.game_state.story_npcs.get(story_id, {}).get(
                "location_id",
                STORY_NPC_PLACEMENTS.get(story_id, {}).get("location_id"),
            )
            route_position = self._location_route_position(location_id, target_location)
            if route_position is not None and route_position not in positions:
                positions.append(route_position)
        return tuple(positions)

    def _house_positions(self, world):
        positions = []
        if world is None:
            return positions

        for chunk in world.loaded_chunks.values():
            for record in chunk.props:
                if not (isinstance(record, dict) and record.get("type") == "house"):
                    continue
                if record.get("scene") == "farmstead":
                    continue

                world_pos = record.get("world_pos")
                if not world_pos:
                    continue

                render_size = record.get("render_size")
                if render_size:
                    positions.append((
                        world_pos[0] + render_size[0] // 2,
                        world_pos[1] + render_size[1] // 2,
                    ))
                else:
                    footprint = record.get("footprint", (1, 1))
                    positions.append((
                        world_pos[0] + (footprint[0] * world.tile_size) // 2,
                        world_pos[1] + (footprint[1] * world.tile_size) // 2,
                    ))
        return positions

    @staticmethod
    def _farmstead_positions(world):
        """Return farm markers, including guaranteed farms not loaded yet."""
        positions = []
        chunk_width, chunk_height = world.chunk_size
        farmstead_coords = list(getattr(world, "farmstead_chunks", ()))
        known_coords = set(farmstead_coords)
        for chunk_coord, chunk in world.loaded_chunks.items():
            if chunk_coord in known_coords:
                continue
            if any(
                isinstance(record, dict)
                and record.get("type") == "house"
                and record.get("scene") == "farmstead"
                for record in chunk.props
            ):
                farmstead_coords.append(chunk_coord)
                known_coords.add(chunk_coord)

        for chunk_coord in farmstead_coords:
            chunk = world.loaded_chunks.get(chunk_coord)
            pen = None
            if chunk is not None:
                pen = next(
                    (
                        record
                        for record in chunk.props
                        if isinstance(record, dict)
                        and record.get("type") == "animal_pen"
                    ),
                    None,
                )
            if pen is not None:
                left, top, width, height = pen["local_rect"]
                world_tile_x = chunk.origin_tile[0] + left + width / 2
                world_tile_y = chunk.origin_tile[1] + top + height / 2
            else:
                world_tile_x = chunk_coord[0] * chunk_width + chunk_width / 2
                world_tile_y = chunk_coord[1] * chunk_height + chunk_height / 2
            positions.append((
                world_tile_x * world.tile_size,
                world_tile_y * world.tile_size,
            ))
        return positions

    def draw_minimap(self, world, npc_manager=None):
        if world is None:
            return

        rect = self._minimap_rect()
        cache_key = (
            id(world),
            rect.size,
            tuple(sorted(world.loaded_chunks)),
        )
        if cache_key != getattr(self, "_minimap_cache_key", None):
            map_surface = pygame.Surface(rect.size, pygame.SRCALPHA)
            map_surface.fill((8, 14, 22, 218))

            min_x, min_y, max_x, max_y = self._minimap_tile_bounds(world)
            total_tiles_w = max(1, max_x - min_x)
            total_tiles_h = max(1, max_y - min_y)

            for chunk in world.loaded_chunks.values():
                chunk_w, chunk_h = chunk.chunk_size
                for local_y in range(chunk_h):
                    for local_x in range(chunk_w):
                        idx = chunk.get_index(local_x, local_y)
                        terrain = chunk.layers["terrain"][idx]
                        if terrain == -1:
                            continue

                        world_tile_x, world_tile_y = chunk.get_world_tile(local_x, local_y)
                        px = int(((world_tile_x - min_x) / total_tiles_w) * rect.width)
                        py = int(((world_tile_y - min_y) / total_tiles_h) * rect.height)
                        next_px = int(((world_tile_x + 1 - min_x) / total_tiles_w) * rect.width)
                        next_py = int(((world_tile_y + 1 - min_y) / total_tiles_h) * rect.height)
                        tile_rect = pygame.Rect(
                            px,
                            py,
                            max(1, next_px - px),
                            max(1, next_py - py),
                        )
                        color = (215, 194, 118) if terrain == 0 else (75, 140, 78)
                        pygame.draw.rect(map_surface, color, tile_rect)
            self._minimap_cache_key = cache_key
            self._minimap_cache_surface = map_surface
        else:
            map_surface = self._minimap_cache_surface

        pygame.draw.rect(self.screen, (7, 10, 16, 180), rect.move(0, 3), border_radius=8)
        pygame.draw.rect(self.screen, (18, 26, 38), rect.inflate(8, 8), border_radius=8)
        pygame.draw.rect(self.screen, (76, 145, 201), rect.inflate(8, 8), 2, border_radius=8)
        self.screen.blit(map_surface, rect)

        player_pos = self._minimap_point(world, rect, self.player.center)
        pygame.draw.circle(self.screen, (70, 235, 105), player_pos, 4)
        pygame.draw.circle(self.screen, (7, 10, 16), player_pos, 5, 1)

        home_pos = self._home_position(world)
        if home_pos is not None:
            marker_pos = self._minimap_point(world, rect, home_pos)
            home = self.small_font.render("H", True, HOME_MARKER_COLOR)
            self.screen.blit(home, home.get_rect(center=marker_pos))

        for villager_pos in self._needed_villager_positions(npc_manager, world):
            marker_pos = self._minimap_point(world, rect, villager_pos)
            pygame.draw.circle(self.screen, (7, 10, 16), marker_pos, 6)
            marker = self.small_font.render("!", True, QUEST_MARKER_COLOR)
            self.screen.blit(marker, marker.get_rect(center=(marker_pos[0], marker_pos[1] - 1)))

        for enemy_pos in self._enemy_positions(npc_manager):
            dot_pos = self._minimap_point(world, rect, enemy_pos)
            pygame.draw.circle(self.screen, (230, 60, 65), dot_pos, 3)

        label = self.small_font.render(world.level_name, True, (236, 240, 245))
        self.screen.blit(label, label.get_rect(topleft=(rect.x + 8, rect.y + 6)))

    def _important_npc_targets(self, world, npc_manager):
        """Return nearby-priority authored NPCs with their world distances."""
        if world is None or npc_manager is None:
            return []
        preferred_ids = self._needed_villager_ids()
        targets = []
        seen = set()
        player_pos = pygame.Vector2(self.player.center)
        for npc in getattr(npc_manager, "npcs", ()):
            story_id = getattr(npc, "story_id", None)
            if story_id not in STORY_NPC_PLACEMENTS or story_id in seen:
                continue
            if preferred_ids and story_id not in preferred_ids:
                continue
            if not getattr(npc, "is_alive", True):
                continue
            location_id = getattr(npc, "location_id", "player_farm")
            if LOCATION_DEFINITIONS.get(location_id, {}).get("runtime", "world") != "world":
                continue
            position = getattr(npc, "center", getattr(getattr(npc, "rect", None), "center", None))
            if position is None:
                continue
            distance = player_pos.distance_to(position)
            targets.append((story_id, STORY_NPC_PLACEMENTS[story_id]["name"], position, distance))
            seen.add(story_id)

        if preferred_ids and self.quest_journal is not None:
            state = self.quest_journal.quest_system.game_state
            current_location = state.current_location_id
            for story_id in sorted(preferred_ids - seen):
                placement = STORY_NPC_PLACEMENTS.get(story_id)
                if placement is None:
                    continue
                target_location = state.story_npcs.get(story_id, {}).get(
                    "location_id", placement.get("location_id")
                )
                position = self._location_route_position(current_location, target_location)
                if position is None:
                    continue
                distance = player_pos.distance_to(position)
                targets.append((story_id, placement["name"], position, distance))

        return sorted(targets, key=lambda target: (target[3], target[0]))

    def draw_important_npc_markers(self, world, npc_manager):
        """Draw direction arrows and tile distances for up to three off-screen NPCs."""
        if world is None:
            return ()
        player_pos = pygame.Vector2(self.player.center)
        screen_center = pygame.Vector2(self.screen_w / 2, self.screen_h / 2)
        half_w = max(80, self.screen_w / 2 - 78)
        half_h = max(70, self.screen_h / 2 - 70)
        drawn = []

        for story_id, name, position, distance in self._important_npc_targets(world, npc_manager):
            delta = pygame.Vector2(position) - player_pos
            if delta.length_squared() < 1:
                continue
            if abs(delta.x) <= half_w and abs(delta.y) <= half_h:
                continue
            direction = delta.normalize()
            edge_scale = min(
                half_w / max(abs(direction.x), 0.0001),
                half_h / max(abs(direction.y), 0.0001),
            )
            marker = screen_center + direction * edge_scale
            marker.x = max(54, min(self.screen_w - 54, marker.x))
            marker.y = max(42, min(self.screen_h - 42, marker.y))

            perpendicular = pygame.Vector2(-direction.y, direction.x)
            tip = marker + direction * 11
            back = marker - direction * 8
            points = (tip, back + perpendicular * 7, back - perpendicular * 7)
            pygame.draw.polygon(self.screen, (255, 214, 76), points)
            pygame.draw.polygon(self.screen, (20, 24, 30), points, 2)

            tile_distance = max(1, round(distance / max(1, world.tile_size)))
            text = self.small_font.render(f"{name}  {tile_distance} tiles", True, (247, 242, 215))
            label = text.get_rect(center=(round(marker.x), round(marker.y + 22)))
            label.clamp_ip(self.screen.get_rect().inflate(-8, -8))
            panel = label.inflate(12, 7)
            pygame.draw.rect(self.screen, (12, 18, 26, 225), panel, border_radius=6)
            pygame.draw.rect(self.screen, (255, 214, 76), panel, 1, border_radius=6)
            self.screen.blit(text, label)
            drawn.append((story_id, tile_distance, (round(marker.x), round(marker.y))))
            if len(drawn) >= 3:
                break
        return tuple(drawn)

    def draw(self, world=None, npc_manager=None, weather=None):
        self.hotbar_ui.display_hot_bar()
        self.hotbar_ui.select_slot(self.get_selected_hotbar_index())
        self.draw_health_panel()
        self.draw_stamina_panel()
        self.draw_experience_and_trust(npc_manager)
        self.draw_coin_panel()
        self.draw_weather_panel(weather)
        self.draw_progression_panel()
        self.draw_minimap(world, npc_manager)
        self.draw_important_npc_markers(world, npc_manager)
        self.draw_selected_overlay()
        if self.quest_journal is not None:
            self.quest_journal.draw_tracked()

        if self.player.inventory.is_inv:
            self.inventory_ui.display_inventory()
            if self.inventory_ui.grabbing:
                self.inventory_ui.grab_item()
        self.draw_death_panel()
        self.draw_notification()
        if self.quest_journal is not None:
            self.quest_journal.draw()

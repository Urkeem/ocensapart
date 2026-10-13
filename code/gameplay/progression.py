"""Progression mutations driven entirely by completed domain events."""

from __future__ import annotations

from gameplay.events import (
    CropHarvested,
    EnemyDefeated,
    EquipmentUpgraded,
    EventDispatcher,
    FishCaught,
    GiftGiven,
    ItemCrafted,
    NpcRescued,
    ProgressionGranted,
    ProgressionUpdated,
)
from gameplay.game_state import GameState
from gameplay.fishing import (
    FISH_BY_ID,
    LOCALITY_UNLOCK_POINTS,
    fish_species,
    is_fish_unlocked,
    is_locality_unlocked,
)
from data.crops import CROP_DEFINITIONS, crop_definition, is_crop_unlocked


ENEMY_XP_BY_TIER = {"primary": 10, "secondary": 25, "tertiary": 50, "boss": 100}
GIFT_TRUST = {"disliked": 0, "normal": 2, "liked": 4, "favorite": 8}
CRAFT_XP = 5
UPGRADE_XP = 20


def synchronize_progression_unlocks(game_state: GameState) -> tuple[str, ...]:
    """Materialize threshold unlocks for persistence and other game systems."""
    unlocked = []
    for crop in CROP_DEFINITIONS.values():
        if is_crop_unlocked(crop.id, game_state) and game_state.unlock(crop.unlock_id):
            unlocked.append(crop.unlock_id)
    for locality in LOCALITY_UNLOCK_POINTS:
        if is_locality_unlocked(locality, game_state):
            unlock_id = f"fishing.locality.{locality}"
            if game_state.unlock(unlock_id):
                unlocked.append(unlock_id)
    for fish in FISH_BY_ID.values():
        if is_fish_unlocked(fish, game_state) and game_state.unlock(fish.unlock_id):
            unlocked.append(fish.unlock_id)
    return tuple(unlocked)


class ProgressionService:
    consumer_id = "progression"

    def __init__(self, game_state: GameState, dispatcher: EventDispatcher | None = None):
        self.game_state = game_state
        synchronize_progression_unlocks(game_state)
        self.dispatcher = None
        self._unsubscribe = []
        if dispatcher is not None:
            self.bind(dispatcher)

    def bind(self, dispatcher: EventDispatcher):
        self.close()
        self.dispatcher = dispatcher
        handlers = {
            CropHarvested: self.on_crop_harvested,
            FishCaught: self.on_fish_caught,
            EnemyDefeated: self.on_enemy_defeated,
            ItemCrafted: self.on_item_crafted,
            EquipmentUpgraded: self.on_equipment_upgraded,
            GiftGiven: self.on_gift_given,
            NpcRescued: self.on_npc_rescued,
            ProgressionGranted: self.on_progression_granted,
        }
        self._unsubscribe = [
            dispatcher.subscribe(event_type, handler)
            for event_type, handler in handlers.items()
        ]
        return self

    def close(self):
        for unsubscribe in self._unsubscribe:
            unsubscribe()
        self._unsubscribe = []
        self.dispatcher = None

    def _claim(self, event) -> bool:
        return self.game_state.claim_event(self.consumer_id, event.event_id)

    def _publish_progress(self, event, track, amount, total, unlocks):
        if self.dispatcher is None or amount <= 0:
            return
        self.dispatcher.publish(
            ProgressionUpdated(
                event_id=f"{event.event_id}:progression:{track}",
                track=track,
                amount=amount,
                total=total,
                source_id=getattr(event, "crop_id", None)
                or getattr(event, "fish_id", None)
                or getattr(event, "enemy_id", None)
                or getattr(event, "npc_id", None)
                or getattr(event, "source_id", "progression"),
                unlocked_ids=tuple(unlocks),
            )
        )

    def on_crop_harvested(self, event: CropHarvested):
        if not self._claim(event):
            return False
        crop = crop_definition(event.crop_id)
        points = (crop.harvest_points if crop is not None else 1) * max(1, int(event.count))
        previous_unlocks = set(self.game_state.progression.unlocks)
        total = self.game_state.add_farming_points(points)
        unlocks = tuple(
            unlock_id
            for unlock_id in synchronize_progression_unlocks(self.game_state)
            if unlock_id not in previous_unlocks
        )
        self._publish_progress(event, "farming", points, total, unlocks)
        return points

    def on_fish_caught(self, event: FishCaught):
        if not self._claim(event):
            return False
        species = fish_species(event.fish_id)
        per_fish = event.point_reward
        if per_fish is None:
            per_fish = species.point_reward if species is not None else max(1, int(event.required_reels))
        points = max(1, int(per_fish)) * max(1, int(event.count))
        previous_unlocks = set(self.game_state.progression.unlocks)
        total = self.game_state.add_fishing_points(points)
        unlocks = tuple(
            unlock_id
            for unlock_id in synchronize_progression_unlocks(self.game_state)
            if unlock_id not in previous_unlocks
        )
        self._publish_progress(event, "fishing", points, total, unlocks)
        return points

    def on_enemy_defeated(self, event: EnemyDefeated):
        if not self._claim(event):
            return False
        amount = event.xp_reward
        if amount is None:
            amount = ENEMY_XP_BY_TIER.get(event.tier, ENEMY_XP_BY_TIER["primary"])
        previous_level = self.game_state.progression.level
        self.game_state.add_experience(amount)
        new_level = self.game_state.progression.level
        level_unlocks = tuple(
            f"level.{level}"
            for level in range(previous_level + 1, new_level + 1)
        )
        self._publish_progress(
            event,
            "experience",
            amount,
            self.game_state.progression.experience,
            level_unlocks,
        )
        return amount

    def on_item_crafted(self, event: ItemCrafted):
        if not self._claim(event):
            return False
        amount = event.xp_reward if event.xp_reward is not None else CRAFT_XP * max(1, int(event.count))
        previous_level = self.game_state.progression.level
        self.game_state.add_experience(amount)
        self._publish_progress(
            event,
            "experience",
            amount,
            self.game_state.progression.experience,
            tuple(f"level.{level}" for level in range(previous_level + 1, self.game_state.progression.level + 1)),
        )
        return amount

    def on_equipment_upgraded(self, event: EquipmentUpgraded):
        if not self._claim(event):
            return False
        amount = event.xp_reward if event.xp_reward is not None else UPGRADE_XP
        previous_level = self.game_state.progression.level
        self.game_state.add_experience(amount)
        self._publish_progress(
            event,
            "experience",
            amount,
            self.game_state.progression.experience,
            tuple(f"level.{level}" for level in range(previous_level + 1, self.game_state.progression.level + 1)),
        )
        return amount

    def on_gift_given(self, event: GiftGiven):
        if not self._claim(event):
            return False
        relationship = self.game_state.relationship(event.npc_id)
        amount = event.trust_reward
        if amount is None:
            amount = GIFT_TRUST.get(event.preference, GIFT_TRUST["normal"])
        if event.day is not None:
            prior_gifts = relationship.gifts_by_day.get(event.day, 0)
            relationship.gifts_by_day[event.day] = prior_gifts + 1
            if prior_gifts:
                amount = amount // 4
        self.game_state.add_trust(event.npc_id, amount)
        self._publish_progress(event, "trust", amount, relationship.trust, ())
        return amount

    def on_npc_rescued(self, event: NpcRescued):
        if not self._claim(event):
            return False
        self.game_state.add_trust(event.npc_id, event.trust_reward)
        self.game_state.add_kingdom_reputation(event.reputation_reward)
        self._publish_progress(
            event, "trust", event.trust_reward, self.game_state.relationship(event.npc_id).trust, ()
        )
        self._publish_progress(
            event, "kingdom_reputation", event.reputation_reward, self.game_state.progression.kingdom_reputation, ()
        )
        return event.trust_reward, event.reputation_reward

    def on_progression_granted(self, event: ProgressionGranted):
        if not self._claim(event):
            return False
        previous_level = self.game_state.progression.level
        self.game_state.add_experience(event.experience)
        self._publish_progress(
            event,
            "experience",
            max(0, int(event.experience)),
            self.game_state.progression.experience,
            tuple(f"level.{level}" for level in range(previous_level + 1, self.game_state.progression.level + 1)),
        )
        previous_unlocks = set(self.game_state.progression.unlocks)
        farming_total = self.game_state.add_farming_points(event.farming_points)
        farming_unlocks = synchronize_progression_unlocks(self.game_state)
        self._publish_progress(
            event,
            "farming",
            max(0, int(event.farming_points)),
            farming_total,
            tuple(item for item in farming_unlocks if item not in previous_unlocks),
        )
        previous_unlocks = set(self.game_state.progression.unlocks)
        fishing_total = self.game_state.add_fishing_points(event.fishing_points)
        fishing_unlocks = synchronize_progression_unlocks(self.game_state)
        self._publish_progress(
            event,
            "fishing",
            max(0, int(event.fishing_points)),
            fishing_total,
            tuple(item for item in fishing_unlocks if item not in previous_unlocks),
        )
        self.game_state.add_kingdom_reputation(event.kingdom_reputation)
        self._publish_progress(
            event,
            "kingdom_reputation",
            max(0, int(event.kingdom_reputation)),
            self.game_state.progression.kingdom_reputation,
            (),
        )
        if event.trust_npc_id and event.trust:
            self.game_state.add_trust(event.trust_npc_id, event.trust)
            self._publish_progress(
                event,
                "trust",
                max(0, int(event.trust)),
                self.game_state.relationship(event.trust_npc_id).trust,
                (),
            )
        return True

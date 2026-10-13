"""Typed domain events and a small synchronous dispatcher."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Callable, TypeVar
from uuid import uuid4


@dataclass(frozen=True, kw_only=True)
class DomainEvent:
    """A completed gameplay fact with an ID suitable for deduplication."""

    event_id: str


@dataclass(frozen=True, kw_only=True)
class CropWatered(DomainEvent):
    crop_id: str | None
    location_id: str
    world_tile: tuple[int, int] | None = None


@dataclass(frozen=True, kw_only=True)
class CropHarvested(DomainEvent):
    crop_id: str
    count: int = 1
    location_id: str = "player_farm"
    world_tile: tuple[int, int] | None = None


@dataclass(frozen=True, kw_only=True)
class FishCaught(DomainEvent):
    fish_id: str
    locality: str
    required_reels: int
    count: int = 1
    point_reward: int | None = None


@dataclass(frozen=True, kw_only=True)
class ProgressionUpdated(DomainEvent):
    track: str
    amount: int
    total: int
    source_id: str
    unlocked_ids: tuple[str, ...] = ()


@dataclass(frozen=True, kw_only=True)
class EnemyDefeated(DomainEvent):
    enemy_id: str
    tier: str
    encounter_id: str | None = None
    xp_reward: int | None = None


@dataclass(frozen=True, kw_only=True)
class EnemyLootGranted(DomainEvent):
    enemy_id: str
    enemy_instance_id: str
    item_id: str
    count: int
    encounter_id: str | None = None


@dataclass(frozen=True, kw_only=True)
class EncounterWaveCompleted(DomainEvent):
    encounter_id: str
    wave: int
    count: int = 1


@dataclass(frozen=True, kw_only=True)
class EncounterCompleted(DomainEvent):
    encounter_id: str
    waves_completed: int
    count: int = 1


@dataclass(frozen=True, kw_only=True)
class EncounterFailed(DomainEvent):
    encounter_id: str
    attempt: int


@dataclass(frozen=True, kw_only=True)
class ItemCrafted(DomainEvent):
    item_id: str
    recipe_id: str
    count: int = 1
    xp_reward: int | None = None


@dataclass(frozen=True, kw_only=True)
class EquipmentUpgraded(DomainEvent):
    equipment_id: str
    old_tier: str
    new_tier: str
    xp_reward: int | None = None


@dataclass(frozen=True, kw_only=True)
class GiftGiven(DomainEvent):
    npc_id: str
    item_id: str
    preference: str = "normal"
    trust_reward: int | None = None
    day: int | None = None


@dataclass(frozen=True, kw_only=True)
class DialogueCompleted(DomainEvent):
    npc_id: str
    node_id: str


@dataclass(frozen=True, kw_only=True)
class LocationEntered(DomainEvent):
    location_id: str


@dataclass(frozen=True, kw_only=True)
class VesselMounted(DomainEvent):
    vessel_id: str


@dataclass(frozen=True, kw_only=True)
class VesselDocked(DomainEvent):
    vessel_id: str
    location_id: str


@dataclass(frozen=True, kw_only=True)
class SurvivorStageChanged(DomainEvent):
    group_id: str
    old_stage: str
    new_stage: str


@dataclass(frozen=True, kw_only=True)
class ResourceDestroyed(DomainEvent):
    resource_id: str
    resource_type: str


@dataclass(frozen=True, kw_only=True)
class NpcRescued(DomainEvent):
    npc_id: str
    encounter_id: str
    trust_reward: int = 10
    reputation_reward: int = 5


@dataclass(frozen=True, kw_only=True)
class PlayerSlept(DomainEvent):
    day: int


@dataclass(frozen=True, kw_only=True)
class PlayerCollapsed(DomainEvent):
    reason: str


@dataclass(frozen=True, kw_only=True)
class ProgressionGranted(DomainEvent):
    """Data-defined quest or story reward routed through progression APIs."""

    source_id: str
    experience: int = 0
    farming_points: int = 0
    fishing_points: int = 0
    kingdom_reputation: int = 0
    trust_npc_id: str | None = None
    trust: int = 0


@dataclass(frozen=True, kw_only=True)
class QuestStateChanged(DomainEvent):
    quest_id: str
    old_status: str
    new_status: str
    reason: str


@dataclass(frozen=True, kw_only=True)
class DialogueSelected(DomainEvent):
    npc_id: str
    node_id: str


@dataclass(frozen=True, kw_only=True)
class AccessDenied(DomainEvent):
    location_id: str
    reason: str


EventType = TypeVar("EventType", bound=DomainEvent)
EventHandler = Callable[[DomainEvent], object]


class EventDispatcher:
    """Publish completed actions to independent gameplay consumers."""

    def __init__(self):
        self._handlers: dict[type[DomainEvent], list[EventHandler]] = defaultdict(list)

    def subscribe(self, event_type: type[EventType], handler: Callable[[EventType], object]):
        handlers = self._handlers[event_type]
        if handler not in handlers:
            handlers.append(handler)
        return lambda: self.unsubscribe(event_type, handler)

    def unsubscribe(self, event_type: type[EventType], handler: Callable[[EventType], object]):
        handlers = self._handlers.get(event_type)
        if not handlers or handler not in handlers:
            return False
        handlers.remove(handler)
        if not handlers:
            self._handlers.pop(event_type, None)
        return True

    def publish(self, event: DomainEvent) -> tuple[object, ...]:
        if not isinstance(event, DomainEvent):
            raise TypeError("Only DomainEvent instances can be published")
        results = []
        for event_type, handlers in tuple(self._handlers.items()):
            if isinstance(event, event_type):
                results.extend(handler(event) for handler in tuple(handlers))
        return tuple(results)


def next_event_id(source, event_name: str) -> str:
    """Allocate an event ID from persisted state when a runtime owner has it."""
    game_state = getattr(source, "game_state", None)
    if game_state is not None:
        return game_state.next_event_id(event_name)
    return f"{event_name}:{uuid4().hex}"


def publish_from(source, event: DomainEvent) -> tuple[object, ...]:
    dispatcher = getattr(source, "event_dispatcher", None)
    if dispatcher is None:
        return ()
    return dispatcher.publish(event)

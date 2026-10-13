"""Persisted mutable state for story, progression, and authored locations."""

from __future__ import annotations

from dataclasses import dataclass, field
from copy import deepcopy
import re


TRUST_TIER_THRESHOLDS = (
    ("ally", 80),
    ("trusted", 50),
    ("familiar", 25),
    ("guarded", 10),
    ("unknown", 0),
)


def trust_tier_for(points: int) -> str:
    points = max(0, int(points))
    for tier, threshold in TRUST_TIER_THRESHOLDS:
        if points >= threshold:
            return tier
    return "unknown"


def experience_to_reach_level(level: int) -> int:
    """Cumulative XP threshold; level 2 starts at 100 XP."""
    level = max(1, int(level))
    return 50 * level * (level - 1)


def level_for_experience(experience: int) -> int:
    experience = max(0, int(experience))
    level = 1
    while experience >= experience_to_reach_level(level + 1):
        level += 1
    return level


def _clean_id(value: object) -> str:
    return re.sub(r"[^a-z0-9._-]+", "_", str(value).strip().lower()).strip("_")


def stable_encounter_id(location_id: str, encounter_name: str, sequence: int | str = 1) -> str:
    return f"encounter:{_clean_id(location_id)}:{_clean_id(encounter_name)}:{_clean_id(sequence)}"


@dataclass
class ProgressionState:
    experience: int = 0
    level: int = 1
    skill_points: int = 0
    farming_points: int = 0
    fishing_points: int = 0
    kingdom_reputation: int = 0
    unlocks: set[str] = field(default_factory=set)

    def to_dict(self) -> dict:
        return {
            "experience": self.experience,
            "level": self.level,
            "skill_points": self.skill_points,
            "farming_points": self.farming_points,
            "fishing_points": self.fishing_points,
            "kingdom_reputation": self.kingdom_reputation,
            "unlocks": sorted(self.unlocks),
        }

    @classmethod
    def from_dict(cls, data=None) -> "ProgressionState":
        data = data or {}
        experience = max(0, int(data.get("experience", 0)))
        calculated_level = level_for_experience(experience)
        return cls(
            experience=experience,
            level=max(calculated_level, int(data.get("level", calculated_level))),
            skill_points=max(0, int(data.get("skill_points", 0))),
            farming_points=max(0, int(data.get("farming_points", 0))),
            fishing_points=max(0, int(data.get("fishing_points", 0))),
            kingdom_reputation=max(0, int(data.get("kingdom_reputation", 0))),
            unlocks=set(data.get("unlocks", ())),
        )


@dataclass
class RelationshipState:
    trust: int = 0
    tier: str = "unknown"
    favorite_plant_known: bool = False
    gifts_by_day: dict[int, int] = field(default_factory=dict)
    memory: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "trust": self.trust,
            "tier": self.tier,
            "favorite_plant_known": self.favorite_plant_known,
            "gifts_by_day": {str(day): count for day, count in sorted(self.gifts_by_day.items())},
            "memory": dict(self.memory),
        }

    @classmethod
    def from_dict(cls, data=None) -> "RelationshipState":
        data = data or {}
        trust = max(0, int(data.get("trust", 0)))
        return cls(
            trust=trust,
            tier=trust_tier_for(trust),
            favorite_plant_known=bool(data.get("favorite_plant_known", False)),
            gifts_by_day={int(day): max(0, int(count)) for day, count in data.get("gifts_by_day", {}).items()},
            memory=dict(data.get("memory", {})),
        )


@dataclass
class DialogueMemory:
    consumed_nodes: set[str] = field(default_factory=set)
    facts: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"consumed_nodes": sorted(self.consumed_nodes), "facts": dict(self.facts)}

    @classmethod
    def from_dict(cls, data=None) -> "DialogueMemory":
        data = data or {}
        return cls(set(data.get("consumed_nodes", ())), dict(data.get("facts", {})))


@dataclass
class AccessibilityState:
    text_scale: float = 1.0
    high_contrast: bool = False
    reduced_motion: bool = False
    dialogue_speed: str = "normal"

    def to_dict(self):
        return {
            "text_scale": self.text_scale,
            "high_contrast": self.high_contrast,
            "reduced_motion": self.reduced_motion,
            "dialogue_speed": self.dialogue_speed,
        }

    @classmethod
    def from_dict(cls, data=None):
        data = data or {}
        speed = str(data.get("dialogue_speed", "normal"))
        if speed not in {"normal", "fast", "instant"}:
            speed = "normal"
        return cls(
            text_scale=min(1.5, max(1.0, float(data.get("text_scale", 1.0)))),
            high_contrast=bool(data.get("high_contrast", False)),
            reduced_motion=bool(data.get("reduced_motion", False)),
            dialogue_speed=speed,
        )


@dataclass
class GameState:
    progression: ProgressionState = field(default_factory=ProgressionState)
    flags: dict[str, object] = field(default_factory=dict)
    quests: dict[str, dict] = field(default_factory=dict)
    tracked_quest_id: str | None = None
    dialogue: DialogueMemory = field(default_factory=DialogueMemory)
    relationships: dict[str, RelationshipState] = field(default_factory=dict)
    stamina: float = 100.0
    max_stamina: float = 100.0
    awake_game_minutes: float = 0.0
    current_location_id: str = "player_farm"
    location_return_points: dict[str, tuple[float, float] | list[float]] = field(default_factory=dict)
    home_id: str = "farmhouse"
    story_npcs: dict[str, dict] = field(default_factory=dict)
    encounters: dict[str, dict] = field(default_factory=dict)
    transports: dict[str, dict] = field(default_factory=dict)
    survivor_groups: dict[str, dict] = field(default_factory=dict)
    event_receipts: dict[str, set[str]] = field(default_factory=dict)
    event_counters: dict[str, int] = field(default_factory=dict)
    accessibility: AccessibilityState = field(default_factory=AccessibilityState)

    def relationship(self, npc_id: str) -> RelationshipState:
        npc_id = _clean_id(npc_id)
        if npc_id not in self.relationships:
            self.relationships[npc_id] = RelationshipState()
        return self.relationships[npc_id]

    def set_flag(self, flag_id: str, value: object = True) -> object:
        self.flags[str(flag_id)] = value
        return value

    def flag(self, flag_id: str, default=None):
        return self.flags.get(str(flag_id), default)

    def remember_dialogue_node(self, node_id: str) -> bool:
        node_id = str(node_id)
        if node_id in self.dialogue.consumed_nodes:
            return False
        self.dialogue.consumed_nodes.add(node_id)
        return True

    def set_dialogue_fact(self, fact_id: str, value: object = True) -> object:
        self.dialogue.facts[str(fact_id)] = value
        return value

    def set_location(self, location_id: str) -> str:
        self.current_location_id = _clean_id(location_id)
        return self.current_location_id

    def set_story_npc_state(self, npc_id: str, **changes) -> dict:
        record = self.story_npcs.setdefault(_clean_id(npc_id), {})
        record.update(changes)
        return record

    def add_experience(self, amount: int) -> int:
        amount = max(0, int(amount))
        previous_level = self.progression.level
        self.progression.experience += amount
        self.progression.level = level_for_experience(self.progression.experience)
        gained_levels = max(0, self.progression.level - previous_level)
        self.progression.skill_points += gained_levels
        return gained_levels

    def add_farming_points(self, amount: int) -> int:
        amount = max(0, int(amount))
        self.progression.farming_points += amount
        return self.progression.farming_points

    def add_fishing_points(self, amount: int) -> int:
        amount = max(0, int(amount))
        self.progression.fishing_points += amount
        return self.progression.fishing_points

    def add_kingdom_reputation(self, amount: int) -> int:
        amount = max(0, int(amount))
        self.progression.kingdom_reputation += amount
        return self.progression.kingdom_reputation

    def add_trust(self, npc_id: str, amount: int) -> tuple[str, str]:
        relationship = self.relationship(npc_id)
        previous_tier = relationship.tier
        relationship.trust += max(0, int(amount))
        relationship.tier = trust_tier_for(relationship.trust)
        return previous_tier, relationship.tier

    def unlock(self, unlock_id: str) -> bool:
        unlock_id = _clean_id(unlock_id)
        if unlock_id in self.progression.unlocks:
            return False
        self.progression.unlocks.add(unlock_id)
        return True

    def claim_event(self, consumer_id: str, event_id: str) -> bool:
        if not event_id:
            raise ValueError("Domain events require a non-empty event_id")
        receipts = self.event_receipts.setdefault(_clean_id(consumer_id), set())
        if event_id in receipts:
            return False
        receipts.add(event_id)
        return True

    def next_event_id(self, event_name: str) -> str:
        event_name = _clean_id(event_name)
        next_value = self.event_counters.get(event_name, 0) + 1
        self.event_counters[event_name] = next_value
        return f"{event_name}:{next_value}"

    def register_encounter(self, location_id: str, encounter_name: str, sequence=1, **state) -> str:
        encounter_id = stable_encounter_id(location_id, encounter_name, sequence)
        record = self.encounters.setdefault(encounter_id, {})
        record.update(state)
        record.setdefault("completed", False)
        return encounter_id

    def update_encounter(self, encounter_id: str, **changes) -> dict:
        if encounter_id not in self.encounters:
            raise KeyError(f"Unknown encounter {encounter_id!r}")
        self.encounters[encounter_id].update(changes)
        return self.encounters[encounter_id]

    def to_dict(self) -> dict:
        return {
            "progression": self.progression.to_dict(),
            "flags": deepcopy(self.flags),
            "quests": deepcopy(self.quests),
            "tracked_quest_id": self.tracked_quest_id,
            "dialogue": self.dialogue.to_dict(),
            "relationships": {
                npc_id: state.to_dict()
                for npc_id, state in sorted(self.relationships.items())
            },
            "stamina": self.stamina,
            "max_stamina": self.max_stamina,
            "awake_game_minutes": self.awake_game_minutes,
            "current_location_id": self.current_location_id,
            "location_return_points": deepcopy(self.location_return_points),
            "home_id": self.home_id,
            "story_npcs": {npc_id: dict(state) for npc_id, state in self.story_npcs.items()},
            "encounters": deepcopy(self.encounters),
            "transports": deepcopy(self.transports),
            "survivor_groups": deepcopy(self.survivor_groups),
            "event_receipts": {
                consumer: sorted(receipts)
                for consumer, receipts in sorted(self.event_receipts.items())
            },
            "event_counters": dict(self.event_counters),
            "accessibility": self.accessibility.to_dict(),
        }

    @classmethod
    def from_dict(cls, data=None) -> "GameState":
        data = data or {}
        max_stamina = max(1.0, float(data.get("max_stamina", 100.0)))
        return cls(
            progression=ProgressionState.from_dict(data.get("progression")),
            flags=deepcopy(data.get("flags", {})),
            quests=deepcopy(data.get("quests", {})),
            tracked_quest_id=data.get("tracked_quest_id"),
            dialogue=DialogueMemory.from_dict(data.get("dialogue")),
            relationships={
                npc_id: RelationshipState.from_dict(state)
                for npc_id, state in data.get("relationships", {}).items()
            },
            stamina=max(0.0, min(max_stamina, float(data.get("stamina", max_stamina)))),
            max_stamina=max_stamina,
            awake_game_minutes=max(0.0, float(data.get("awake_game_minutes", 0.0))),
            current_location_id=str(data.get("current_location_id", "player_farm")),
            location_return_points=deepcopy(data.get("location_return_points", {})),
            home_id=str(data.get("home_id", "farmhouse")),
            story_npcs={npc_id: dict(state) for npc_id, state in data.get("story_npcs", {}).items()},
            encounters=deepcopy(data.get("encounters", {})),
            transports=deepcopy(data.get("transports", {})),
            survivor_groups=deepcopy(data.get("survivor_groups", {})),
            event_receipts={
                consumer: set(receipts)
                for consumer, receipts in data.get("event_receipts", {}).items()
            },
            event_counters={name: max(0, int(value)) for name, value in data.get("event_counters", {}).items()},
            accessibility=AccessibilityState.from_dict(data.get("accessibility")),
        )

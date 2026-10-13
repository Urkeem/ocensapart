"""Data-defined quest runtime driven by domain events."""

from __future__ import annotations

from copy import deepcopy

from data.quests import QUEST_DEFINITIONS
from gameplay.events import DomainEvent, EventDispatcher, ProgressionGranted, QuestStateChanged
from gameplay.game_state import GameState
from inventory_item import Item


LOCKED = "locked"
AVAILABLE = "available"
ACTIVE = "active"
READY_TO_TURN_IN = "ready_to_turn_in"
COMPLETED = "completed"


class QuestSystem:
    """Own quest transitions while persisting all mutable state in GameState."""

    def __init__(
        self,
        game_state: GameState,
        dispatcher: EventDispatcher | None = None,
        definitions=None,
        player=None,
    ):
        self.game_state = game_state
        self.definitions = definitions or QUEST_DEFINITIONS
        self.player = player
        self.dispatcher = None
        self._unsubscribe = None
        self._initialize_states()
        if dispatcher is not None:
            self.bind(dispatcher)

    def _initialize_states(self):
        for quest_id, definition in self.definitions.items():
            state = self.game_state.quests.setdefault(
                quest_id,
                {
                    "status": LOCKED,
                    "objectives": {},
                    "reward_claimed": False,
                },
            )
            state.setdefault("status", LOCKED)
            state.setdefault("objectives", {})
            state.setdefault("reward_claimed", False)
            for objective in definition.get("objectives", ()):
                state["objectives"].setdefault(objective["id"], 0)
        self.refresh_availability()

    def bind(self, dispatcher: EventDispatcher):
        self.close()
        self.dispatcher = dispatcher
        self._unsubscribe = dispatcher.subscribe(DomainEvent, self.on_event)
        return self

    def close(self):
        if self._unsubscribe is not None:
            self._unsubscribe()
        self._unsubscribe = None
        self.dispatcher = None

    def _transition(self, quest_id, new_status, reason):
        state = self.game_state.quests[quest_id]
        old_status = state["status"]
        if old_status == new_status:
            return False
        state["status"] = new_status
        if self.dispatcher is not None:
            self.dispatcher.publish(
                QuestStateChanged(
                    event_id=self.game_state.next_event_id("quest_state"),
                    quest_id=quest_id,
                    old_status=old_status,
                    new_status=new_status,
                    reason=str(reason),
                )
            )
        return True

    def get_definition(self, quest_id: str) -> dict:
        try:
            return self.definitions[quest_id]
        except KeyError as error:
            raise KeyError(f"Unknown quest {quest_id!r}") from error

    def get_state(self, quest_id: str) -> dict:
        self.get_definition(quest_id)
        return self.game_state.quests[quest_id]

    def status(self, quest_id: str) -> str:
        return self.get_state(quest_id)["status"]

    def _prerequisite_met(self, requirement) -> bool:
        if isinstance(requirement, str):
            return self.status(requirement) == COMPLETED
        requirement_type = requirement.get("type")
        if requirement_type == "quest":
            return self.status(requirement["quest_id"]) == requirement.get("status", COMPLETED)
        if requirement_type == "flag":
            return self.game_state.flag(requirement["flag"]) == requirement.get("value", True)
        if requirement_type == "trust":
            return self.game_state.relationship(requirement["npc_id"]).trust >= int(requirement["minimum"])
        return False

    def refresh_availability(self):
        changed = []
        for quest_id, definition in self.definitions.items():
            state = self.game_state.quests[quest_id]
            if state["status"] != LOCKED:
                continue
            if all(self._prerequisite_met(item) for item in definition.get("prerequisites", ())):
                self._transition(quest_id, AVAILABLE, "prerequisites_met")
                changed.append(quest_id)
        return tuple(changed)

    def start(self, quest_id: str) -> bool:
        state = self.get_state(quest_id)
        if state["status"] != AVAILABLE:
            return False
        self._transition(quest_id, ACTIVE, "accepted")
        state["started"] = True
        self.game_state.tracked_quest_id = quest_id
        self._apply_actions(self.get_definition(quest_id).get("start_actions", ()), quest_id)
        if self._objectives_complete(quest_id):
            self._transition(quest_id, READY_TO_TURN_IN, "objectives_complete")
        return True

    def track(self, quest_id: str | None) -> bool:
        if quest_id is None:
            self.game_state.tracked_quest_id = None
            return True
        if self.status(quest_id) not in (ACTIVE, READY_TO_TURN_IN):
            return False
        self.game_state.tracked_quest_id = quest_id
        return True

    def _event_matches(self, event: DomainEvent, objective: dict) -> bool:
        if type(event).__name__ != objective.get("event"):
            return False
        for field, wanted in objective.get("filters", {}).items():
            actual = getattr(event, field, None)
            if isinstance(wanted, (tuple, list, set, frozenset)):
                if actual not in wanted:
                    return False
            elif actual != wanted:
                return False
        return True

    @staticmethod
    def _event_amount(event: DomainEvent) -> int:
        return max(1, int(getattr(event, "count", 1)))

    def on_event(self, event: DomainEvent):
        changes = []
        for quest_id, definition in self.definitions.items():
            state = self.game_state.quests[quest_id]
            if state["status"] != ACTIVE:
                continue
            for objective in definition.get("objectives", ()):
                objective_id = objective["id"]
                if not self._event_matches(event, objective):
                    continue
                consumer_id = f"quest:{quest_id}:{objective_id}"
                if not self.game_state.claim_event(consumer_id, event.event_id):
                    continue
                required = max(1, int(objective.get("required", 1)))
                old_value = int(state["objectives"].get(objective_id, 0))
                new_value = min(required, old_value + self._event_amount(event))
                state["objectives"][objective_id] = new_value
                changes.append((quest_id, objective_id, new_value, required))
            if self._objectives_complete(quest_id):
                self._transition(quest_id, READY_TO_TURN_IN, f"event:{type(event).__name__}")
        return tuple(changes)

    def _objectives_complete(self, quest_id: str) -> bool:
        state = self.get_state(quest_id)
        return all(
            int(state["objectives"].get(objective["id"], 0))
            >= max(1, int(objective.get("required", 1)))
            for objective in self.get_definition(quest_id).get("objectives", ())
        )

    def turn_in(self, quest_id: str) -> bool:
        state = self.get_state(quest_id)
        if state["status"] != READY_TO_TURN_IN:
            return False
        self._transition(quest_id, COMPLETED, "turned_in")
        state["completed"] = True
        if not state.get("reward_claimed", False):
            state["reward_claimed"] = True
            self._apply_actions(self.get_definition(quest_id).get("rewards", ()), quest_id)
        if self.game_state.tracked_quest_id == quest_id:
            self.game_state.tracked_quest_id = None
        self.refresh_availability()
        return True

    def apply_action(self, action, source_id="story"):
        action_type = action.get("type")
        if action_type == "set_flag":
            return self.game_state.set_flag(action["flag"], action.get("value", True))
        if action_type == "progression" and self.dispatcher is not None:
            return self.dispatcher.publish(
                    ProgressionGranted(
                        event_id=self.game_state.next_event_id("quest_reward"),
                        source_id=source_id,
                        experience=int(action.get("experience", 0)),
                        farming_points=int(action.get("farming_points", 0)),
                        fishing_points=int(action.get("fishing_points", 0)),
                        kingdom_reputation=int(action.get("kingdom_reputation", 0)),
                        trust_npc_id=action.get("trust_npc_id"),
                        trust=int(action.get("trust", 0)),
                    )
                )
        if action_type == "progression":
            self.game_state.add_experience(int(action.get("experience", 0)))
            self.game_state.add_farming_points(int(action.get("farming_points", 0)))
            self.game_state.add_fishing_points(int(action.get("fishing_points", 0)))
            self.game_state.add_kingdom_reputation(int(action.get("kingdom_reputation", 0)))
            from gameplay.progression import synchronize_progression_unlocks

            synchronize_progression_unlocks(self.game_state)
            if action.get("trust_npc_id") and action.get("trust"):
                self.game_state.add_trust(action["trust_npc_id"], int(action["trust"]))
            return True
        if action_type == "unlock":
            return self.game_state.unlock(action["unlock_id"])
        if action_type == "unlock_transport":
            transport_id = action["transport_id"]
            self.game_state.transports.setdefault(transport_id, {})["unlocked"] = True
            self.game_state.unlock(f"transport.{transport_id}")
            return True
        if action_type in {"set_story_npc", "recruit_npc"}:
            npc_id = action["npc_id"]
            changes = dict(action.get("changes", {}))
            if action_type == "recruit_npc":
                changes.setdefault("recruited", True)
                changes.setdefault("community_member", True)
                changes.setdefault("location_id", "player_farm")
            return self.game_state.set_story_npc_state(npc_id, **changes)
        if action_type == "reveal_favorite":
            relationship = self.game_state.relationship(action["npc_id"])
            relationship.favorite_plant_known = True
            relationship.memory["favorite_plant"] = action["plant_id"]
            return True
        if action_type in {"give_item", "take_item"}:
            item_id = action["item_id"]
            count = max(1, int(action.get("count", 1)))
            inventory = getattr(self.player, "inventory", None)
            if inventory is None:
                return False
            if action_type == "take_item":
                return inventory.remove_item_count(item_id, count)
            if not inventory.can_add_item(item_id, count):
                pending = self.game_state.flags.setdefault("story.pending_items", {})
                pending[item_id] = int(pending.get(item_id, 0)) + count
                return False
            return inventory.add_item_to_slot(Item(item_id), count)
        return False

    def _apply_actions(self, actions, source_id: str):
        return tuple(self.apply_action(action, source_id) for action in actions)

    def claim_pending_items(self):
        """Deliver quest rewards deferred while the inventory was full."""
        inventory = getattr(self.player, "inventory", None)
        pending = self.game_state.flag("story.pending_items", {})
        if inventory is None or not isinstance(pending, dict):
            return ()
        claimed = []
        for item_id, raw_count in tuple(pending.items()):
            count = max(1, int(raw_count))
            if not inventory.can_add_item(item_id, count):
                continue
            if inventory.add_item_to_slot(Item(item_id), count):
                pending.pop(item_id, None)
                claimed.append((item_id, count))
        if not pending:
            self.game_state.flags.pop("story.pending_items", None)
        return tuple(claimed)

    def entries(self, *, completed=False, category=None):
        wanted = {COMPLETED} if completed else {LOCKED, AVAILABLE, ACTIVE, READY_TO_TURN_IN}
        entries = []
        for quest_id, definition in self.definitions.items():
            if category and definition.get("category", "side") != category:
                continue
            state = self.game_state.quests[quest_id]
            if state["status"] in wanted:
                entries.append((definition, state))
        return tuple(entries)

    def blocked_reason(self, quest_id: str) -> str | None:
        if self.status(quest_id) != LOCKED:
            return None
        for requirement in self.get_definition(quest_id).get("prerequisites", ()):
            if self._prerequisite_met(requirement):
                continue
            if isinstance(requirement, str):
                return f"Complete {self.get_definition(requirement)['title']} first."
            requirement_type = requirement.get("type")
            if requirement_type == "quest":
                return f"Quest requirement: {self.get_definition(requirement['quest_id'])['title']}."
            if requirement_type == "trust":
                name = requirement["npc_id"].replace("_", " ").title()
                return f"Raise {name} Trust to {int(requirement['minimum'])}."
            if requirement_type == "flag":
                return str(requirement.get("reason", "Continue the story to unlock this quest."))
        return "This quest is not available yet."

    def snapshot(self, quest_id: str) -> dict:
        """Return a detached definition/state pair for UI and diagnostics."""
        return {
            "definition": deepcopy(self.get_definition(quest_id)),
            "state": deepcopy(self.get_state(quest_id)),
        }

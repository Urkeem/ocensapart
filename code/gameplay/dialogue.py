"""Dialogue selection, conditions, actions, and persistent memory."""

from __future__ import annotations

from data.dialogue import DIALOGUE_DEFINITIONS
from gameplay.events import DialogueCompleted, DialogueSelected, EventDispatcher
from gameplay.game_state import GameState
from gameplay.quests import QuestSystem


class DialogueResolver:
    def __init__(
        self,
        game_state: GameState,
        quest_system: QuestSystem,
        dispatcher: EventDispatcher | None = None,
        definitions=None,
        player=None,
    ):
        self.game_state = game_state
        self.quest_system = quest_system
        self.dispatcher = dispatcher
        self.definitions = definitions or DIALOGUE_DEFINITIONS
        self.player = player
        self.services = {}

    def set_services(self, **services):
        self.services.update({name: service for name, service in services.items() if service is not None})
        return self

    def condition_met(self, condition: dict) -> bool:
        condition_type = condition.get("type")
        if condition_type == "quest_status":
            return self.quest_system.status(condition["quest_id"]) == condition["status"]
        if condition_type == "flag":
            # Unset boolean flags represent their initial, disabled state.
            return self.game_state.flag(condition["flag"], False) == condition.get("value", True)
        if condition_type == "trust":
            return self.game_state.relationship(condition["npc_id"]).trust >= int(condition["minimum"])
        if condition_type == "trust_tier":
            tiers = {"unknown": 0, "guarded": 1, "familiar": 2, "trusted": 3, "ally": 4}
            actual = self.game_state.relationship(condition["npc_id"]).tier
            return tiers.get(actual, 0) >= tiers.get(condition["tier"], 0)
        if condition_type == "has_item":
            inventory = getattr(self.player, "inventory", None)
            count = inventory.count_item(condition["item_id"]) if inventory is not None else 0
            result = count >= max(1, int(condition.get("count", 1)))
            return result == condition.get("value", True)
        if condition_type == "location":
            return self.game_state.current_location_id == condition["location_id"]
        if condition_type == "dialogue_consumed":
            consumed = condition["node_id"] in self.game_state.dialogue.consumed_nodes
            return consumed == condition.get("value", True)
        return False

    def eligible(self, node: dict) -> bool:
        if node.get("once") and node["id"] in self.game_state.dialogue.consumed_nodes:
            return False
        return all(self.condition_met(condition) for condition in node.get("conditions", ()))

    def resolve(self, npc_id: str) -> dict | None:
        nodes = self.definitions.get(npc_id, self.definitions.get("villager", ()))
        eligible = [node for node in nodes if self.eligible(node)]
        if not eligible:
            return None
        selected = max(eligible, key=lambda node: int(node.get("priority", 0)))
        if self.dispatcher is not None:
            self.dispatcher.publish(
                DialogueSelected(
                    event_id=self.game_state.next_event_id("dialogue_selected"),
                    npc_id=npc_id,
                    node_id=selected["id"],
                )
            )
        return selected

    def _apply_action(self, action: dict):
        action_type = action.get("type")
        if action_type == "start_quest":
            return self.quest_system.start(action["quest_id"])
        if action_type == "turn_in_quest":
            return self.quest_system.turn_in(action["quest_id"])
        if action_type == "set_flag":
            return self.game_state.set_flag(action["flag"], action.get("value", True))
        if action_type == "set_dialogue_fact":
            return self.game_state.set_dialogue_fact(action["fact"], action.get("value", True))
        if action_type == "open_shop":
            # UI/service actions are returned to the dialogue controller after
            # gameplay mutations have completed.
            return "open_shop"
        if action_type == "open_upgrade_service":
            return "open_upgrade_service"
        if action_type == "survivor_sequence":
            service = self.services.get("survivor_transport")
            if service is None:
                return False
            position = tuple(getattr(self.player, "pos", (0, 0)))
            return service.complete_sequence(position=position)[0]
        if action_type in {
            "give_item",
            "take_item",
            "unlock",
            "unlock_transport",
            "set_story_npc",
            "recruit_npc",
            "reveal_favorite",
            "progression",
        }:
            return self.quest_system.apply_action(action, source_id="dialogue")
        return False

    def complete(self, npc_id: str, node: dict, choice_id: str | None = None) -> bool:
        node_id = node["id"]
        if node.get("once") and node_id in self.game_state.dialogue.consumed_nodes:
            return ()
        if choice_id is not None:
            choice = next(
                (item for item in node.get("choices", ()) if item["id"] == choice_id),
                None,
            )
            if choice is None:
                raise ValueError(f"Unknown choice {choice_id!r} for {node_id!r}")
            for action in choice.get("actions", ()):
                self._apply_action(action)
            self.game_state.set_dialogue_fact(f"choice:{node_id}", choice_id)
        results = []
        for action in node.get("actions", ()):
            results.append(self._apply_action(action))
        if node.get("once"):
            self.game_state.remember_dialogue_node(node_id)
        if self.dispatcher is not None:
            self.dispatcher.publish(
                DialogueCompleted(
                    event_id=self.game_state.next_event_id("dialogue_completed"),
                    npc_id=npc_id,
                    node_id=node_id,
                )
            )
        return tuple(results)

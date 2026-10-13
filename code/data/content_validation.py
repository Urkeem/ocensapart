"""Cross-domain validation for story content and progression balance."""

from __future__ import annotations

from dataclasses import dataclass

from data.asset_validation import validate_asset_manifest
from data.content_manifest import ITEM_ASSETS
from data.crafting import RECIPES
from data.crops import CROP_DEFINITIONS
from data.dialogue import DIALOGUE_DEFINITIONS
from data.encounters import ENCOUNTER_DEFINITIONS
from data.enemies import ENEMY_DEFINITIONS
from data.equipment import (
    EQUIPMENT_DEFINITIONS,
    TIER_DURABILITY_MULTIPLIERS,
    UPGRADE_COIN_COSTS,
)
from data.items import ITEM_DEFINITIONS
from data.locations import LOCATION_CONNECTIONS, LOCATION_DEFINITIONS
from data.quests import QUEST_DEFINITIONS
from gameplay.game_state import experience_to_reach_level
from gameplay.recovery import RECOVERY_FEE_CAP, RECOVERY_FEE_MINIMUM, RECOVERY_FEE_PERCENT
from gameplay.resources import COMMON_ORE_WEIGHTS, ORE_SPAWN_CHANCE
from gameplay.stamina import ACTION_STAMINA_COSTS, MAX_AWAKE_GAME_MINUTES, SPRINT_STAMINA_PER_REAL_SECOND


@dataclass(frozen=True)
class ContentIssue:
    domain: str
    content_id: str
    message: str

    def __str__(self):
        return f"{self.domain}.{self.content_id}: {self.message}"


def _quest_cycles():
    edges = {
        quest_id: tuple(item for item in quest.get("prerequisites", ()) if isinstance(item, str))
        for quest_id, quest in QUEST_DEFINITIONS.items()
    }
    visiting, visited, cycles = set(), set(), []

    def visit(quest_id, path):
        if quest_id in visiting:
            start = path.index(quest_id)
            cycles.append(tuple(path[start:] + [quest_id]))
            return
        if quest_id in visited:
            return
        visiting.add(quest_id)
        for required in edges.get(quest_id, ()):
            if required in edges:
                visit(required, path + [quest_id])
        visiting.remove(quest_id)
        visited.add(quest_id)

    for quest_id in edges:
        visit(quest_id, [])
    return tuple(cycles)


def validate_content(*, include_assets=True):
    issues = []
    known_items = (
        set(ITEM_DEFINITIONS)
        | set(ITEM_ASSETS)
        | set(CROP_DEFINITIONS)
        | set(EQUIPMENT_DEFINITIONS)
        | {recipe.output_id for recipe in RECIPES.values()}
    )
    dialogue_nodes = {
        node["id"]: npc_id
        for npc_id, nodes in DIALOGUE_DEFINITIONS.items()
        for node in nodes
    }

    for npc_id, nodes in DIALOGUE_DEFINITIONS.items():
        if not any(not node.get("conditions") for node in nodes):
            issues.append(ContentIssue("dialogue", npc_id, "has no unconditional ambient fallback"))
        seen = set()
        for node in nodes:
            node_id = node.get("id")
            if not node_id:
                issues.append(ContentIssue("dialogue", npc_id, "contains a node without an id"))
            elif node_id in seen:
                issues.append(ContentIssue("dialogue", npc_id, f"duplicates node {node_id}"))
            seen.add(node_id)
            for action in node.get("actions", ()):
                if action.get("type") in {"start_quest", "turn_in_quest"} and action.get("quest_id") not in QUEST_DEFINITIONS:
                    issues.append(ContentIssue("dialogue", node_id, f"references unknown quest {action.get('quest_id')}"))

    for quest_id, quest in QUEST_DEFINITIONS.items():
        for speaker_key in ("giver", "turn_in"):
            speaker = quest.get(speaker_key)
            if speaker not in DIALOGUE_DEFINITIONS:
                issues.append(ContentIssue("quest", quest_id, f"{speaker_key} {speaker!r} has no dialogue"))
        for requirement in quest.get("prerequisites", ()):
            if isinstance(requirement, str) and requirement not in QUEST_DEFINITIONS:
                issues.append(ContentIssue("quest", quest_id, f"requires unknown quest {requirement}"))
            elif isinstance(requirement, dict) and requirement.get("type") == "quest" and requirement.get("quest_id") not in QUEST_DEFINITIONS:
                issues.append(ContentIssue("quest", quest_id, f"requires unknown quest {requirement.get('quest_id')}"))
        for objective in quest.get("objectives", ()):
            filters = objective.get("filters", {})
            if objective.get("event") == "EncounterCompleted" and filters.get("encounter_id") not in ENCOUNTER_DEFINITIONS:
                issues.append(ContentIssue("quest", quest_id, f"references unknown encounter {filters.get('encounter_id')}"))
            if objective.get("event") == "DialogueCompleted":
                wanted = filters.get("node_id", ())
                for node_id in (wanted,) if isinstance(wanted, str) else wanted:
                    if node_id not in dialogue_nodes:
                        issues.append(ContentIssue("quest", quest_id, f"references unknown dialogue node {node_id}"))
            if objective.get("event") == "ItemCrafted" and filters.get("item_id") not in known_items:
                issues.append(ContentIssue("quest", quest_id, f"requires unavailable crafted item {filters.get('item_id')}"))
            if objective.get("event") in {"CropWatered", "CropHarvested"}:
                wanted = filters.get("crop_id", ())
                for crop_id in (wanted,) if isinstance(wanted, str) else wanted:
                    if crop_id not in CROP_DEFINITIONS:
                        issues.append(ContentIssue("quest", quest_id, f"requires unavailable crop {crop_id}"))
        for action in (*quest.get("start_actions", ()), *quest.get("rewards", ())):
            if action.get("type") in {"give_item", "take_item"} and action.get("item_id") not in known_items:
                issues.append(ContentIssue("quest", quest_id, f"uses unavailable item {action.get('item_id')}"))

    for cycle in _quest_cycles():
        issues.append(ContentIssue("quest", cycle[0], f"impossible prerequisite cycle: {' -> '.join(cycle)}"))

    for recipe_id, recipe in RECIPES.items():
        if recipe.output_id not in known_items:
            issues.append(ContentIssue("recipe", recipe_id, f"output {recipe.output_id} is unavailable"))
        for item_id in recipe.ingredients:
            if item_id not in known_items:
                issues.append(ContentIssue("recipe", recipe_id, f"ingredient {item_id} is unavailable"))

    for encounter_id, encounter in ENCOUNTER_DEFINITIONS.items():
        if encounter.location_id not in LOCATION_DEFINITIONS:
            issues.append(ContentIssue("encounter", encounter_id, f"uses unknown location {encounter.location_id}"))
        if encounter.quest_id and encounter.quest_id not in QUEST_DEFINITIONS:
            issues.append(ContentIssue("encounter", encounter_id, f"uses unknown quest {encounter.quest_id}"))
        for wave in encounter.waves:
            for enemy_id in wave:
                if enemy_id not in ENEMY_DEFINITIONS:
                    issues.append(ContentIssue("encounter", encounter_id, f"uses unknown enemy {enemy_id}"))

    for origin_id, connections in LOCATION_CONNECTIONS.items():
        if origin_id not in LOCATION_DEFINITIONS:
            issues.append(ContentIssue("location", origin_id, "connection origin is undefined"))
        for connection in connections:
            if connection.get("target") not in LOCATION_DEFINITIONS:
                issues.append(ContentIssue("location", origin_id, f"connects to unknown location {connection.get('target')}"))
    for location_id, location in LOCATION_DEFINITIONS.items():
        requirements = location.get("requirements", ())
        if isinstance(requirements, dict):
            requirements = requirements.get("all", ())
        for requirement in requirements:
            if requirement.get("type") == "quest_completed" and requirement.get("quest_id") not in QUEST_DEFINITIONS:
                issues.append(ContentIssue("location", location_id, f"requires unknown quest {requirement.get('quest_id')}"))
            if requirement.get("type") in {"key_item", "possess_item"} and requirement.get("item_id") not in known_items:
                issues.append(ContentIssue("location", location_id, f"requires unavailable item {requirement.get('item_id')}"))

    if include_assets:
        issues.extend(ContentIssue("asset", issue.asset_id, issue.message) for issue in validate_asset_manifest())
    return tuple(issues)


def validate_balance():
    """Sanity-check the tuned campaign profile against progression locks."""
    issues = []
    story_xp = sum(
        int(action.get("experience", 0))
        for quest in QUEST_DEFINITIONS.values()
        for action in quest.get("rewards", ())
        if action.get("type") == "progression"
    )
    level_12_xp = experience_to_reach_level(12)
    if story_xp < level_12_xp:
        issues.append(ContentIssue("balance", "story_xp", f"{story_xp} XP cannot reach the Citadel's level 12 gate ({level_12_xp})"))
    if MAX_AWAKE_GAME_MINUTES != 48 * 60:
        issues.append(ContentIssue("balance", "awake_limit", "must remain exactly 48 game hours"))
    if not 0 < SPRINT_STAMINA_PER_REAL_SECOND <= 2:
        issues.append(ContentIssue("balance", "sprint", "sprint drain falls outside the playtested range"))
    if any(cost <= 0 or cost > 5 for cost in ACTION_STAMINA_COSTS.values()):
        issues.append(ContentIssue("balance", "actions", "action stamina costs fall outside 0-5"))
    if not (0 < RECOVERY_FEE_PERCENT <= 0.25 and 0 <= RECOVERY_FEE_MINIMUM <= RECOVERY_FEE_CAP):
        issues.append(ContentIssue("balance", "recovery_fee", "recovery fee settings are inconsistent"))
    if any(enemy.health <= 0 or enemy.xp_reward <= 0 for enemy in ENEMY_DEFINITIONS.values()):
        issues.append(ContentIssue("balance", "enemies", "enemy health and XP must be positive"))
    if any(not 30 <= equipment.base_max_durability <= 150 for equipment in EQUIPMENT_DEFINITIONS.values()):
        issues.append(ContentIssue("balance", "equipment", "base durability falls outside 30-150"))
    multipliers = tuple(TIER_DURABILITY_MULTIPLIERS.values())
    if tuple(sorted(multipliers)) != multipliers or len(set(multipliers)) != len(multipliers):
        issues.append(ContentIssue("balance", "equipment_tiers", "durability multipliers must rise by tier"))
    upgrade_costs = tuple(UPGRADE_COIN_COSTS.values())
    if tuple(sorted(upgrade_costs)) != upgrade_costs:
        issues.append(ContentIssue("balance", "upgrade_costs", "upgrade costs must rise by tier"))
    if any(not 0 < chance <= 0.10 for chance in ORE_SPAWN_CHANCE.values()):
        issues.append(ContentIssue("balance", "ore_spawn", "ore spawn chance falls outside 0-10%"))
    ore_weights = dict(COMMON_ORE_WEIGHTS)
    if ore_weights.get("coal_ore", 0) <= ore_weights.get("diamond_ore", 0) or ore_weights.get("iron_ore", 0) <= ore_weights.get("ruby_ore", 0):
        issues.append(ContentIssue("balance", "ore_rarity", "rare ores must remain rarer than coal and iron"))
    if any(crop.harvest_points <= 0 or crop.unlock_at_farming_points < 0 for crop in CROP_DEFINITIONS.values()):
        issues.append(ContentIssue("balance", "crops", "crop points and thresholds must be non-negative"))
    return tuple(issues)


def validate_all_content():
    return (*validate_content(), *validate_balance())

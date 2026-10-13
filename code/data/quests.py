"""Authored quest definitions.

The runtime treats these records as immutable content. Mutable objective progress
belongs to ``GameState.quests`` so saving never depends on Python objects.
"""

from data.encounters import (
    ALCHEMIST_FAMILY_ENCOUNTER_ID,
    ALCHEMIST_RESCUE_ENCOUNTER_ID,
    CITADEL_ENCOUNTER_ID,
    FINAL_FARM_DEFENSE_ENCOUNTER_ID,
    FIRST_DEFENSE_ENCOUNTER_ID,
    HOLD_1_ENCOUNTER_ID,
    HOLD_2_ENCOUNTER_ID,
    HOLD_3_ENCOUNTER_ID,
    HOLD_4_ENCOUNTER_ID,
    HOLD_5_ENCOUNTER_ID,
)

MORNING_CHORES = {
    "id": "prologue.morning_chores",
    "title": "Morning Chores",
    "summary": "Help your wife prepare the farm for the day.",
    "category": "story",
    "giver": "wife",
    "turn_in": "wife",
    "prerequisites": (),
    "objectives": (
        {
            "id": "water_crops",
            "description": "Water growing corn or tomato crops",
            "event": "CropWatered",
            "required": 3,
            "filters": {
                "crop_id": ("corn", "tomato"),
                "location_id": "player_farm",
            },
        },
        {
            "id": "harvest_breakfast",
            "description": "Harvest ripe corn or tomatoes",
            "event": "CropHarvested",
            "required": 2,
            "filters": {
                "crop_id": ("corn", "tomato"),
                "location_id": "player_farm",
            },
        },
    ),
    "start_actions": (
        {"type": "set_flag", "flag": "prologue.morning_chores_started", "value": True},
    ),
    "rewards": (
        {"type": "set_flag", "flag": "prologue.morning_chores_complete", "value": True},
        {"type": "progression", "experience": 25},
    ),
}


FIRST_DEFENSE = {
    "id": "prologue.first_defense",
    "title": "Defend the Farm",
    "summary": "Drive the first goblin raiders away from the farmstead.",
    "category": "story",
    "giver": "wife",
    "turn_in": "wife",
    "prerequisites": (MORNING_CHORES["id"],),
    "objectives": (
        {
            "id": "survive_attack",
            "description": "Defeat every wave of goblin raiders",
            "event": "EncounterCompleted",
            "required": 1,
            "filters": {"encounter_id": FIRST_DEFENSE_ENCOUNTER_ID},
        },
    ),
    "start_actions": (
        {"type": "set_flag", "flag": "prologue.first_defense_started", "value": True},
    ),
    "rewards": (
        {"type": "set_flag", "flag": "prologue.first_defense_complete", "value": True},
        {"type": "progression", "experience": 25, "kingdom_reputation": 5},
    ),
}


def _objective(objective_id, description, event, *, required=1, filters=None):
    return {
        "id": objective_id,
        "description": description,
        "event": event,
        "required": required,
        "filters": dict(filters or {}),
    }


def _story_quest(
    quest_id,
    title,
    summary,
    act,
    giver,
    turn_in,
    prerequisites,
    objectives=(),
    *,
    start_actions=(),
    rewards=(),
    tier="primary",
):
    return {
        "id": quest_id,
        "title": title,
        "summary": summary,
        "category": "story",
        "story_act": act,
        "tier": tier,
        "giver": giver,
        "turn_in": turn_in,
        "prerequisites": tuple(prerequisites),
        "objectives": tuple(objectives),
        "start_actions": tuple(start_actions),
        "rewards": tuple(rewards),
    }


WIFES_ILLNESS = _story_quest(
    "prologue.wifes_illness",
    "A Sudden Illness",
    "Ask Lillian about the strange illness weakening your Wife.",
    "prologue",
    "wife",
    "lillian",
    (FIRST_DEFENSE["id"],),
    (_objective("seek_lillian", "Speak with Lillian in Ironveil Village", "DialogueCompleted", filters={"node_id": "lillian.illness_lead"}),),
    rewards=(
        {"type": "set_flag", "flag": "prologue.wife_ill", "value": True},
        {"type": "progression", "experience": 25},
    ),
)

RESCUE_ALCHEMIST = _story_quest(
    "act1.rescue_alchemist",
    "The Missing Alchemist",
    "Break the raiders' hold on Ironveil and free the Alchemist.",
    "act_1",
    "lillian",
    "alchemist",
    (WIFES_ILLNESS["id"],),
    (_objective("clear_captors", "Defeat the Alchemist's captors", "EncounterCompleted", filters={"encounter_id": ALCHEMIST_RESCUE_ENCOUNTER_ID}),),
    rewards=(
        {"type": "set_flag", "flag": "story.alchemist_rescued", "value": True},
        {"type": "set_story_npc", "npc_id": "alchemist", "changes": {"recruited": True, "location_id": "alchemist_workspace"}},
        {"type": "unlock", "unlock_id": "recipes.temporary_medicine"},
        {"type": "progression", "experience": 200, "kingdom_reputation": 5, "trust_npc_id": "alchemist", "trust": 25},
    ),
)

TEMPORARY_MEDICINE = _story_quest(
    "act1.temporary_medicine",
    "Borrowed Time",
    "Craft the Alchemist's temporary medicine for your Wife.",
    "act_1",
    "alchemist",
    "alchemist",
    (RESCUE_ALCHEMIST["id"],),
    (_objective("craft_medicine", "Craft temporary medicine", "ItemCrafted", filters={"item_id": "temporary_medicine"}),),
    rewards=(
        {"type": "take_item", "item_id": "temporary_medicine"},
        {"type": "set_flag", "flag": "act1.wife_stabilized", "value": True},
        {"type": "set_flag", "flag": "farm.expansion.alchemist_workspace", "value": True},
        {"type": "unlock", "unlock_id": "recipes.royal_medicine"},
        {"type": "progression", "experience": 175, "farming_points": 20},
    ),
)

RECRUIT_HUNTER = _story_quest(
    "act2.recruit_hunter",
    "Hunter's Trial",
    "Earn Hunter's confidence and recruit him for the Hold campaign.",
    "act_2",
    "hunter",
    "hunter",
    (TEMPORARY_MEDICINE["id"],),
    (_objective("hunter_trial", "Complete Hunter's tracking trial", "DialogueCompleted", filters={"node_id": "hunter.recruit.trial"}),),
    rewards=(
        {"type": "recruit_npc", "npc_id": "hunter", "changes": {"location_id": "village", "community_member": False}},
        {"type": "progression", "experience": 250, "trust_npc_id": "hunter", "trust": 30},
        {"type": "set_flag", "flag": "act2.hunter_recruited", "value": True},
    ),
)

RECOVER_KINGDOM_MAP = _story_quest(
    "act2.recover_kingdom_map",
    "The Navigator's Map",
    "Confront the Navigator and recover the route through the Holds.",
    "act_2",
    "navigator",
    "navigator",
    (RECRUIT_HUNTER["id"],),
    (_objective("confront_navigator", "Question the Navigator", "DialogueCompleted", filters={"node_id": "navigator.map.confront"}),),
    rewards=(
        {"type": "give_item", "item_id": "kingdom_map"},
        {"type": "set_flag", "flag": "act2.kingdom_map_recovered", "value": True},
        {"type": "progression", "experience": 250, "kingdom_reputation": 5},
    ),
)

SAVE_QUEEN = _story_quest(
    "act3.save_queen",
    "Medicine for the Queen",
    "Craft royal medicine and bring it to the Queen in Ironveil Castle.",
    "act_3",
    "king",
    "queen",
    (RECOVER_KINGDOM_MAP["id"], TEMPORARY_MEDICINE["id"]),
    (_objective("craft_royal_medicine", "Craft royal medicine", "ItemCrafted", filters={"item_id": "royal_medicine"}),),
    rewards=(
        {"type": "take_item", "item_id": "royal_medicine"},
        {"type": "set_flag", "flag": "act3.queen_saved", "value": True},
        {"type": "progression", "experience": 400, "kingdom_reputation": 15, "trust_npc_id": "queen", "trust": 30},
    ),
)

ROYAL_AID = _story_quest(
    "act3.royal_aid",
    "The King's Soldiers",
    "Accept the King's soldiers and learn that the Princess is alive.",
    "act_3",
    "king",
    "king",
    (SAVE_QUEEN["id"],),
    (),
    rewards=(
        {"type": "set_flag", "flag": "act3.royal_soldiers_granted", "value": True},
        {"type": "set_flag", "flag": "act3.princess_revealed", "value": True},
        {"type": "recruit_npc", "npc_id": "royal_soldier_1"},
        {"type": "recruit_npc", "npc_id": "royal_soldier_2"},
        {"type": "progression", "experience": 250, "kingdom_reputation": 10},
    ),
)

OPEN_MARKET_STALL = _story_quest(
    "pirate.open_market_stall",
    "A Stall by the Coast",
    "Craft a wheelbarrow to finish a market stall that will attract Pirate.",
    "pirate_arc",
    "lillian",
    "pirate",
    (TEMPORARY_MEDICINE["id"],),
    (_objective("craft_wheelbarrow", "Craft a wheelbarrow for the stall", "ItemCrafted", filters={"item_id": "wheelbarrow"}),),
    rewards=(
        {"type": "set_flag", "flag": "pirate.market_stall_open", "value": True},
        {"type": "set_flag", "flag": "farm.expansion.market_stall", "value": True},
        {"type": "progression", "experience": 200},
    ),
    tier="secondary",
)

BEFRIEND_PIRATE = _story_quest(
    "pirate.befriend",
    "Lillian's Rum",
    "Share Lillian's rum and secure Pirate's help at sea.",
    "pirate_arc",
    "pirate",
    "pirate",
    (OPEN_MARKET_STALL["id"], RECOVER_KINGDOM_MAP["id"]),
    (_objective("share_rum", "Share a drink and hear Pirate's terms", "DialogueCompleted", filters={"node_id": "pirate.befriend.rum"}),),
    rewards=(
        {"type": "unlock_transport", "transport_id": "player_boat"},
        {"type": "unlock_transport", "transport_id": "pirate_ship"},
        {"type": "recruit_npc", "npc_id": "pirate"},
        {"type": "set_flag", "flag": "pirate.alliance", "value": True},
        {"type": "progression", "experience": 300, "trust_npc_id": "pirate", "trust": 50},
    ),
    tier="secondary",
)

ASHFALL = _story_quest(
    "holds.ashfall",
    "Hold I: Ashfall",
    "Clear the first Hold on the Navigator's map.",
    "holds_1_3",
    "hunter",
    "hunter",
    (RECOVER_KINGDOM_MAP["id"], BEFRIEND_PIRATE["id"]),
    (_objective("clear_ashfall", "Clear Ashfall Hold", "EncounterCompleted", filters={"encounter_id": HOLD_1_ENCOUNTER_ID}),),
    rewards=(
        {"type": "set_flag", "flag": "holds.hold_1_complete", "value": True},
        {"type": "progression", "experience": 500, "kingdom_reputation": 5},
    ),
)

BLACKTHORN = _story_quest(
    "holds.blackthorn",
    "Hold II: Blackthorn",
    "Break the middle Hold's monster companies.",
    "holds_1_3",
    "hunter",
    "hunter",
    (ASHFALL["id"],),
    (_objective("clear_blackthorn", "Clear Blackthorn Hold", "EncounterCompleted", filters={"encounter_id": HOLD_2_ENCOUNTER_ID}),),
    rewards=(
        {"type": "set_flag", "flag": "holds.hold_2_complete", "value": True},
        {"type": "progression", "experience": 600, "kingdom_reputation": 5},
    ),
)

GRIMROOT = _story_quest(
    "holds.grimroot",
    "Hold III: Grimroot",
    "Clear Grimroot and evacuate its captives with Hunter and Pirate.",
    "holds_1_3",
    "hunter",
    "hunter",
    (BLACKTHORN["id"],),
    (
        _objective("clear_grimroot", "Clear Grimroot Hold", "EncounterCompleted", filters={"encounter_id": HOLD_3_ENCOUNTER_ID}),
        _objective("extract_survivors", "Move the survivors through Pirate's extraction", "DialogueCompleted", filters={"node_id": "hunter.grimroot.extraction"}),
    ),
    start_actions=({"type": "set_story_npc", "npc_id": "hunter", "changes": {"location_id": "hold_3"}},),
    rewards=(
        {"type": "set_flag", "flag": "holds.hold_3_complete", "value": True},
        {"type": "give_item", "item_id": "hollow_crypt_key"},
        {"type": "recruit_npc", "npc_id": "hunter"},
        {"type": "set_flag", "flag": "farm.expansion.survivor_homes", "value": True},
        {"type": "progression", "experience": 700, "kingdom_reputation": 15},
    ),
)

HOLLOW_CRYPT = _story_quest(
    "holds.hollow_crypt",
    "Hold IV: Hollow Crypt",
    "Use the crypt key and recover the royal tiara.",
    "holds_4_5",
    "hunter",
    "hunter",
    (GRIMROOT["id"], ROYAL_AID["id"]),
    (_objective("clear_hollow_crypt", "Clear the Hollow Crypt", "EncounterCompleted", filters={"encounter_id": HOLD_4_ENCOUNTER_ID}),),
    rewards=(
        {"type": "set_flag", "flag": "holds.hold_4_complete", "value": True},
        {"type": "give_item", "item_id": "royal_tiara"},
        {"type": "give_item", "item_id": "ironveil_key"},
        {"type": "progression", "experience": 1100, "kingdom_reputation": 10},
    ),
)

IRONVEIL_PRISON = _story_quest(
    "holds.ironveil_prison",
    "Hold V: Ironveil Prison",
    "Open the prison with the Ironveil Key and rescue the Princess.",
    "holds_4_5",
    "king",
    "princess",
    (HOLLOW_CRYPT["id"],),
    (_objective("clear_prison", "Defeat the Ironveil jailers", "EncounterCompleted", filters={"encounter_id": HOLD_5_ENCOUNTER_ID}),),
    rewards=(
        {"type": "set_flag", "flag": "holds.hold_5_complete", "value": True},
        {"type": "set_flag", "flag": "act5.princess_rescued", "value": True},
        {"type": "recruit_npc", "npc_id": "princess"},
        {"type": "progression", "experience": 1000, "kingdom_reputation": 20, "trust_npc_id": "princess", "trust": 50},
    ),
)

FINAL_FARM_DEFENSE = _story_quest(
    "act6.final_farm_defense",
    "The Last Siege",
    "Defend the farm community against the Necromancer's final assault.",
    "act_6",
    "wife",
    "wife",
    (IRONVEIL_PRISON["id"],),
    (_objective("survive_final_siege", "Defeat every attacking wave", "EncounterCompleted", filters={"encounter_id": FINAL_FARM_DEFENSE_ENCOUNTER_ID}),),
    rewards=(
        {"type": "set_flag", "flag": "act6.farm_survived", "value": True},
        {"type": "progression", "experience": 800, "kingdom_reputation": 20},
    ),
)

RESCUE_ALCHEMIST_FAMILY = _story_quest(
    "act6.rescue_alchemist_family",
    "The Alchemist's Family",
    "Free the Alchemist's family and recover the first true potion.",
    "act_6",
    "alchemist",
    "alchemist",
    (FINAL_FARM_DEFENSE["id"],),
    (_objective("free_family", "Defeat the family captors", "EncounterCompleted", filters={"encounter_id": ALCHEMIST_FAMILY_ENCOUNTER_ID}),),
    rewards=(
        {"type": "give_item", "item_id": "potion_of_life"},
        {"type": "set_flag", "flag": "potions.life_recovered", "value": True},
        {"type": "recruit_npc", "npc_id": "alchemist_family_1"},
        {"type": "recruit_npc", "npc_id": "alchemist_family_2"},
        {"type": "set_flag", "flag": "farm.expansion.alchemist_family_home", "value": True},
        {"type": "progression", "experience": 700, "kingdom_reputation": 15},
    ),
)

NECROMANCER_CITADEL = _story_quest(
    "act7.necromancer_citadel",
    "The Necromancer's Citadel",
    "Sail to the Citadel, defeat its master, and recover the final potions.",
    "act_7",
    "pirate",
    "necromancer",
    (RESCUE_ALCHEMIST_FAMILY["id"],),
    (_objective("defeat_necromancer", "Defeat the Necromancer", "EncounterCompleted", filters={"encounter_id": CITADEL_ENCOUNTER_ID}),),
    rewards=(
        {"type": "give_item", "item_id": "potion_of_memory"},
        {"type": "give_item", "item_id": "potion_of_vigor"},
        {"type": "set_flag", "flag": "potions.memory_recovered", "value": True},
        {"type": "set_flag", "flag": "potions.vigor_recovered", "value": True},
        {"type": "set_flag", "flag": "act7.three_potions_recovered", "value": True},
        {"type": "unlock", "unlock_id": "recipes.last_cure"},
        {"type": "progression", "experience": 1000, "kingdom_reputation": 25},
    ),
)

CRAFT_LAST_CURE = _story_quest(
    "act8.craft_last_cure",
    "The Last Cure",
    "Combine the three recovered potions into the cure for your Wife.",
    "act_8",
    "alchemist",
    "wife",
    (NECROMANCER_CITADEL["id"],),
    (_objective("craft_cure", "Craft the Last Cure", "ItemCrafted", filters={"item_id": "last_cure"}),),
    rewards=(
        {"type": "take_item", "item_id": "last_cure"},
        {"type": "set_flag", "flag": "act8.wife_cured", "value": True},
        {"type": "unlock", "unlock_id": "farming.cured_seeds"},
        {"type": "progression", "experience": 500, "farming_points": 100},
    ),
)

GROW_CURED_CROPS = _story_quest(
    "act8.grow_cured_crops",
    "Seeds of Recovery",
    "Grow healthy corn or tomatoes from the Alchemist's cured seed treatment.",
    "act_8",
    "wife",
    "wife",
    (CRAFT_LAST_CURE["id"],),
    (_objective("harvest_cured_crops", "Harvest three cured corn or tomato crops", "CropHarvested", required=3, filters={"crop_id": ("corn", "tomato"), "location_id": "player_farm"}),),
    rewards=(
        {"type": "give_item", "item_id": "cured_seed_bag", "count": 5},
        {"type": "set_flag", "flag": "act8.cured_crops_grown", "value": True},
        {"type": "progression", "experience": 300, "kingdom_reputation": 10},
    ),
)

DISTRIBUTE_CURE = _story_quest(
    "act8.distribute_cure",
    "A Cure for Every Field",
    "Give cured seed bags to the allies who helped restore Ironveil.",
    "act_8",
    "alchemist",
    "wife",
    (GROW_CURED_CROPS["id"],),
    (
        _objective(
            "deliver_seed_bags",
            "Give cured seed bags to five allies",
            "DialogueCompleted",
            required=5,
            filters={"node_id": (
                "alchemist.cure.delivery",
                "hunter.cure.delivery",
                "pirate.cure.delivery",
                "princess.cure.delivery",
                "king.cure.delivery",
            )},
        ),
    ),
    rewards=(
        {"type": "set_flag", "flag": "act8.cure_distributed", "value": True},
        {"type": "set_flag", "flag": "world.kingdom_restored", "value": True},
        {"type": "progression", "experience": 500, "kingdom_reputation": 50},
    ),
)

REBUILDING_EPILOGUE = _story_quest(
    "epilogue.rebuilding",
    "Ironveil Reborn",
    "Walk through the rebuilt community and speak with your Wife.",
    "epilogue",
    "wife",
    "wife",
    (DISTRIBUTE_CURE["id"],),
    (),
    rewards=(
        {"type": "set_flag", "flag": "epilogue.complete", "value": True},
        {"type": "set_flag", "flag": "game.story_complete", "value": True},
    ),
)


STORY_QUESTS = (
    MORNING_CHORES,
    FIRST_DEFENSE,
    WIFES_ILLNESS,
    RESCUE_ALCHEMIST,
    TEMPORARY_MEDICINE,
    RECRUIT_HUNTER,
    RECOVER_KINGDOM_MAP,
    SAVE_QUEEN,
    ROYAL_AID,
    OPEN_MARKET_STALL,
    BEFRIEND_PIRATE,
    ASHFALL,
    BLACKTHORN,
    GRIMROOT,
    HOLLOW_CRYPT,
    IRONVEIL_PRISON,
    FINAL_FARM_DEFENSE,
    RESCUE_ALCHEMIST_FAMILY,
    NECROMANCER_CITADEL,
    CRAFT_LAST_CURE,
    GROW_CURED_CROPS,
    DISTRIBUTE_CURE,
    REBUILDING_EPILOGUE,
)


QUEST_DEFINITIONS = {quest["id"]: quest for quest in STORY_QUESTS}

"""Data-defined combat encounters and their wave compositions."""

from __future__ import annotations

from dataclasses import dataclass


FIRST_DEFENSE_ENCOUNTER_ID = "encounter:player_farm:first_defense:1"
ALCHEMIST_RESCUE_ENCOUNTER_ID = "encounter:village:alchemist_rescue:1"
HOLD_1_ENCOUNTER_ID = "encounter:hold_1:ashfall:1"
HOLD_2_ENCOUNTER_ID = "encounter:hold_2:blackthorn:1"
HOLD_3_ENCOUNTER_ID = "encounter:hold_3:grimroot:1"
HOLD_4_ENCOUNTER_ID = "encounter:hold_4:hollow_crypt:1"
HOLD_5_ENCOUNTER_ID = "encounter:hold_5:ironveil_prison:1"
FINAL_FARM_DEFENSE_ENCOUNTER_ID = "encounter:player_farm:final_defense:1"
ALCHEMIST_FAMILY_ENCOUNTER_ID = "encounter:village:alchemist_family:1"
CITADEL_ENCOUNTER_ID = "encounter:necromancer_citadel:final:1"
MIN_ENEMIES_PER_WAVE = 15

_LEADER_REINFORCEMENTS = {
    "skeleton_king": ("skeleton_hunter", "armored_skeleton"),
    "necromancer": ("cultist", "armored_skeleton", "demon"),
}


def expand_wave(enemy_ids, minimum=MIN_ENEMIES_PER_WAVE):
    """Repeat a wave's enemy mix to its minimum size without cloning bosses."""
    wave = list(enemy_ids)
    if not wave:
        raise ValueError("Encounter waves require at least one enemy")
    leaders = [enemy_id for enemy_id in wave if enemy_id in _LEADER_REINFORCEMENTS]
    reinforcement_pool = [enemy_id for enemy_id in wave if enemy_id not in _LEADER_REINFORCEMENTS]
    if not reinforcement_pool and leaders:
        reinforcement_pool = list(_LEADER_REINFORCEMENTS[leaders[0]])
    if not reinforcement_pool:
        reinforcement_pool = list(wave)
    index = 0
    while len(wave) < max(1, int(minimum)):
        wave.append(reinforcement_pool[index % len(reinforcement_pool)])
        index += 1
    return tuple(wave)


@dataclass(frozen=True)
class EncounterDefinition:
    id: str
    name: str
    location_id: str
    quest_id: str | None
    waves: tuple[tuple[str, ...], ...]
    spawn_radius: int = 340
    leash_radius: int = 650
    retry_after_recovery: bool = True
    completion_flag: str | None = None


FIRST_DEFENSE = EncounterDefinition(
    id=FIRST_DEFENSE_ENCOUNTER_ID,
    name="First Farm Defense",
    location_id="player_farm",
    quest_id="prologue.first_defense",
    waves=(
        expand_wave(("goblin_berserker",)),
        expand_wave(("goblin_berserker", "goblin_slinger")),
    ),
    completion_flag="prologue.first_defense_won",
)


def _encounter(encounter_id, name, location_id, quest_id, waves, *, radius=120, leash=360, flag=None):
    return EncounterDefinition(
        id=encounter_id,
        name=name,
        location_id=location_id,
        quest_id=quest_id,
        waves=tuple(expand_wave(wave) for wave in waves),
        spawn_radius=radius,
        leash_radius=leash,
        completion_flag=flag,
    )


STORY_ENCOUNTERS = (
    FIRST_DEFENSE,
    _encounter(
        ALCHEMIST_RESCUE_ENCOUNTER_ID,
        "Rescue the Alchemist",
        "alchemist_home",
        "act1.rescue_alchemist",
        (("goblin_berserker", "goblin_slinger"), ("cultist", "skeleton_grunt")),
        radius=190,
        leash=480,
        flag="act1.alchemist_rescue_won",
    ),
    _encounter(HOLD_1_ENCOUNTER_ID, "Ashfall Hold", "hold_1", "holds.ashfall", (("skeleton", "bat"), ("skeleton_grunt", "goblin_slinger")), flag="holds.hold_1_encounter_complete"),
    _encounter(HOLD_2_ENCOUNTER_ID, "Blackthorn Hold", "hold_2", "holds.blackthorn", (("orc", "hellbat"), ("werewolf", "flame_golem")), flag="holds.hold_2_encounter_complete"),
    _encounter(HOLD_3_ENCOUNTER_ID, "Grimroot Hold", "hold_3", "holds.grimroot", (("cultist", "skeleton_hunter"), ("skeleton_king",)), flag="holds.hold_3_encounter_complete"),
    _encounter(HOLD_4_ENCOUNTER_ID, "Hollow Crypt", "hold_4", "holds.hollow_crypt", (("armored_skeleton", "demon"), ("warlock", "elite_orc")), flag="holds.hold_4_encounter_complete"),
    _encounter(HOLD_5_ENCOUNTER_ID, "Ironveil Prison", "hold_5", "holds.ironveil_prison", (("armored_orc", "armored_skeleton"), ("demon", "warlock")), flag="holds.hold_5_encounter_complete"),
    _encounter(
        FINAL_FARM_DEFENSE_ENCOUNTER_ID,
        "Final Farm Defense",
        "player_farm",
        "act6.final_farm_defense",
        (("orc", "werewolf"), ("armored_orc", "warlock"), ("elite_orc", "demon")),
        radius=300,
        leash=680,
        flag="act6.final_farm_defense_won",
    ),
    _encounter(
        ALCHEMIST_FAMILY_ENCOUNTER_ID,
        "Rescue the Alchemist's Family",
        "village",
        "act6.rescue_alchemist_family",
        (("elite_orc", "armored_skeleton"), ("demon", "warlock")),
        radius=190,
        leash=500,
        flag="act6.alchemist_family_rescued",
    ),
    _encounter(
        CITADEL_ENCOUNTER_ID,
        "Necromancer's Citadel",
        "necromancer_citadel",
        "act7.necromancer_citadel",
        (("demon", "warlock"), ("elite_orc", "armored_skeleton"), ("necromancer",)),
        radius=130,
        leash=400,
        flag="act7.citadel_battle_won",
    ),
)


ENCOUNTER_DEFINITIONS = {encounter.id: encounter for encounter in STORY_ENCOUNTERS}

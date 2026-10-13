"""Persisted survivor relocation from Hunter's rescue to the farm."""

from __future__ import annotations

import pygame

from gameplay.events import NpcRescued, SurvivorStageChanged, publish_from


CAPTIVE = "captive"
FOLLOWING_HUNTER = "following_hunter"
AT_EXTRACTION = "at_extraction"
ABOARD_PIRATE_SHIP = "aboard_pirate_ship"
TRAVELLING = "travelling"
SETTLED_AT_FARM = "settled_at_farm"

SURVIVOR_STAGES = (
    CAPTIVE,
    FOLLOWING_HUNTER,
    AT_EXTRACTION,
    ABOARD_PIRATE_SHIP,
    TRAVELLING,
    SETTLED_AT_FARM,
)

HUNTER_RESCUE_GROUP = {
    "id": "hunter_hold_survivors",
    "survivor_ids": ("hunter_survivor_1", "hunter_survivor_2", "hunter_survivor_3"),
    "origin_location_id": "hold_3",
    "hunter_id": "hunter",
    "pirate_id": "pirate",
    "destination_location_id": "player_farm",
}


class SurvivorTransportService:
    """Advance one rescue group through an idempotent authored travel chain."""

    def __init__(self, game_state, vessel_manager, event_dispatcher=None, npc_manager=None):
        self.game_state = game_state
        self.vessel_manager = vessel_manager
        self.event_dispatcher = event_dispatcher
        self.npc_manager = npc_manager
        self.register_group(HUNTER_RESCUE_GROUP)
        self.sync_community()

    def register_group(self, definition):
        group_id = definition["id"]
        record = self.game_state.survivor_groups.setdefault(
            group_id,
            {
                "stage": CAPTIVE,
                "survivor_ids": list(definition["survivor_ids"]),
                "origin_location_id": definition["origin_location_id"],
                "hunter_id": definition["hunter_id"],
                "pirate_id": definition["pirate_id"],
                "destination_location_id": definition["destination_location_id"],
                "history": [CAPTIVE],
            },
        )
        if record.get("stage") not in SURVIVOR_STAGES:
            record["stage"] = CAPTIVE
        record.setdefault("survivor_ids", list(definition["survivor_ids"]))
        record.setdefault("history", [record["stage"]])
        return record

    def record(self, group_id=HUNTER_RESCUE_GROUP["id"]):
        try:
            return self.game_state.survivor_groups[group_id]
        except KeyError as error:
            raise KeyError(f"Unknown survivor group {group_id!r}") from error

    def _transition(self, group_id, expected_stage, new_stage):
        record = self.record(group_id)
        if record["stage"] == new_stage:
            return True, ""
        if record["stage"] != expected_stage:
            return False, f"This rescue is at the {record['stage'].replace('_', ' ')} stage."
        old_stage = record["stage"]
        record["stage"] = new_stage
        if not record["history"] or record["history"][-1] != new_stage:
            record["history"].append(new_stage)
        publish_from(
            self,
            SurvivorStageChanged(
                event_id=f"survivor:{group_id}:{new_stage}",
                group_id=group_id,
                old_stage=old_stage,
                new_stage=new_stage,
            ),
        )
        return True, ""

    def free(self, group_id=HUNTER_RESCUE_GROUP["id"]):
        success, reason = self._transition(group_id, CAPTIVE, FOLLOWING_HUNTER)
        if success:
            record = self.record(group_id)
            for index, npc_id in enumerate(record["survivor_ids"]):
                self.game_state.set_story_npc_state(
                    npc_id,
                    rescue_group_id=group_id,
                    rescue_stage=FOLLOWING_HUNTER,
                    following_id=record["hunter_id"],
                    location_id=record["origin_location_id"],
                    community_member=False,
                    follow_index=index,
                )
        return success, reason

    def reach_extraction(self, group_id=HUNTER_RESCUE_GROUP["id"], position=None):
        if self.record(group_id)["stage"] == AT_EXTRACTION:
            return True, ""
        success, reason = self._transition(group_id, FOLLOWING_HUNTER, AT_EXTRACTION)
        if success:
            record = self.record(group_id)
            if position is None:
                hunter = self._actor(record["hunter_id"])
                position = tuple(hunter.pos) if hunter is not None else None
            record["extraction_position"] = position
            self._set_survivor_stage(group_id, AT_EXTRACTION, location_id=record["origin_location_id"])
        return success, reason

    def call_pirate_to_extraction(self, group_id=HUNTER_RESCUE_GROUP["id"]):
        record = self.record(group_id)
        if record["stage"] != AT_EXTRACTION:
            return False, "Bring every survivor to Hunter's extraction point first."
        ship = self.vessel_manager.pirate_ship
        if not ship.unlocked:
            return False, "Earn Pirate's help before calling the rescue ship."
        ship.dock("hunter_extraction", record.get("extraction_position"))
        ship.location_id = record["origin_location_id"]
        if hasattr(ship, "persist"):
            ship.persist()
        return True, ""

    def handoff_to_pirate(self, group_id=HUNTER_RESCUE_GROUP["id"]):
        record = self.record(group_id)
        ship = self.vessel_manager.pirate_ship
        if not ship.unlocked:
            return False, "Earn Pirate's help before handing over the survivors."
        if ship.docked_at != "hunter_extraction":
            return False, "Wait for Pirate's ship to reach the extraction dock."
        success, reason = self._transition(group_id, AT_EXTRACTION, ABOARD_PIRATE_SHIP)
        if success:
            self._set_survivor_stage(group_id, ABOARD_PIRATE_SHIP, location_id="pirate_ship")
        return success, reason

    def begin_travel(self, group_id=HUNTER_RESCUE_GROUP["id"]):
        record = self.record(group_id)
        if record["stage"] == TRAVELLING:
            return True, ""
        if record["stage"] != ABOARD_PIRATE_SHIP:
            return False, "Complete Pirate's survivor handoff before departing."
        success, reason = self.vessel_manager.pirate_ship.begin_travel(record["destination_location_id"])
        if not success:
            return success, reason
        self.vessel_manager.pirate_ship.location_id = "pirate_ship"
        if hasattr(self.vessel_manager.pirate_ship, "persist"):
            self.vessel_manager.pirate_ship.persist()
        success, reason = self._transition(group_id, ABOARD_PIRATE_SHIP, TRAVELLING)
        if success:
            self._set_survivor_stage(group_id, TRAVELLING, location_id="pirate_ship")
        return success, reason

    def complete_travel(self, group_id=HUNTER_RESCUE_GROUP["id"]):
        record = self.record(group_id)
        if record["stage"] == SETTLED_AT_FARM:
            self.sync_community()
            return True, ""
        success, reason = self._transition(group_id, TRAVELLING, SETTLED_AT_FARM)
        if not success:
            return success, reason
        destination = record["destination_location_id"]
        self.vessel_manager.pirate_ship.dock(destination)
        for npc_id in record["survivor_ids"]:
            self.game_state.set_story_npc_state(
                npc_id,
                rescue_group_id=group_id,
                rescue_stage=SETTLED_AT_FARM,
                following_id=None,
                location_id=destination,
                community_member=True,
            )
            publish_from(
                self,
                NpcRescued(
                    event_id=f"survivor:{group_id}:{npc_id}:settled",
                    npc_id=npc_id,
                    encounter_id=record["origin_location_id"],
                    trust_reward=3,
                    reputation_reward=2,
                ),
            )
        self._set_survivor_stage(group_id, SETTLED_AT_FARM, location_id=destination)
        self.game_state.set_flag("farm.hunter_survivors_settled", True)
        self.sync_community()
        return True, ""

    def complete_sequence(self, group_id=HUNTER_RESCUE_GROUP["id"], position=None):
        """Resume and finish the authored handoff from any persisted stage."""
        while True:
            stage = self.record(group_id)["stage"]
            if stage == CAPTIVE:
                result = self.free(group_id)
            elif stage == FOLLOWING_HUNTER:
                result = self.reach_extraction(group_id, position)
            elif stage == AT_EXTRACTION:
                result = self.call_pirate_to_extraction(group_id)
                if result[0]:
                    result = self.handoff_to_pirate(group_id)
            elif stage == ABOARD_PIRATE_SHIP:
                result = self.begin_travel(group_id)
            elif stage == TRAVELLING:
                result = self.complete_travel(group_id)
            elif stage == SETTLED_AT_FARM:
                return True, ""
            else:
                return False, f"Unknown survivor stage {stage!r}."
            if not result[0]:
                return result

    def _set_survivor_stage(self, group_id, stage, *, location_id):
        for npc_id in self.record(group_id)["survivor_ids"]:
            self.game_state.set_story_npc_state(npc_id, rescue_stage=stage, location_id=location_id)
            actor = self._actor(npc_id)
            if actor is not None:
                actor.location_id = location_id
                actor.community_member = stage == SETTLED_AT_FARM
                actor.managed_by_survivor_transport = stage != SETTLED_AT_FARM

    def _actor(self, story_id):
        return next(
            (
                npc
                for npc in getattr(self.npc_manager, "npcs", ())
                if getattr(npc, "story_id", None) == story_id
            ),
            None,
        )

    @staticmethod
    def _move_actor(actor, position):
        actor.pos.update(position)
        actor.rect.midbottom = (round(actor.pos.x), round(actor.pos.y))
        if hasattr(actor, "sync_collision_boxes"):
            actor.sync_collision_boxes()
        elif hasattr(actor, "collision_box"):
            actor.collision_box.center = actor.rect.center

    def update(self, dt):
        """Keep the freed group in a visible formation behind Hunter."""
        record = self.record()
        if record["stage"] not in {FOLLOWING_HUNTER, AT_EXTRACTION}:
            return
        self.sync_community()
        if record["stage"] == AT_EXTRACTION:
            extraction = record.get("extraction_position")
            if extraction is not None:
                for index, npc_id in enumerate(record["survivor_ids"]):
                    actor = self._actor(npc_id)
                    if actor is not None:
                        self._move_actor(actor, pygame.Vector2(extraction) + (index * 28 - 28, 18))
            return
        hunter = self._actor(record["hunter_id"])
        if hunter is None:
            return
        facing = pygame.Vector2(getattr(hunter, "direction", (0, 1)))
        if facing.length_squared() == 0:
            facing.update(0, 1)
        facing = facing.normalize()
        side = pygame.Vector2(-facing.y, facing.x)
        for index, npc_id in enumerate(record["survivor_ids"]):
            actor = self._actor(npc_id)
            if actor is None:
                continue
            target = pygame.Vector2(hunter.pos) - facing * (42 + index * 28) + side * ((index % 2) * 30 - 15)
            blend = min(1.0, max(0.0, float(dt)) * 5.0)
            self._move_actor(actor, pygame.Vector2(actor.pos).lerp(target, blend))

    def sync_community(self):
        if self.npc_manager is not None and hasattr(self.npc_manager, "spawn_recruited_survivors"):
            return self.npc_manager.spawn_recruited_survivors()
        return ()

    def set_npc_manager(self, npc_manager):
        self.npc_manager = npc_manager
        return self.sync_community()

"""GOAP-driven villagers and coastal market merchants."""

from __future__ import annotations

import pygame

from entities.npc import WanderingNPC
from gameplay.goap import DailySchedule, GOAPAction, GOAPPlanner
from data.crops import crop_definition, crop_seed_market_offers, is_crop_unlocked


MARKET_OFFERS = {
    "produce": (("apple", 4), ("tomato", 6), ("carrot", 5), ("corn", 5)),
    "grain": (("wheat", 4), ("barley", 4), ("oats", 4), ("rye", 5)),
    "fish_meat": (("fish", 8), ("meat", 10), ("egg", 4), ("shell", 3)),
}


class ScheduledNPC(WanderingNPC):
    """A villager who follows work, social, and rest destinations by time."""

    schedule = DailySchedule(((6, 17, "work"), (17, 22, "social")), default="rest")

    def __init__(self, *args, home_pos=None, work_pos=None, social_pos=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.home_pos = pygame.Vector2(home_pos or self.pos)
        self.work_pos = pygame.Vector2(work_pos or self.pos)
        self.social_pos = pygame.Vector2(social_pos or self.work_pos)
        self.daily_activity = None
        self.planner = GOAPPlanner()
        self.goap_actions = (
            GOAPAction("go_to_work", effects={"at_work": True, "at_home": False, "social": False}),
            GOAPAction("go_socialize", effects={"social": True, "at_home": False, "at_work": False}),
            GOAPAction("go_home", effects={"at_home": True, "at_work": False, "social": False}),
        )

    def _destination_for(self, activity):
        return {"work": self.work_pos, "social": self.social_pos, "rest": self.home_pos}[activity]

    def _route_to(self, destination):
        start = self.pathfinder.world_to_tile(self.pos)
        goal = self.pathfinder.world_to_tile(destination)
        path = self.pathfinder.find_full_path(start, goal)
        if len(path) > 1:
            self.path = path[1:]
            self.set_next_target()
        elif start == goal:
            self.pos.update(destination)
            self.rect.midbottom = (round(self.pos.x), round(self.pos.y))
            self.collision_box.center = self.rect.center
            self.begin_rest()

    def set_daily_activity(self, activity):
        if activity == self.daily_activity:
            return
        state = {
            "at_work": self.daily_activity == "work",
            "social": self.daily_activity == "social",
            "at_home": self.daily_activity == "rest",
        }
        goal_key = {"work": "at_work", "social": "social", "rest": "at_home"}[activity]
        plan = self.planner.plan(state, {goal_key: True}, self.goap_actions)
        if not plan:
            return
        self.daily_activity = activity
        self.special_animation = None
        self.special_timer = 0
        self._route_to(self._destination_for(activity))

    def update(self, dt, game_time=None):
        if not self.is_alive:
            return super().update(dt)
        hour = getattr(game_time, "hours", 12)
        self.set_daily_activity(self.schedule.goal_for_hour(hour))
        if self.target_tile is None:
            self.direction.update(0, 0)
            self.wait_timer = 999999
        previous = pygame.Vector2(self.pos)
        self.move(dt)
        if self.pos.distance_squared_to(previous) < 0.0001 and self.target_tile is not None:
            self.route_stall_timer += dt
            if self.route_stall_timer >= 2:
                self.begin_rest()
        else:
            self.route_stall_timer = 0
        self.update_status()
        self.animate(dt)
        self.tick_opacity(dt)


class MerchantNPC(ScheduledNPC):
    """A scheduled seller bound to one market stall."""

    schedule = DailySchedule(((6, 19, "work"),), default="rest")

    def __init__(self, *args, stall, **kwargs):
        self.stall = stall
        self.game_state = kwargs.pop("game_state", None)
        record = stall.record
        kwargs.setdefault("home_pos", record["rest_world_pos"])
        kwargs.setdefault("work_pos", record["merchant_world_pos"])
        kwargs.setdefault("social_pos", record["visitor_world_pos"])
        super().__init__(*args, **kwargs)
        self.name = "merchant"
        self.is_merchant = True
        self.offers = [
            {"item": item, "price": price, "stock": 8}
            for item, price in MARKET_OFFERS[self.stall.stall_kind]
        ]
        self.offers.extend(
            {"item": crop_id, "price": price, "stock": 8, "seed": True}
            for crop_id, price in crop_seed_market_offers(self.stall.stall_kind)
        )
        self.stall.merchant = self
        self.dialogue_name = self.role.replace("_", " ").title()

    def available_offers(self):
        """Expose crop produce/seeds only after its farming milestone."""
        existing_seed_ids = {
            offer["item"] for offer in self.offers if offer.get("seed")
        }
        self.offers.extend(
            {"item": crop_id, "price": price, "stock": 8, "seed": True}
            for crop_id, price in crop_seed_market_offers(self.stall.stall_kind)
            if crop_id not in existing_seed_ids
        )
        return [
            offer
            for offer in self.offers
            if crop_definition(offer["item"]) is None
            or is_crop_unlocked(offer["item"], self.game_state)
        ]

    @property
    def is_available(self):
        return self.is_alive and self.daily_activity == "work" and self.stall.is_open

    def set_daily_activity(self, activity):
        previous = self.daily_activity
        super().set_daily_activity(activity)
        if self.daily_activity == "work":
            self.stall.set_open(True)
        elif previous == "work" or self.daily_activity == "rest":
            self.stall.set_open(False)

    def update(self, dt, game_time=None):
        super().update(dt, game_time=game_time)
        if not self.is_alive:
            self.stall.set_open(False)

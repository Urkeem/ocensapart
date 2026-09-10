"""Small deterministic GOAP planner used by daily NPC schedules."""

from __future__ import annotations

from dataclasses import dataclass, field
import heapq
from itertools import count


@dataclass(frozen=True)
class GOAPAction:
    name: str
    preconditions: dict[str, bool] = field(default_factory=dict)
    effects: dict[str, bool] = field(default_factory=dict)
    cost: float = 1.0

    def can_run(self, state):
        return all(state.get(key, False) == value for key, value in self.preconditions.items())

    def apply(self, state):
        next_state = dict(state)
        next_state.update(self.effects)
        return next_state


class GOAPPlanner:
    def plan(self, state, goal, actions):
        if self._satisfies(state, goal):
            return []
        serial = count()
        queue = [(0.0, next(serial), dict(state), [])]
        best_cost = {self._key(state): 0.0}
        while queue:
            cost, _, current, plan = heapq.heappop(queue)
            if self._satisfies(current, goal):
                return plan
            for action in actions:
                if not action.can_run(current):
                    continue
                next_state = action.apply(current)
                next_cost = cost + max(0.0, float(action.cost))
                key = self._key(next_state)
                if next_cost >= best_cost.get(key, float("inf")):
                    continue
                best_cost[key] = next_cost
                heapq.heappush(
                    queue,
                    (next_cost, next(serial), next_state, [*plan, action]),
                )
        return []

    @staticmethod
    def _satisfies(state, goal):
        return all(state.get(key, False) == value for key, value in goal.items())

    @staticmethod
    def _key(state):
        return tuple(sorted(state.items()))


class DailySchedule:
    """Select a named goal from inclusive-start, exclusive-end periods."""

    def __init__(self, periods, default="rest"):
        self.periods = tuple(periods)
        self.default = default

    def goal_for_hour(self, hour):
        hour = int(hour) % 24
        for start, end, goal in self.periods:
            if start <= hour < end:
                return goal
        return self.default

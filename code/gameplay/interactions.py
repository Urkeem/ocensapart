"""Shared nearby-target selection for NPCs and future world interactables."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

import pygame

from data.locations import LOCATION_DEFINITIONS


@dataclass(frozen=True)
class InteractionTarget:
    target_id: str
    kind: str
    entity: object
    position: tuple[float, float]
    priority: int = 0
    prompt: str = "Interact"
    action: Callable[[], object] | None = None


class InteractionSystem:
    """Ranks targets from registered providers through one interaction key."""

    def __init__(self, npc_manager=None):
        self.npc_manager = npc_manager
        self.current_location_id = "player_farm"
        self._providers: list[Callable[[object, float], Iterable[InteractionTarget]]] = []

    def set_npc_manager(self, npc_manager):
        self.npc_manager = npc_manager

    def register_provider(self, provider):
        if provider not in self._providers:
            self._providers.append(provider)
        return lambda: self.unregister_provider(provider)

    def unregister_provider(self, provider):
        if provider not in self._providers:
            return False
        self._providers.remove(provider)
        return True

    def _npc_targets(self, player, max_distance):
        if self.npc_manager is None:
            return
        current_runtime = LOCATION_DEFINITIONS.get(
            self.current_location_id, {}
        ).get("runtime", "world")
        for npc in self.npc_manager.npcs:
            if getattr(npc, "is_enemy", False):
                continue
            if not getattr(npc, "is_alive", True):
                continue
            if getattr(npc, "is_merchant", False) and not npc.is_available:
                continue
            npc_location_id = getattr(npc, "location_id", "player_farm")
            npc_runtime = LOCATION_DEFINITIONS.get(
                npc_location_id, {}
            ).get("runtime", "world")
            if (
                npc_location_id != self.current_location_id
                and not (current_runtime == "world" and npc_runtime == "world")
            ):
                continue
            story_id = getattr(npc, "story_id", None)
            yield InteractionTarget(
                target_id=story_id or getattr(npc, "save_id", None) or f"npc:{id(npc)}",
                kind="npc",
                entity=npc,
                position=tuple(npc.rect.midbottom),
                priority=10 if story_id else 0,
            )

    def find_best(self, player, max_distance=112) -> InteractionTarget | None:
        player_center = pygame.Vector2(player.feet_collision_box.center)
        candidates = list(self._npc_targets(player, max_distance) or ())
        for provider in tuple(self._providers):
            candidates.extend(provider(player, max_distance) or ())
        in_range = [
            target
            for target in candidates
            if player_center.distance_to(target.position) <= max_distance
        ]
        if not in_range:
            return None
        return min(
            in_range,
            key=lambda target: (
                player_center.distance_to(target.position) - target.priority,
                target.target_id,
            ),
        )

    def activate(self, target: InteractionTarget | None):
        if target is None or target.action is None:
            return False
        return target.action()

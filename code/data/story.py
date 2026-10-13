"""Stable placements and display names for The Last Cure cast."""

STORY_NPC_PLACEMENTS = {
    "wife": {"name": "Wife", "location_id": "player_house_interior", "anchor": "wife"},
    "jim": {"name": "Jim", "location_id": "jim_home", "slot": 0},
    "lillian": {"name": "Lillian", "location_id": "lillian_home", "slot": 0},
    "alchemist": {"name": "Alchemist", "location_id": "alchemist_home", "slot": 0},
    "hunter": {"name": "Hunter", "location_id": "hunter_lodge", "slot": 0},
    "navigator": {"name": "Navigator", "location_id": "navigator_home", "slot": 0},
    "pirate": {"name": "Pirate", "location_id": "pirate_home", "slot": 0},
    "king": {"name": "King", "location_id": "castle_interior", "slot": 0},
    "queen": {"name": "Queen", "location_id": "castle_interior", "slot": 1},
    "princess": {"name": "Princess", "location_id": "hold_5", "slot": 0},
    "necromancer": {"name": "Necromancer", "location_id": "necromancer_citadel", "slot": 0},
}


INSTANCE_NPC_ANCHORS = (
    (112, 112),
    (208, 112),
    (112, 190),
    (208, 190),
    (160, 144),
)

WORLD_NPC_OFFSETS = (
    (-80, -48),
    (80, -48),
    (-128, 32),
    (128, 32),
    (0, 72),
)

# Authored districts are measured in chunks from the player's farm. These
# positions keep every major destination inside the 25-by-25 streamed kingdom
# while giving each character meaningful distance and a stable address.
KINGDOM_LOCATION_CHUNK_OFFSETS = {
    "village": (4, -1),
    "jim_home": (3, 1),
    "lillian_home": (5, 1),
    "alchemist_home": (6, -3),
    "hunter_lodge": (-5, -5),
    "navigator_home": (5, 5),
    "pirate_home": (7, 6),
    "castle_exterior": (0, -8),
}

"""Authored location layouts and source regions."""

FARMHOUSE_INTERIOR = {
    "id": "player_house_interior",
    "size": (320, 320),
    "scale": 2.0,
    "floor_asset": "graphics/sprites/character/house/floor.png",
    "wall_asset": "graphics/sprites/character/house/wall.png",
    "furniture_asset": "graphics/sprites/character/house/furniture.png",
    "collision_grid": 16,
    "anchors": {
        "bedside_spawn": (92, 136),
        "entry_spawn": (160, 286),
        "recovery_spawn": (92, 136),
        "wife": (62, 127),
        "bed": (125, 105),
        "exit": (160, 292),
    },
    "furniture_regions": {
        "empty_shelves": (6, 39, 22, 79),
        "bed": (103, 98, 43, 47),
        "rug": (13, 194, 68, 40),
        "bookshelf": (216, 199, 52, 55),
        "stool_upper": (261, 265, 19, 19),
        "stool_lower": (261, 287, 19, 19),
        "table": (283, 259, 29, 49),
    },
    "furniture": (
        {"id": "empty_shelves", "region": "empty_shelves", "position": (6, 39), "collision": (7, 46, 20, 70)},
        {"id": "bed", "region": "bed", "position": (103, 98), "collision": (104, 105, 41, 38)},
        {"id": "rug", "region": "rug", "position": (13, 194), "ground": True},
        {"id": "bookshelf", "region": "bookshelf", "position": (216, 199), "collision": (218, 204, 48, 48)},
        {"id": "stool_upper", "region": "stool_upper", "position": (261, 265), "collision": (263, 270, 15, 12)},
        {"id": "stool_lower", "region": "stool_lower", "position": (261, 287), "collision": (263, 292, 15, 12)},
        {"id": "table", "region": "table", "position": (283, 259), "collision": (285, 268, 25, 38)},
    ),
}


def _room(location_id, title, *, kind="interior", requirements=(), accent=(76, 84, 103)):
    """Create one authored room contract from the shared indoor art kit."""
    return {
        "id": location_id,
        "title": title,
        "kind": kind,
        "runtime": "instance",
        "size": FARMHOUSE_INTERIOR["size"],
        "floor_asset": FARMHOUSE_INTERIOR["floor_asset"],
        "wall_asset": FARMHOUSE_INTERIOR["wall_asset"],
        "furniture_asset": FARMHOUSE_INTERIOR["furniture_asset"],
        "collision_grid": FARMHOUSE_INTERIOR["collision_grid"],
        "accent": accent,
        "requirements": tuple(requirements),
        "anchors": {
            "entry_spawn": (160, 270),
            "exit": (160, 292),
            "encounter_spawn": (160, 96),
            "extraction": (160, 144),
        },
        "furniture_regions": {},
        "furniture": (),
    }


WORLD_LOCATIONS = {
    "player_farm": {
        "id": "player_farm",
        "title": "Home Farm",
        "kind": "authored_exterior",
        "runtime": "world",
        "requirements": (),
    },
    "village": {
        "id": "village",
        "title": "Ironveil Village",
        "kind": "authored_exterior",
        "runtime": "world",
        "requirements": (),
    },
    "castle_exterior": {
        "id": "castle_exterior",
        "title": "Ironveil Castle",
        "kind": "authored_exterior",
        "runtime": "world",
        "asset": "graphics/sprites/houses/tertiary/castle.png",
        "requirements": (
            {"type": "quest_completed", "quest_id": "prologue.first_defense", "reason": "Help defend the farm before seeking an audience at the castle."},
            {"type": "min_reputation", "amount": 5, "reason": "Earn 5 kingdom reputation so the castle guard will admit you."},
        ),
    },
    "jim_home": {
        "id": "jim_home", "title": "Jim's Forge", "kind": "authored_exterior",
        "runtime": "world", "asset": "graphics/sprites/houses/secondary/blacksmith.png", "requirements": (),
    },
    "lillian_home": {
        "id": "lillian_home", "title": "Lillian's Bakery", "kind": "authored_exterior",
        "runtime": "world", "asset": "graphics/sprites/houses/tertiary/bakerystewhouse.png", "requirements": (),
    },
    "alchemist_home": {
        "id": "alchemist_home", "title": "Alchemist's House", "kind": "authored_exterior",
        "runtime": "world", "asset": "graphics/sprites/houses/secondary/regular.png", "scale": 2.0, "requirements": (),
    },
    "hunter_lodge": {
        "id": "hunter_lodge", "title": "Hunter's Lodge", "kind": "authored_exterior",
        "runtime": "world", "asset": "graphics/sprites/houses/primary/stonehut2.png", "requirements": (),
    },
    "navigator_home": {
        "id": "navigator_home", "title": "Navigator's House", "kind": "authored_exterior",
        "runtime": "world", "asset": "graphics/sprites/houses/primary/fishermanhut.png", "requirements": (),
    },
    "pirate_home": {
        "id": "pirate_home", "title": "Pirate's Harbour House", "kind": "authored_exterior",
        "runtime": "world", "asset": "graphics/sprites/houses/tertiary/harbouroffice.png", "requirements": (),
    },
}


PROGRESSION_LOCATIONS = {
    "player_house_interior": {
        **FARMHOUSE_INTERIOR,
        "title": "Farmhouse",
        "kind": "authored_interior",
        "runtime": "instance",
        "requirements": (),
    },
    "castle_interior": _room(
        "castle_interior",
        "Ironveil Castle Hall",
        requirements=(
            {"type": "min_level", "level": 2, "reason": "Reach level 2 before entering the royal hall."},
            {"type": "min_reputation", "amount": 5, "reason": "Earn 5 kingdom reputation so the castle guard will admit you."},
        ),
        accent=(104, 83, 122),
    ),
    "alchemist_workspace": _room(
        "alchemist_workspace",
        "Alchemist's Workspace",
        requirements=(
            {"type": "flag", "flag_id": "story.alchemist_rescued", "reason": "Rescue the alchemist before visiting the workspace."},
        ),
        accent=(70, 111, 101),
    ),
    "hold_1": _room(
        "hold_1",
        "First Hold",
        kind="dungeon",
        requirements=(
            {"type": "min_level", "level": 3, "reason": "Reach level 3 before entering the First Hold."},
            {"type": "quest_completed", "quest_id": "prologue.first_defense", "reason": "Complete the farm defense before entering the holds."},
        ),
    ),
    "hold_2": _room(
        "hold_2",
        "Second Hold",
        kind="dungeon",
        requirements=(
            {"type": "min_level", "level": 4, "reason": "Reach level 4 before entering the Second Hold."},
            {"type": "flag", "flag_id": "holds.hold_1_complete", "reason": "Clear the First Hold before continuing."},
        ),
    ),
    "hold_3": _room(
        "hold_3",
        "Hunter's Hold",
        kind="dungeon",
        requirements=(
            {"type": "min_level", "level": 6, "reason": "Reach level 6 before entering Hunter's Hold."},
            {"type": "min_trust", "npc_id": "hunter", "amount": 25, "reason": "Earn 25 Trust with Hunter so he will guide you inside."},
        ),
    ),
    "hold_4": _room(
        "hold_4",
        "Hollow Crypt",
        kind="dungeon",
        requirements=(
            {"type": "min_level", "level": 8, "reason": "Reach level 8 before entering the Hollow Crypt."},
            {"type": "flag", "flag_id": "holds.hold_3_complete", "reason": "Clear Hunter's Hold before entering the crypt."},
            {"type": "key_item", "item_id": "hollow_crypt_key", "reason": "Find the Hollow Crypt Key before trying this door."},
        ),
    ),
    "hold_5": _room(
        "hold_5",
        "Royal Prison",
        kind="dungeon",
        requirements=(
            {"type": "min_level", "level": 10, "reason": "Reach level 10 before entering the Royal Prison."},
            {"type": "flag", "flag_id": "holds.hold_4_complete", "reason": "Clear the Hollow Crypt before entering the prison."},
            {"type": "key_item", "item_id": "ironveil_key", "reason": "Find the Ironveil Key before trying this door."},
        ),
    ),
    "necromancer_citadel": _room(
        "necromancer_citadel",
        "Necromancer's Citadel",
        kind="dungeon",
        requirements=(
            {"type": "min_level", "level": 12, "reason": "Reach level 12 before sailing to the citadel."},
            {"type": "flag", "flag_id": "holds.hold_5_complete", "reason": "Free the Royal Prison before confronting the necromancer."},
            {"type": "transport_unlock", "transport_id": "pirate_ship", "reason": "Secure Pirate's ship before crossing to the citadel."},
        ),
        accent=(113, 58, 78),
    ),
}


LOCATION_DEFINITIONS = {**WORLD_LOCATIONS, **PROGRESSION_LOCATIONS}


# World-edge/door connections. The interaction layer may place these at authored
# anchors now and swap in full exterior maps later without changing save IDs.
LOCATION_CONNECTIONS = {
    "player_farm": (
        {"id": "farm-road-village", "target": "village", "prompt": "Enter Ironveil Village"},
    ),
    "village": (
        {"id": "village-road-farm", "target": "player_farm", "prompt": "Enter the farm district"},
        {"id": "village-road-castle", "target": "castle_exterior", "prompt": "Enter the castle district"},
        {"id": "village-road-jim", "target": "jim_home", "prompt": "Visit Jim's forge"},
        {"id": "village-road-lillian", "target": "lillian_home", "prompt": "Visit Lillian's bakery"},
        {"id": "village-road-alchemist", "target": "alchemist_home", "prompt": "Visit the alchemist's house"},
        {"id": "village-road-hunter", "target": "hunter_lodge", "prompt": "Visit Hunter's lodge"},
        {"id": "village-road-navigator", "target": "navigator_home", "prompt": "Visit Navigator's house"},
        {"id": "village-road-pirate", "target": "pirate_home", "prompt": "Visit Pirate's harbour house"},
        {"id": "village-hold-road", "target": "hold_1", "prompt": "Travel to the First Hold", "offset": (80, -144)},
    ),
    "castle_exterior": (
        {"id": "castle-road-village", "target": "village", "prompt": "Return to Ironveil Village", "offset": (-180, 64)},
        {"id": "castle-main-door", "target": "castle_interior", "prompt": "Enter the castle", "offset": (0, -48)},
    ),
    "jim_home": ({"id": "jim-road-village", "target": "village", "prompt": "Enter Ironveil Village"},),
    "lillian_home": ({"id": "lillian-road-village", "target": "village", "prompt": "Enter Ironveil Village"},),
    "alchemist_home": ({"id": "alchemist-road-village", "target": "village", "prompt": "Enter Ironveil Village"},),
    "hunter_lodge": ({"id": "hunter-road-village", "target": "village", "prompt": "Enter Ironveil Village"},),
    "navigator_home": ({"id": "navigator-road-village", "target": "village", "prompt": "Enter Ironveil Village"},),
    "pirate_home": ({"id": "pirate-road-village", "target": "village", "prompt": "Enter Ironveil Village"},),
    "hold_1": (
        {"id": "hold-1-depths", "target": "hold_2", "prompt": "Descend to the Second Hold", "anchor": "encounter_spawn"},
    ),
    "hold_2": (
        {"id": "hold-2-depths", "target": "hold_3", "prompt": "Follow the trail to Hunter's Hold", "anchor": "encounter_spawn"},
    ),
    "hold_3": (
        {"id": "hold-3-depths", "target": "hold_4", "prompt": "Unlock the Hollow Crypt", "anchor": "encounter_spawn"},
    ),
    "hold_4": (
        {"id": "hold-4-depths", "target": "hold_5", "prompt": "Open the Royal Prison route", "anchor": "encounter_spawn"},
    ),
    "hold_5": (
        {"id": "hold-5-citadel-route", "target": "necromancer_citadel", "prompt": "Sail to the Necromancer's Citadel", "anchor": "encounter_spawn"},
    ),
}

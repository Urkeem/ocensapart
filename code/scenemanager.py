"""Scene templates and layout helpers for generated neighborhoods."""

from __future__ import annotations

import random

from entities.house import HOUSE_SCALE


HOUSE_FOOTPRINT_TILES = (HOUSE_SCALE, 3)
SCENES_PER_CHUNK = 6

HOUSE_CATEGORY_FOOTPRINTS = {
    "primary": (3, 4),
    "secondary": (5, 5),
    "tertiary": (6, 6),
}

HOUSE_SCENE_TEMPLATES = [
    {
        "name": "farmstead",
        "weight": 4,
        "size": (13, 9),
        "fences": [
            {"rect": (0, 0, 13, 9), "gates": [(6, 8)]},
        ],
        "farm_plots": [
            {"rect": (6, 1, 3, 4)},
        ],
        "houses": [
            {"category": "primary", "prefer": "farmhouse", "offset": (1, 1), "role": "farmhouse"},
            {"category": "primary", "prefer": "hut", "offset": (9, 3), "role": "worker_home"},
        ],
        "props": [
            {"asset": "props/general/hay.png", "offset": (1, 6), "prop_type": "hay"},
            {"asset": "props/general/wheelbarrow.png", "offset": (4, 7), "prop_type": "wheelbarrow", "blocks": True},
            {"asset": "props/general/barrel.png", "offset": (7, 7), "prop_type": "barrel", "blocks": True},
            {"asset": "props/crates/1.png", "offset": (11, 7), "prop_type": "crate", "blocks": True},
            {"asset": "props/lanterns/1.png", "offset": (6, 5), "prop_type": "lantern"},
            {"asset": "props/flowers_pot_fenced/flowersmall.png#0", "offset": (2, 7), "prop_type": "flower"},
        ],
    },
    {
        "name": "homestead_training_yard",
        "weight": 3,
        "size": (18, 12),
        "houses": [
            {"category": "primary", "prefer": "farmhouse", "offset": (4, 1), "role": "farmhouse"},
            {"category": "primary", "prefer": "woodstall", "offset": (12, 2), "role": "yard_stall"},
        ],
        "props": [
            {"asset": "props/general/barrel.png", "offset": (2, 7), "prop_type": "barrel", "blocks": True},
            {"asset": "props/buckets/buckets.png#0", "offset": (3, 7), "prop_type": "bucket"},
            {"asset": "props/general/hay.png", "offset": (8, 7), "prop_type": "hay"},
            {"asset": "props/trainingyard/armsdisplay_empty.png", "offset": (11, 7), "prop_type": "training_prop", "blocks": True},
            {"asset": "props/trainingyard/trainfigure1.png", "offset": (13, 7), "prop_type": "training_prop", "blocks": True},
            {"asset": "props/trainingyard/trainfigure2.png", "offset": (15, 7), "prop_type": "training_prop", "blocks": True},
            {"asset": "props/crates/1.png", "offset": (6, 8), "prop_type": "crate", "blocks": True},
            {"asset": "props/lanterns/1.png", "offset": (9, 6), "prop_type": "lantern"},
        ],
        "trees": [
            {"species": "oak", "offset": (0, 1), "size": 1.05},
            {"species": "birch", "offset": (2, 3), "size": 0.95},
            {"species": "apple", "offset": (1, 10), "size": 1.0},
            {"species": "oak", "offset": (16, 1), "size": 1.1},
        ],
    },
    {
        "name": "market_row",
        "weight": 3,
        "houses": [
            {"category": "secondary", "prefer": "merchanthouse", "offset": (1, 1), "role": "merchant"},
            {"category": "tertiary", "prefer": "bakerystewhouse", "offset": (9, 1), "role": "bakery"},
        ],
        "props": [
            {"asset": "props/crates/1.png", "offset": (4, 7), "prop_type": "crate", "blocks": True},
            {"asset": "props/crates/5.png", "offset": (5, 7), "prop_type": "crate", "blocks": True},
            {"asset": "props/general/sackopen.png", "offset": (7, 7), "prop_type": "sack"},
            {"asset": "props/general/signpost.png", "offset": (0, 7), "prop_type": "signpost", "blocks": True},
            {"asset": "props/pots/potsmeduim.png#1", "offset": (12, 7), "prop_type": "pot", "blocks": True},
            {"asset": "props/flowers_pot_fenced/flowerthin.png#1", "offset": (13, 7), "prop_type": "flower"},
            {"asset": "props/lanterns/1.png", "offset": (8, 6), "prop_type": "lantern"},
        ],
    },
    {
        "name": "harbor_service",
        "weight": 3,
        "houses": [
            {"category": "secondary", "prefer": "fishermanhut", "offset": (1, 2), "role": "fisherman"},
            {"category": "tertiary", "prefer": "harbouroffice", "offset": (8, 1), "role": "harbor_office"},
        ],
        "props": [
            {"asset": "props/crates/3.png", "offset": (2, 7), "prop_type": "crate", "blocks": True},
            {"asset": "props/crates/7.png", "offset": (3, 7), "prop_type": "crate", "blocks": True},
            {"asset": "props/general/barrel.png", "offset": (5, 7), "prop_type": "barrel", "blocks": True},
            {"asset": "props/buckets/buckets.png#0", "offset": (6, 7), "prop_type": "bucket"},
            {"asset": "props/lanterns/1.png", "offset": (11, 7), "prop_type": "lantern"},
        ],
    },
    {
        "name": "training_yard",
        "weight": 2,
        "houses": [
            {"category": "primary", "prefer": "woodstall", "offset": (1, 1), "role": "stall"},
            {"category": "tertiary", "prefer": "fort", "offset": (8, 1), "role": "fort"},
        ],
        "props": [
            {"asset": "props/trainingyard/armsdisplay_empty.png", "offset": (2, 7), "prop_type": "training_prop", "blocks": True},
            {"asset": "props/trainingyard/arrowtrain.png", "offset": (4, 7), "prop_type": "training_prop", "blocks": True},
            {"asset": "props/trainingyard/trainfigure2.png", "offset": (6, 7), "prop_type": "training_prop", "blocks": True},
            {"asset": "props/trainingyard/tent.png", "offset": (10, 7), "prop_type": "tent", "blocks": True},
            {"asset": "props/crates/9.png", "offset": (14, 7), "prop_type": "crate", "blocks": True},
        ],
    },
    {
        "name": "civic_corner",
        "weight": 2,
        "houses": [
            {"category": "tertiary", "prefer": "portcouncilchamber", "offset": (1, 1), "role": "council"},
            {"category": "secondary", "prefer": "secondaryhouse", "offset": (11, 2), "role": "quest_house"},
        ],
        "props": [
            {"asset": "props/general/signpost.png", "offset": (0, 8), "prop_type": "signpost", "blocks": True},
            {"asset": "props/flowers_pot_fenced/flowerlarge.png#2", "offset": (5, 8), "prop_type": "flower"},
            {"asset": "props/pots/potsthin.png#2", "offset": (8, 8), "prop_type": "pot", "blocks": True},
            {"asset": "props/lanterns/1.png", "offset": (10, 8), "prop_type": "lantern"},
            {"asset": "props/crates/10.png", "offset": (15, 8), "prop_type": "crate", "blocks": True},
        ],
    },
    {
        "name": "blacksmith_yard",
        "weight": 3,
        "houses": [
            {"category": "secondary", "prefer": "blacksmith", "offset": (1, 1), "role": "blacksmith"},
            {"category": "primary", "prefer": "woodstall", "offset": (10, 3), "role": "supply_stall"},
        ],
        "props": [
            {"asset": "props/trainingyard/armsdisplay2.png", "offset": (1, 7), "prop_type": "training_prop", "blocks": True},
            {"asset": "props/trainingyard/armsdisplay3.png", "offset": (3, 7), "prop_type": "training_prop", "blocks": True},
            {"asset": "props/crates/4.png", "offset": (6, 7), "prop_type": "crate", "blocks": True},
            {"asset": "props/general/barrel.png", "offset": (8, 7), "prop_type": "barrel", "blocks": True},
            {"asset": "props/lanterns/1.png", "offset": (9, 6), "prop_type": "lantern"},
        ],
    },
    {
        "name": "tavern_square",
        "weight": 2,
        "houses": [
            {"category": "tertiary", "prefer": "tavern", "offset": (1, 1), "role": "tavern"},
            {"category": "primary", "prefer": "thatchhut", "offset": (11, 4), "role": "lodging"},
        ],
        "props": [
            {"asset": "props/general/barrel.png", "offset": (4, 8), "prop_type": "barrel", "blocks": True},
            {"asset": "props/general/sackopen.png", "offset": (6, 8), "prop_type": "sack"},
            {"asset": "props/crates/8.png", "offset": (8, 8), "prop_type": "crate", "blocks": True},
            {"asset": "props/pots/potsmeduim.png#0", "offset": (10, 8), "prop_type": "pot", "blocks": True},
            {"asset": "props/flowers_pot_fenced/flowermeduim.png#1", "offset": (12, 8), "prop_type": "flower"},
            {"asset": "props/lanterns/1.png", "offset": (7, 7), "prop_type": "lantern"},
        ],
    },
    {
        "name": "warehouse_lane",
        "weight": 3,
        "houses": [
            {"category": "tertiary", "prefer": "warehouse", "offset": (1, 1), "role": "warehouse"},
            {"category": "secondary", "prefer": "merchanthouse", "offset": (10, 2), "role": "trader"},
        ],
        "props": [
            {"asset": "props/crates/1.png", "offset": (1, 8), "prop_type": "crate", "blocks": True},
            {"asset": "props/crates/6.png", "offset": (2, 8), "prop_type": "crate", "blocks": True},
            {"asset": "props/crates/10.png", "offset": (3, 8), "prop_type": "crate", "blocks": True},
            {"asset": "props/general/barrel.png", "offset": (5, 8), "prop_type": "barrel", "blocks": True},
            {"asset": "props/buckets/buckets.png#1", "offset": (7, 8), "prop_type": "bucket"},
            {"asset": "props/lanterns/1.png", "offset": (9, 7), "prop_type": "lantern"},
        ],
    },
    {
        "name": "pawnshop_alley",
        "weight": 2,
        "houses": [
            {"category": "tertiary", "prefer": "pawnshop", "offset": (1, 1), "role": "pawnshop"},
            {"category": "primary", "prefer": "abandoned", "offset": (10, 3), "role": "abandoned_home"},
        ],
        "props": [
            {"asset": "props/general/signpost.png", "offset": (0, 8), "prop_type": "signpost", "blocks": True},
            {"asset": "props/crates/5.png", "offset": (5, 8), "prop_type": "crate", "blocks": True},
            {"asset": "props/general/sackopen.png", "offset": (7, 8), "prop_type": "sack"},
            {"asset": "props/pots/potsthin.png#0", "offset": (9, 8), "prop_type": "pot", "blocks": True},
            {"asset": "props/flowers_pot_fenced/flowerthin.png#2", "offset": (12, 8), "prop_type": "flower"},
        ],
    },
    {
        "name": "fisher_row",
        "weight": 4,
        "houses": [
            {"category": "secondary", "prefer": "fishermanhut", "offset": (1, 2), "role": "fisher_home"},
            {"category": "primary", "prefer": "beachcabin", "offset": (8, 3), "role": "beach_cabin"},
            {"category": "primary", "prefer": "hut", "offset": (14, 4), "role": "dock_worker_home"},
        ],
        "props": [
            {"asset": "props/crates/1.png", "offset": (2, 8), "prop_type": "crate", "blocks": True},
            {"asset": "props/buckets/buckets.png#2", "offset": (4, 8), "prop_type": "bucket"},
            {"asset": "props/general/barrel.png", "offset": (6, 8), "prop_type": "barrel", "blocks": True},
            {"asset": "props/lanterns/1.png", "offset": (10, 8), "prop_type": "lantern"},
        ],
    },
    {
        "name": "garden_homes",
        "weight": 3,
        "houses": [
            {"category": "primary", "prefer": "simplehouse", "offset": (1, 1), "role": "home"},
            {"category": "primary", "prefer": "stonehut", "offset": (8, 2), "role": "home"},
        ],
        "props": [
            {"asset": "props/flowers_pot_fenced/flowersmall.png#0", "offset": (1, 7), "prop_type": "flower"},
            {"asset": "props/flowers_pot_fenced/flowersmall.png#1", "offset": (2, 7), "prop_type": "flower"},
            {"asset": "props/flowers_pot_fenced/flowerthin.png#0", "offset": (4, 7), "prop_type": "flower"},
            {"asset": "props/flowers_pot_fenced/flowermeduim.png#2", "offset": (9, 7), "prop_type": "flower"},
            {"asset": "props/pots/potsmeduim.png#2", "offset": (11, 7), "prop_type": "pot", "blocks": True},
            {"asset": "props/lanterns/1.png", "offset": (6, 7), "prop_type": "lantern"},
        ],
    },
    {
        "name": "butcher_stop",
        "weight": 2,
        "houses": [
            {"category": "secondary", "prefer": "secondaryhouse", "offset": (1, 1), "role": "butcher"},
            {"category": "primary", "prefer": "woodstall", "offset": (9, 3), "role": "market_stall"},
        ],
        "props": [
            {"asset": "props/butcher/hide.png", "offset": (2, 7), "prop_type": "butcher_prop", "blocks": True},
            {"asset": "props/butcher/tools.png", "offset": (4, 7), "prop_type": "butcher_prop", "blocks": True},
            {"asset": "props/general/barrel.png", "offset": (6, 7), "prop_type": "barrel", "blocks": True},
            {"asset": "props/crates/7.png", "offset": (11, 7), "prop_type": "crate", "blocks": True},
            {"asset": "props/lanterns/1.png", "offset": (8, 6), "prop_type": "lantern"},
        ],
    },
    {
        "name": "counting_house_block",
        "weight": 2,
        "houses": [
            {"category": "tertiary", "prefer": "countinghouse", "offset": (1, 1), "role": "counting_house"},
            {"category": "secondary", "prefer": "merchanthouse", "offset": (10, 2), "role": "merchant"},
        ],
        "props": [
            {"asset": "props/general/signpost.png", "offset": (0, 8), "prop_type": "signpost", "blocks": True},
            {"asset": "props/crates/4.png", "offset": (6, 8), "prop_type": "crate", "blocks": True},
            {"asset": "props/crates/9.png", "offset": (7, 8), "prop_type": "crate", "blocks": True},
            {"asset": "props/pots/potsmeduim.png#2", "offset": (9, 8), "prop_type": "pot", "blocks": True},
            {"asset": "props/lanterns/1.png", "offset": (11, 8), "prop_type": "lantern"},
        ],
    },
    {
        "name": "quiet_huts",
        "weight": 5,
        "houses": [
            {"category": "primary", "prefer": "hut", "offset": (1, 1), "role": "home"},
            {"category": "primary", "prefer": "thatchhut", "offset": (7, 2), "role": "home"},
            {"category": "primary", "prefer": "stonehut", "offset": (13, 3), "role": "home"},
        ],
        "props": [
            {"asset": "props/general/hay.png", "offset": (1, 7), "prop_type": "hay"},
            {"asset": "props/buckets/buckets.png#3", "offset": (4, 7), "prop_type": "bucket"},
            {"asset": "props/pots/potsthin.png#1", "offset": (8, 7), "prop_type": "pot", "blocks": True},
            {"asset": "props/flowers_pot_fenced/flowerlarge.png#1", "offset": (11, 7), "prop_type": "flower"},
            {"asset": "props/lanterns/1.png", "offset": (15, 7), "prop_type": "lantern"},
        ],
    },
    {
        "name": "council_storage",
        "weight": 1,
        "houses": [
            {"category": "tertiary", "prefer": "portcouncilchamber", "offset": (1, 1), "role": "council"},
            {"category": "tertiary", "prefer": "warehouse", "offset": (10, 1), "role": "records_storage"},
        ],
        "props": [
            {"asset": "props/crates/1.png", "offset": (3, 8), "prop_type": "crate", "blocks": True},
            {"asset": "props/crates/1.png", "offset": (4, 8), "prop_type": "crate", "blocks": True},
            {"asset": "props/general/signpost.png", "offset": (8, 8), "prop_type": "signpost", "blocks": True},
            {"asset": "props/pots/potsmeduim.png#0", "offset": (10, 8), "prop_type": "pot", "blocks": True},
            {"asset": "props/lanterns/1.png", "offset": (12, 8), "prop_type": "lantern"},
        ],
    },
    {
        "name": "bakery_lane",
        "weight": 3,
        "houses": [
            {"category": "tertiary", "prefer": "bakerystewhouse", "offset": (1, 1), "role": "bakery"},
            {"category": "primary", "prefer": "woodstall", "offset": (10, 3), "role": "bread_stall"},
            {"category": "secondary", "prefer": "secondaryhouse", "offset": (15, 2), "role": "baker_home"},
        ],
        "props": [
            {"asset": "props/general/sackopen.png", "offset": (2, 8), "prop_type": "sack"},
            {"asset": "props/general/sackopen.png", "offset": (4, 8), "prop_type": "sack"},
            {"asset": "props/crates/6.png", "offset": (6, 8), "prop_type": "crate", "blocks": True},
            {"asset": "props/pots/potsmeduim.png#1", "offset": (9, 8), "prop_type": "pot", "blocks": True},
            {"asset": "props/flowers_pot_fenced/flowermeduim.png#0", "offset": (12, 8), "prop_type": "flower"},
            {"asset": "props/lanterns/1.png", "offset": (14, 8), "prop_type": "lantern"},
        ],
    },
    {
        "name": "fort_gate",
        "weight": 2,
        "houses": [
            {"category": "tertiary", "prefer": "fort", "offset": (1, 1), "role": "fort"},
            {"category": "primary", "prefer": "woodstall", "offset": (11, 4), "role": "guard_post"},
            {"category": "primary", "prefer": "stonehut", "offset": (16, 4), "role": "guard_home"},
        ],
        "props": [
            {"asset": "props/trainingyard/armsdisplay_empty.png", "offset": (2, 9), "prop_type": "training_prop", "blocks": True},
            {"asset": "props/trainingyard/arrowtrain2.png", "offset": (4, 9), "prop_type": "training_prop", "blocks": True},
            {"asset": "props/trainingyard/trainfigure1.png", "offset": (6, 9), "prop_type": "training_prop", "blocks": True},
            {"asset": "props/crates/8.png", "offset": (9, 9), "prop_type": "crate", "blocks": True},
            {"asset": "props/lanterns/1.png", "offset": (13, 9), "prop_type": "lantern"},
        ],
    },
    {
        "name": "merchant_court",
        "weight": 3,
        "houses": [
            {"category": "secondary", "prefer": "merchanthouse1", "offset": (1, 1), "role": "merchant"},
            {"category": "secondary", "prefer": "merchanthouse2", "offset": (10, 2), "role": "merchant"},
            {"category": "primary", "prefer": "woodstall", "offset": (18, 5), "role": "stall"},
        ],
        "props": [
            {"asset": "props/crates/1.png", "offset": (3, 9), "prop_type": "crate", "blocks": True},
            {"asset": "props/crates/3.png", "offset": (5, 9), "prop_type": "crate", "blocks": True},
            {"asset": "props/general/barrel.png", "offset": (7, 9), "prop_type": "barrel", "blocks": True},
            {"asset": "props/general/signpost.png", "offset": (9, 9), "prop_type": "signpost", "blocks": True},
            {"asset": "props/pots/potsthin.png#2", "offset": (12, 9), "prop_type": "pot", "blocks": True},
            {"asset": "props/lanterns/1.png", "offset": (15, 9), "prop_type": "lantern"},
        ],
    },
    {
        "name": "harbor_warehouses",
        "weight": 2,
        "houses": [
            {"category": "tertiary", "prefer": "warehouse1", "offset": (1, 1), "role": "warehouse"},
            {"category": "tertiary", "prefer": "warehouse3", "offset": (10, 2), "role": "warehouse"},
            {"category": "tertiary", "prefer": "harbouroffice", "offset": (17, 2), "role": "harbor_office"},
        ],
        "props": [
            {"asset": "props/crates/1.png", "offset": (2, 9), "prop_type": "crate", "blocks": True},
            {"asset": "props/crates/4.png", "offset": (3, 9), "prop_type": "crate", "blocks": True},
            {"asset": "props/crates/7.png", "offset": (5, 9), "prop_type": "crate", "blocks": True},
            {"asset": "props/general/barrel.png", "offset": (7, 9), "prop_type": "barrel", "blocks": True},
            {"asset": "props/buckets/buckets.png#0", "offset": (9, 9), "prop_type": "bucket"},
            {"asset": "props/lanterns/1.png", "offset": (13, 9), "prop_type": "lantern"},
        ],
    },
    {
        "name": "flower_cottages",
        "weight": 4,
        "houses": [
            {"category": "primary", "prefer": "simplehouse", "offset": (1, 1), "role": "home"},
            {"category": "primary", "prefer": "thatchhut", "offset": (8, 2), "role": "home"},
            {"category": "secondary", "prefer": "secondaryhouse2", "offset": (14, 1), "role": "gardener_home"},
        ],
        "props": [
            {"asset": "props/flowers_pot_fenced/flowerthin.png#0", "offset": (1, 8), "prop_type": "flower"},
            {"asset": "props/flowers_pot_fenced/flowerthin.png#1", "offset": (2, 8), "prop_type": "flower"},
            {"asset": "props/flowers_pot_fenced/flowerlarge.png#0", "offset": (4, 8), "prop_type": "flower"},
            {"asset": "props/flowers_pot_fenced/flowerlarge.png#2", "offset": (6, 8), "prop_type": "flower"},
            {"asset": "props/flowers_pot_fenced/flowerfenced.png#0", "offset": (9, 8), "prop_type": "flower", "blocks": True},
            {"asset": "props/pots/potsmeduim.png#0", "offset": (13, 8), "prop_type": "pot", "blocks": True},
            {"asset": "props/pots/potsthin.png#1", "offset": (15, 8), "prop_type": "pot", "blocks": True},
        ],
    },
    {
        "name": "ruined_edge",
        "weight": 3,
        "houses": [
            {"category": "primary", "prefer": "abandoned", "offset": (1, 1), "role": "abandoned_home"},
            {"category": "primary", "prefer": "stonehut2", "offset": (10, 3), "role": "old_home"},
        ],
        "props": [
            {"asset": "props/crates/10.png", "offset": (2, 8), "prop_type": "crate", "blocks": True},
            {"asset": "props/general/sackopen.png", "offset": (4, 8), "prop_type": "sack"},
            {"asset": "props/buckets/buckets.png#1", "offset": (6, 8), "prop_type": "bucket"},
            {"asset": "props/pots/potsthin.png#0", "offset": (8, 8), "prop_type": "pot", "blocks": True},
            {"asset": "props/flowers_pot_fenced/flowersmall.png#2", "offset": (11, 8), "prop_type": "flower"},
        ],
    },
    {
        "name": "inn_and_stables",
        "weight": 2,
        "houses": [
            {"category": "tertiary", "prefer": "tavern", "offset": (1, 1), "role": "inn"},
            {"category": "primary", "prefer": "farmhouse", "offset": (12, 3), "role": "stable_house"},
            {"category": "primary", "prefer": "hut", "offset": (18, 4), "role": "stable_hand_home"},
        ],
        "props": [
            {"asset": "props/general/hay.png", "offset": (3, 9), "prop_type": "hay"},
            {"asset": "props/general/wheelbarrow.png", "offset": (5, 9), "prop_type": "wheelbarrow", "blocks": True},
            {"asset": "props/general/barrel.png", "offset": (8, 9), "prop_type": "barrel", "blocks": True},
            {"asset": "props/crates/5.png", "offset": (10, 9), "prop_type": "crate", "blocks": True},
            {"asset": "props/lanterns/1.png", "offset": (14, 9), "prop_type": "lantern"},
        ],
    },
    {
        "name": "fisher_market",
        "weight": 3,
        "houses": [
            {"category": "secondary", "prefer": "fishermanhut", "offset": (1, 2), "role": "fisher_home"},
            {"category": "secondary", "prefer": "merchanthouse3", "offset": (8, 1), "role": "fish_merchant"},
            {"category": "primary", "prefer": "beachcabin", "offset": (17, 4), "role": "shore_home"},
        ],
        "props": [
            {"asset": "props/buckets/buckets.png#2", "offset": (2, 9), "prop_type": "bucket"},
            {"asset": "props/crates/3.png", "offset": (4, 9), "prop_type": "crate", "blocks": True},
            {"asset": "props/crates/6.png", "offset": (6, 9), "prop_type": "crate", "blocks": True},
            {"asset": "props/general/barrel.png", "offset": (8, 9), "prop_type": "barrel", "blocks": True},
            {"asset": "props/lanterns/1.png", "offset": (12, 9), "prop_type": "lantern"},
        ],
    },
    {
        "name": "council_plaza",
        "weight": 1,
        "houses": [
            {"category": "tertiary", "prefer": "portcouncilchamber", "offset": (1, 1), "role": "council"},
            {"category": "tertiary", "prefer": "countinghouse", "offset": (10, 2), "role": "treasury"},
            {"category": "secondary", "prefer": "secondaryhouse", "offset": (17, 4), "role": "clerk_home"},
        ],
        "props": [
            {"asset": "props/general/signpost.png", "offset": (3, 9), "prop_type": "signpost", "blocks": True},
            {"asset": "props/pots/potsmeduim.png#0", "offset": (6, 9), "prop_type": "pot", "blocks": True},
            {"asset": "props/pots/potsmeduim.png#2", "offset": (8, 9), "prop_type": "pot", "blocks": True},
            {"asset": "props/flowers_pot_fenced/flowerlarge.png#1", "offset": (10, 9), "prop_type": "flower"},
            {"asset": "props/lanterns/1.png", "offset": (13, 9), "prop_type": "lantern"},
        ],
    },
    {
        "name": "stall_cluster",
        "weight": 4,
        "houses": [
            {"category": "primary", "prefer": "woodstall1", "offset": (1, 2), "role": "stall"},
            {"category": "primary", "prefer": "woodstall2", "offset": (7, 2), "role": "stall"},
            {"category": "primary", "prefer": "woodstall3", "offset": (13, 1), "role": "stall"},
        ],
        "props": [
            {"asset": "props/crates/1.png", "offset": (2, 8), "prop_type": "crate", "blocks": True},
            {"asset": "props/crates/1.png", "offset": (4, 8), "prop_type": "crate", "blocks": True},
            {"asset": "props/general/sackopen.png", "offset": (6, 8), "prop_type": "sack"},
            {"asset": "props/general/barrel.png", "offset": (9, 8), "prop_type": "barrel", "blocks": True},
            {"asset": "props/pots/potsthin.png#2", "offset": (12, 8), "prop_type": "pot", "blocks": True},
            {"asset": "props/lanterns/1.png", "offset": (15, 8), "prop_type": "lantern"},
        ],
    },
    {
        "name": "coastal_fort_watch",
        "tags": {"coastal", "fort"},
        "weight": 5,
        "houses": [
            {"category": "tertiary", "prefer": "fort", "offset": (1, 1), "role": "coastal_fort"},
            {"category": "primary", "prefer": "woodstall", "offset": (10, 4), "role": "watch_post"},
            {"category": "primary", "prefer": "stonehut", "offset": (15, 4), "role": "guard_home"},
        ],
        "props": [
            {"asset": "props/trainingyard/arrowtrain2.png", "offset": (2, 9), "prop_type": "training_prop", "blocks": True},
            {"asset": "props/trainingyard/trainfigure3.png", "offset": (4, 9), "prop_type": "training_prop", "blocks": True},
            {"asset": "props/trainingyard/armsdisplay_empty.png", "offset": (6, 9), "prop_type": "training_prop", "blocks": True},
            {"asset": "props/crates/9.png", "offset": (9, 9), "prop_type": "crate", "blocks": True},
            {"asset": "props/lanterns/1.png", "offset": (12, 9), "prop_type": "lantern"},
        ],
    },
    {
        "name": "beach_warehouse_row",
        "tags": {"coastal", "warehouse"},
        "weight": 6,
        "houses": [
            {"category": "tertiary", "prefer": "warehouse1", "offset": (1, 1), "role": "warehouse"},
            {"category": "tertiary", "prefer": "warehouse2", "offset": (10, 1), "role": "warehouse"},
            {"category": "primary", "prefer": "beachcabin", "offset": (19, 5), "role": "shore_keeper"},
        ],
        "props": [
            {"asset": "props/crates/1.png", "offset": (2, 9), "prop_type": "crate", "blocks": True},
            {"asset": "props/crates/4.png", "offset": (4, 9), "prop_type": "crate", "blocks": True},
            {"asset": "props/crates/8.png", "offset": (6, 9), "prop_type": "crate", "blocks": True},
            {"asset": "props/general/barrel.png", "offset": (8, 9), "prop_type": "barrel", "blocks": True},
            {"asset": "props/buckets/buckets.png#3", "offset": (11, 9), "prop_type": "bucket"},
            {"asset": "props/lanterns/1.png", "offset": (14, 9), "prop_type": "lantern"},
        ],
    },
    {
        "name": "harbor_customs_yard",
        "tags": {"coastal", "warehouse", "harbor"},
        "weight": 5,
        "houses": [
            {"category": "tertiary", "prefer": "harbouroffice", "offset": (1, 1), "role": "customs_office"},
            {"category": "tertiary", "prefer": "warehouse3", "offset": (10, 2), "role": "bonded_warehouse"},
            {"category": "secondary", "prefer": "merchanthouse", "offset": (17, 4), "role": "import_merchant"},
        ],
        "props": [
            {"asset": "props/general/signpost.png", "offset": (1, 9), "prop_type": "signpost", "blocks": True},
            {"asset": "props/crates/1.png", "offset": (4, 9), "prop_type": "crate", "blocks": True},
            {"asset": "props/crates/6.png", "offset": (6, 9), "prop_type": "crate", "blocks": True},
            {"asset": "props/general/barrel.png", "offset": (8, 9), "prop_type": "barrel", "blocks": True},
            {"asset": "props/lanterns/1.png", "offset": (12, 9), "prop_type": "lantern"},
        ],
    },
    {
        "name": "shore_guard_post",
        "tags": {"coastal", "fort"},
        "weight": 5,
        "houses": [
            {"category": "tertiary", "prefer": "fort", "offset": (1, 1), "role": "guard_post"},
            {"category": "secondary", "prefer": "fishermanhut", "offset": (11, 4), "role": "lookout_home"},
            {"category": "primary", "prefer": "woodstall", "offset": (17, 5), "role": "supply_stall"},
        ],
        "props": [
            {"asset": "props/trainingyard/trainfigure4.png", "offset": (3, 9), "prop_type": "training_prop", "blocks": True},
            {"asset": "props/trainingyard/armsdisplay2.png", "offset": (5, 9), "prop_type": "training_prop", "blocks": True},
            {"asset": "props/crates/3.png", "offset": (8, 9), "prop_type": "crate", "blocks": True},
            {"asset": "props/general/barrel.png", "offset": (10, 9), "prop_type": "barrel", "blocks": True},
            {"asset": "props/lanterns/1.png", "offset": (14, 9), "prop_type": "lantern"},
        ],
    },
    {
        "name": "smuggler_warehouses",
        "tags": {"coastal", "warehouse"},
        "weight": 4,
        "houses": [
            {"category": "tertiary", "prefer": "warehouse2", "offset": (1, 1), "role": "hidden_warehouse"},
            {"category": "primary", "prefer": "abandoned", "offset": (10, 4), "role": "front_house"},
            {"category": "primary", "prefer": "beachcabin", "offset": (17, 5), "role": "lookout_cabin"},
        ],
        "props": [
            {"asset": "props/crates/10.png", "offset": (2, 9), "prop_type": "crate", "blocks": True},
            {"asset": "props/crates/7.png", "offset": (4, 9), "prop_type": "crate", "blocks": True},
            {"asset": "props/general/sackopen.png", "offset": (6, 9), "prop_type": "sack"},
            {"asset": "props/general/barrel.png", "offset": (8, 9), "prop_type": "barrel", "blocks": True},
            {"asset": "props/lanterns/1.png", "offset": (12, 9), "prop_type": "lantern"},
        ],
    },
    {
        "name": "dockside_fishery",
        "tags": {"coastal", "harbor"},
        "weight": 6,
        "houses": [
            {"category": "secondary", "prefer": "fishermanhut", "offset": (1, 2), "role": "fishery"},
            {"category": "tertiary", "prefer": "warehouse3", "offset": (8, 2), "role": "cold_storage"},
            {"category": "primary", "prefer": "beachcabin", "offset": (15, 5), "role": "dock_home"},
        ],
        "props": [
            {"asset": "props/buckets/buckets.png#0", "offset": (2, 9), "prop_type": "bucket"},
            {"asset": "props/crates/1.png", "offset": (4, 9), "prop_type": "crate", "blocks": True},
            {"asset": "props/crates/5.png", "offset": (6, 9), "prop_type": "crate", "blocks": True},
            {"asset": "props/general/barrel.png", "offset": (8, 9), "prop_type": "barrel", "blocks": True},
            {"asset": "props/lanterns/1.png", "offset": (11, 9), "prop_type": "lantern"},
        ],
    },
    {
        "name": "beach_trade_gate",
        "tags": {"coastal", "warehouse", "fort"},
        "weight": 3,
        "houses": [
            {"category": "tertiary", "prefer": "fort", "offset": (1, 1), "role": "trade_gate"},
            {"category": "tertiary", "prefer": "warehouse1", "offset": (10, 2), "role": "customs_storage"},
            {"category": "secondary", "prefer": "merchanthouse", "offset": (18, 4), "role": "coast_merchant"},
        ],
        "props": [
            {"asset": "props/general/signpost.png", "offset": (2, 9), "prop_type": "signpost", "blocks": True},
            {"asset": "props/trainingyard/armsdisplay3.png", "offset": (5, 9), "prop_type": "training_prop", "blocks": True},
            {"asset": "props/crates/6.png", "offset": (8, 9), "prop_type": "crate", "blocks": True},
            {"asset": "props/crates/9.png", "offset": (10, 9), "prop_type": "crate", "blocks": True},
            {"asset": "props/lanterns/1.png", "offset": (14, 9), "prop_type": "lantern"},
        ],
    },
    {
        "name": "stone_hut_circle",
        "weight": 4,
        "houses": [
            {"category": "primary", "prefer": "stonehut", "offset": (1, 1), "role": "home"},
            {"category": "primary", "prefer": "stonehut2", "offset": (8, 2), "role": "home"},
            {"category": "primary", "prefer": "simplehouse", "offset": (14, 3), "role": "home"},
        ],
        "props": [
            {"asset": "props/buckets/buckets.png#1", "offset": (2, 8), "prop_type": "bucket"},
            {"asset": "props/general/hay.png", "offset": (5, 8), "prop_type": "hay"},
            {"asset": "props/pots/potsthin.png#1", "offset": (8, 8), "prop_type": "pot", "blocks": True},
            {"asset": "props/flowers_pot_fenced/flowersmall.png#1", "offset": (11, 8), "prop_type": "flower"},
            {"asset": "props/lanterns/1.png", "offset": (14, 8), "prop_type": "lantern"},
        ],
    },
    {
        "name": "merchant_backlot",
        "weight": 3,
        "houses": [
            {"category": "secondary", "prefer": "merchanthouse2", "offset": (1, 1), "role": "merchant"},
            {"category": "primary", "prefer": "woodstall2", "offset": (10, 4), "role": "stall"},
            {"category": "primary", "prefer": "hut", "offset": (16, 4), "role": "worker_home"},
        ],
        "props": [
            {"asset": "props/crates/1.png", "offset": (2, 9), "prop_type": "crate", "blocks": True},
            {"asset": "props/crates/5.png", "offset": (4, 9), "prop_type": "crate", "blocks": True},
            {"asset": "props/general/sackopen.png", "offset": (6, 9), "prop_type": "sack"},
            {"asset": "props/general/barrel.png", "offset": (9, 9), "prop_type": "barrel", "blocks": True},
            {"asset": "props/pots/potsmeduim.png#2", "offset": (12, 9), "prop_type": "pot", "blocks": True},
            {"asset": "props/lanterns/1.png", "offset": (14, 9), "prop_type": "lantern"},
        ],
    },
    {
        "name": "training_camp",
        "weight": 3,
        "houses": [
            {"category": "primary", "prefer": "woodstall3", "offset": (1, 1), "role": "armory_stall"},
            {"category": "primary", "prefer": "thatchhut", "offset": (8, 3), "role": "trainer_home"},
            {"category": "primary", "prefer": "hut", "offset": (14, 4), "role": "recruit_home"},
        ],
        "props": [
            {"asset": "props/trainingyard/tent.png", "offset": (2, 8), "prop_type": "tent", "blocks": True},
            {"asset": "props/trainingyard/trainfigure1.png", "offset": (5, 8), "prop_type": "training_prop", "blocks": True},
            {"asset": "props/trainingyard/trainfigure4.png", "offset": (7, 8), "prop_type": "training_prop", "blocks": True},
            {"asset": "props/trainingyard/arrowtrain.png", "offset": (10, 8), "prop_type": "training_prop", "blocks": True},
            {"asset": "props/crates/8.png", "offset": (13, 8), "prop_type": "crate", "blocks": True},
        ],
    },
    {
        "name": "harbor_guard_warehouse",
        "tags": {"coastal", "warehouse", "fort", "harbor"},
        "weight": 4,
        "houses": [
            {"category": "tertiary", "prefer": "warehouse2", "offset": (1, 1), "role": "warehouse"},
            {"category": "tertiary", "prefer": "fort", "offset": (10, 1), "role": "guard_fort"},
            {"category": "primary", "prefer": "beachcabin", "offset": (18, 5), "role": "harbor_guard_home"},
        ],
        "props": [
            {"asset": "props/crates/1.png", "offset": (2, 9), "prop_type": "crate", "blocks": True},
            {"asset": "props/crates/10.png", "offset": (4, 9), "prop_type": "crate", "blocks": True},
            {"asset": "props/trainingyard/armsdisplay2.png", "offset": (7, 9), "prop_type": "training_prop", "blocks": True},
            {"asset": "props/general/barrel.png", "offset": (10, 9), "prop_type": "barrel", "blocks": True},
            {"asset": "props/lanterns/1.png", "offset": (14, 9), "prop_type": "lantern"},
        ],
    },
]

COASTAL_SCENE_TAGS = {"coastal", "warehouse", "fort", "harbor"}


def get_house_scene_footprint(category: str) -> tuple[int, int]:
    return HOUSE_CATEGORY_FOOTPRINTS.get(category, HOUSE_FOOTPRINT_TILES)


def _infer_scene_size(template: dict) -> tuple[int, int]:
    max_x = 0
    max_y = 0
    for house in template.get("houses", []):
        offset_x, offset_y = house["offset"]
        footprint_w, footprint_h = get_house_scene_footprint(house.get("category", "primary"))
        max_x = max(max_x, offset_x + footprint_w)
        max_y = max(max_y, offset_y + footprint_h)
    for prop in template.get("props", []):
        offset_x, offset_y = prop["offset"]
        max_x = max(max_x, offset_x + prop.get("width", 1))
        max_y = max(max_y, offset_y + prop.get("height", 1))
    for tree in template.get("trees", []):
        offset_x, offset_y = tree["offset"]
        max_x = max(max_x, offset_x + tree.get("width", 1))
        max_y = max(max_y, offset_y + tree.get("height", 1))
    for fence in template.get("fences", []):
        offset_x, offset_y, width, height = fence["rect"]
        max_x = max(max_x, offset_x + width)
        max_y = max(max_y, offset_y + height)
    for farm_plot in template.get("farm_plots", []):
        offset_x, offset_y, width, height = farm_plot["rect"]
        max_x = max(max_x, offset_x + width)
        max_y = max(max_y, offset_y + height)
    return max_x + 1, max_y + 1


def explicit_scene_fence_tiles(template: dict) -> tuple[tuple[int, int, bool], ...]:
    """Expand explicitly configured fence rectangles into perimeter records."""
    tiles = {}
    for fence in template.get("fences", []):
        offset_x, offset_y, width, height = fence["rect"]
        if width < 2 or height < 2:
            raise ValueError("Scene fence rectangles must be at least 2x2 tiles")

        perimeter = {
            *((x, offset_y) for x in range(offset_x, offset_x + width)),
            *((x, offset_y + height - 1) for x in range(offset_x, offset_x + width)),
            *((offset_x, y) for y in range(offset_y + 1, offset_y + height - 1)),
            *((offset_x + width - 1, y) for y in range(offset_y + 1, offset_y + height - 1)),
        }
        gates = {tuple(gate) for gate in fence.get("gates", ())}
        invalid_gates = gates - perimeter
        if invalid_gates:
            raise ValueError(f"Scene fence gates must lie on the perimeter: {sorted(invalid_gates)}")

        for tile in perimeter:
            tiles[tile] = tile in gates

    return tuple(
        (tile_x, tile_y, is_gate)
        for (tile_x, tile_y), is_gate in sorted(tiles.items(), key=lambda item: (item[0][1], item[0][0]))
    )


def _template_occupied_tiles(template: dict) -> set[tuple[int, int]]:
    occupied = set()
    for house in template.get("houses", []):
        offset_x, offset_y = house["offset"]
        width, height = get_house_scene_footprint(house.get("category", "primary"))
        occupied.update(
            (x, y)
            for y in range(offset_y, offset_y + height)
            for x in range(offset_x, offset_x + width)
        )
    for collection_name in ("props", "trees"):
        for record in template.get(collection_name, []):
            offset_x, offset_y = record["offset"]
            width = record.get("width", 1)
            height = record.get("height", 1)
            occupied.update(
                (x, y)
                for y in range(offset_y, offset_y + height)
                for x in range(offset_x, offset_x + width)
            )
    for farm_plot in template.get("farm_plots", []):
        offset_x, offset_y, width, height = farm_plot["rect"]
        occupied.update(
            (x, y)
            for y in range(offset_y, offset_y + height)
            for x in range(offset_x, offset_x + width)
        )
    return occupied


def _house_is_inside_explicit_fence(template: dict, house: dict) -> bool:
    house_x, house_y = house["offset"]
    house_w, house_h = get_house_scene_footprint(house.get("category", "primary"))
    for fence in template.get("fences", []):
        fence_x, fence_y, fence_w, fence_h = fence["rect"]
        if (
            house_x >= fence_x + 1
            and house_y >= fence_y + 1
            and house_x + house_w <= fence_x + fence_w - 1
            and house_y + house_h <= fence_y + fence_h - 1
        ):
            return True
    return False


def primary_house_fence_tiles(template: dict, house: dict) -> tuple[tuple[int, int, bool], ...]:
    """Return a broken front-yard fence for one primary-category house."""
    if house.get("category", "primary") != "primary":
        return ()
    if house.get("fence") != "frontage":
        return ()
    if _house_is_inside_explicit_fence(template, house):
        return ()

    house_x, house_y = house["offset"]
    house_w, house_h = get_house_scene_footprint("primary")
    front_y = house_y + house_h
    candidates = {
        (house_x - 1, front_y - 1),
        (house_x + house_w, front_y - 1),
        (house_x - 1, front_y),
        (house_x, front_y),
        (house_x + house_w - 1, front_y),
        (house_x + house_w, front_y),
    }

    occupied = _template_occupied_tiles(template)
    explicit_tiles = {
        (tile_x, tile_y)
        for tile_x, tile_y, _ in explicit_scene_fence_tiles(template)
    }
    available = candidates - occupied - explicit_tiles
    return tuple((tile_x, tile_y, False) for tile_x, tile_y in sorted(available, key=lambda tile: (tile[1], tile[0])))


def scene_fence_tiles(template: dict) -> tuple[tuple[int, int, bool], ...]:
    """Return explicit enclosures and partial primary-house frontage fences."""
    tiles = {
        (tile_x, tile_y): is_gate
        for tile_x, tile_y, is_gate in explicit_scene_fence_tiles(template)
    }
    for house in template.get("houses", []):
        for tile_x, tile_y, is_gate in primary_house_fence_tiles(template, house):
            tiles.setdefault((tile_x, tile_y), is_gate)

    return tuple(
        (tile_x, tile_y, is_gate)
        for (tile_x, tile_y), is_gate in sorted(tiles.items(), key=lambda item: (item[0][1], item[0][0]))
    )


def scene_fence_prop_pairs(template: dict) -> tuple[tuple[int, int, int, int], ...]:
    """Pair each solid generated fence tile with one consistent outside tile."""
    pairs = {}

    for fence in template.get("fences", []):
        left, top, width, height = fence["rect"]
        right = left + width - 1
        bottom = top + height - 1
        gates = {tuple(gate) for gate in fence.get("gates", ())}

        # Corners belong to the horizontal runs. This keeps every paired prop
        # tile unique while forming a clean one-tile-wide lane around the fence.
        for fence_x in range(left, right + 1):
            for fence_y, prop_y in ((top, top - 1), (bottom, bottom + 1)):
                if (fence_x, fence_y) not in gates:
                    pairs.setdefault((fence_x, fence_y), (fence_x, prop_y))
        for fence_y in range(top + 1, bottom):
            for fence_x, prop_x in ((left, left - 1), (right, right + 1)):
                if (fence_x, fence_y) not in gates:
                    pairs.setdefault((fence_x, fence_y), (prop_x, fence_y))

    for house in template.get("houses", []):
        house_x, house_y = house["offset"]
        house_w, _ = get_house_scene_footprint(house.get("category", "primary"))
        for fence_x, fence_y, is_gate in primary_house_fence_tiles(template, house):
            if is_gate or (fence_x, fence_y) in pairs:
                continue
            if fence_x < house_x:
                prop_tile = (fence_x - 1, fence_y)
            elif fence_x >= house_x + house_w:
                prop_tile = (fence_x + 1, fence_y)
            else:
                prop_tile = (fence_x, fence_y + 1)
            pairs[(fence_x, fence_y)] = prop_tile

    fence_tiles = {(x, y) for x, y, _ in scene_fence_tiles(template)}
    occupied = _template_occupied_tiles(template) | fence_tiles
    claimed = set()
    valid_pairs = []
    for fence_tile, prop_tile in sorted(pairs.items(), key=lambda item: (item[0][1], item[0][0])):
        fence_x, fence_y = fence_tile
        direction_x = prop_tile[0] - fence_x
        direction_y = prop_tile[1] - fence_y
        if direction_x:
            candidates = (
                prop_tile,
                (fence_x, fence_y - 1),
                (fence_x, fence_y + 1),
                (fence_x - direction_x, fence_y),
            )
        else:
            candidates = (
                prop_tile,
                (fence_x - 1, fence_y),
                (fence_x + 1, fence_y),
                (fence_x, fence_y - direction_y),
            )
        prop_tile = next(
            (candidate for candidate in candidates if candidate not in occupied and candidate not in claimed),
            None,
        )
        if prop_tile is None:
            continue
        claimed.add(prop_tile)
        valid_pairs.append((*fence_tile, *prop_tile))
    return tuple(valid_pairs)


def scene_fence_prop_tiles(template: dict) -> tuple[tuple[int, int], ...]:
    """Return the dedicated prop tile paired with each generated fence tile."""
    return tuple((prop_x, prop_y) for _, _, prop_x, prop_y in scene_fence_prop_pairs(template))


def scene_template_bounds(template: dict) -> tuple[int, int]:
    explicit_size = template.get("size")
    if explicit_size is not None:
        return tuple(explicit_size)
    return _infer_scene_size(template)


def scene_is_coastal(template: dict) -> bool:
    return bool(set(template.get("tags", set())) & COASTAL_SCENE_TAGS)


def weighted_scene_template(
    rng: random.Random,
    used_names: set[str] | None = None,
    *,
    prefer_coastal: bool = False,
) -> dict:
    used_names = used_names or set()
    templates = [template for template in HOUSE_SCENE_TEMPLATES if template["name"] not in used_names]
    if not templates:
        templates = HOUSE_SCENE_TEMPLATES

    weights = []
    for template in templates:
        weight = template.get("weight", 1)
        tags = set(template.get("tags", set()))
        if prefer_coastal and tags & COASTAL_SCENE_TAGS:
            weight *= 5
        elif prefer_coastal:
            weight = max(1, weight // 2)
        weights.append(weight)
    return rng.choices(templates, weights=weights, k=1)[0]


for scene_template in HOUSE_SCENE_TEMPLATES:
    for scene_house in scene_template.get("houses", []):
        if scene_house.get("category", "primary") == "primary":
            scene_house.setdefault("fence", "frontage")
    scene_template.setdefault("size", _infer_scene_size(scene_template))

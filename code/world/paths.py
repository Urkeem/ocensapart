"""Deterministic village roads connecting scene yard gates."""

from __future__ import annotations

import heapq
import random

from entities.environment_prop import list_environment_assets
from world.fence import FENCE_GATE


PATH_EMPTY = 0
PATH_TILE = 1
MAIN_STREET_WIDTH = 3
GATE_BRANCH_WIDTH = 2
CLIFF_BIOME_ID = 9


def _is_cliff(chunk, tile: tuple[int, int]) -> bool:
    x, y = tile
    return (
        chunk.in_bounds(x, y)
        and chunk.layers["biome"][chunk.get_index(x, y)] == CLIFF_BIOME_ID
    )


def _is_gate(chunk, tile: tuple[int, int]) -> bool:
    x, y = tile
    return chunk.in_bounds(x, y) and chunk.layers["fence"][chunk.get_index(x, y)] == FENCE_GATE


def _is_route_tile(chunk, tile: tuple[int, int], endpoints=()) -> bool:
    """Return whether a centerline may cross a tile.

    Route centerlines avoid authored objects. A gate is deliberately exempt so
    the path texture can begin beneath the transparent gate opening.
    """
    x, y = tile
    if not chunk.in_bounds(x, y):
        return False
    index = chunk.get_index(x, y)
    if chunk.layers["terrain"][index] < 0:
        return False
    if chunk.layers["dock"][index] is not None:
        return False
    if _is_cliff(chunk, tile):
        return False
    if tile in endpoints or _is_gate(chunk, tile):
        return True
    if chunk.layers["soil"][index] != 0:
        return False
    if chunk.layers["collision"][index] != 0:
        return False
    decoration = chunk.layers["decoration"][index]
    return decoration is None or (
        isinstance(decoration, dict) and decoration.get("type") == "path"
    )


def _nearest_open_tile(chunk, desired: tuple[int, int], endpoints=()) -> tuple[int, int] | None:
    x, y = desired
    candidates = []
    for radius in range(0, 7):
        for offset_y in range(-radius, radius + 1):
            for offset_x in range(-radius, radius + 1):
                if max(abs(offset_x), abs(offset_y)) != radius:
                    continue
                tile = (x + offset_x, y + offset_y)
                if _is_route_tile(chunk, tile, endpoints):
                    candidates.append((abs(offset_x) + abs(offset_y), tile[1], tile[0], tile))
        if candidates:
            return min(candidates)[-1]
    return None


def _a_star(chunk, start: tuple[int, int], goal: tuple[int, int]) -> list[tuple[int, int]]:
    if start == goal:
        return [start]
    endpoints = {start, goal}
    frontier = [(0, 0, start)]
    parents: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
    costs = {start: 0}
    serial = 0
    # The fixed order makes generation repeatable on every Python version.
    neighbors = ((1, 0), (0, 1), (-1, 0), (0, -1))

    while frontier:
        _, _, current = heapq.heappop(frontier)
        if current == goal:
            break
        for offset_x, offset_y in neighbors:
            neighbor = (current[0] + offset_x, current[1] + offset_y)
            if not _is_route_tile(chunk, neighbor, endpoints):
                continue
            index = chunk.get_index(*neighbor)
            # Reusing an established path is encouraged and naturally creates
            # clean junctions instead of several nearly parallel lanes.
            step_cost = 6 if chunk.layers["path"][index] == PATH_EMPTY else 2
            new_cost = costs[current] + step_cost
            if new_cost >= costs.get(neighbor, 1 << 30):
                continue
            costs[neighbor] = new_cost
            parents[neighbor] = current
            heuristic = abs(goal[0] - neighbor[0]) + abs(goal[1] - neighbor[1])
            serial += 1
            heapq.heappush(frontier, (new_cost + heuristic * 5, serial, neighbor))

    if goal not in parents:
        return []
    route = []
    current = goal
    while current is not None:
        route.append(current)
        current = parents[current]
    route.reverse()
    return route


def _winding_route(
    chunk,
    start: tuple[int, int],
    goal: tuple[int, int],
    rng: random.Random,
) -> list[tuple[int, int]]:
    """Route through a displaced midpoint so long roads never look ruler-straight."""
    distance = abs(goal[0] - start[0]) + abs(goal[1] - start[1])
    if distance < 5:
        return _a_star(chunk, start, goal)

    midpoint = ((start[0] + goal[0]) // 2, (start[1] + goal[1]) // 2)
    displacement = min(4, max(2, distance // 5))
    if abs(goal[0] - start[0]) >= abs(goal[1] - start[1]):
        direction = rng.choice((-1, 1))
        desired = (midpoint[0], midpoint[1] + direction * displacement)
    else:
        direction = rng.choice((-1, 1))
        desired = (midpoint[0] + direction * displacement, midpoint[1])
    waypoint = _nearest_open_tile(chunk, desired, {start, goal})
    if waypoint is None or waypoint in {start, goal}:
        return _a_star(chunk, start, goal)

    first = _a_star(chunk, start, waypoint)
    second = _a_star(chunk, waypoint, goal)
    if not first or not second:
        return _a_star(chunk, start, goal)
    return first + second[1:]


def _tile_can_receive_path(chunk, tile: tuple[int, int]) -> bool:
    x, y = tile
    if not chunk.in_bounds(x, y):
        return False
    index = chunk.get_index(x, y)
    if chunk.layers["terrain"][index] < 0 or chunk.layers["dock"][index] is not None:
        return False
    if _is_cliff(chunk, tile):
        return False
    if _is_gate(chunk, tile):
        return True
    if chunk.layers["collision"][index] != 0:
        return False
    if chunk.layers["soil"][index] != 0:
        return False
    decoration = chunk.layers["decoration"][index]
    return decoration is None or decoration.get("type") == "path"


def _paint_route(chunk, route: list[tuple[int, int]], width: int) -> set[tuple[int, int]]:
    painted = set()
    for route_index, (x, y) in enumerate(route):
        if width == MAIN_STREET_WIDTH:
            candidates = ((x + dx, y + dy) for dy in (-1, 0, 1) for dx in (-1, 0, 1))
        else:
            previous = route[max(0, route_index - 1)]
            following = route[min(len(route) - 1, route_index + 1)]
            horizontal = abs(following[0] - previous[0]) >= abs(following[1] - previous[1])
            candidates = ((x, y), (x, y + 1)) if horizontal else ((x, y), (x + 1, y))
        for tile in candidates:
            if not _tile_can_receive_path(chunk, tile):
                continue
            chunk.layers["path"][chunk.get_index(*tile)] = PATH_TILE
            painted.add(tile)
    return painted


def _gate_junction(chunk, house: dict) -> tuple[int, int]:
    gate_x, gate_y = map(int, house["yard_gate_tile"])
    # Generated yard gates face down. Prefer a three-tile approach beyond the
    # fence, then gracefully pull it inward for bottom-edge yards or coastline.
    desired = (gate_x, min(chunk.chunk_size[1] - 2, gate_y + 3))
    return _nearest_open_tile(chunk, desired, {(gate_x, gate_y)}) or (gate_x, gate_y)


def _street_loop_waypoints(
    chunk,
    junctions: list[tuple[int, int]],
) -> list[tuple[int, int]]:
    """Choose an open rectangular circuit around the village approaches."""
    width, height = chunk.chunk_size
    center_x = sum(tile[0] for tile in junctions) // len(junctions)
    center_y = sum(tile[1] for tile in junctions) // len(junctions)
    half_width = max(4, (max(tile[0] for tile in junctions) - min(tile[0] for tile in junctions)) // 2 + 3)
    half_height = max(4, (max(tile[1] for tile in junctions) - min(tile[1] for tile in junctions)) // 2 + 3)

    left = max(1, center_x - half_width)
    right = min(width - 2, center_x + half_width)
    top = max(1, center_y - half_height)
    bottom = min(height - 2, center_y + half_height)
    desired = ((left, top), (right, top), (right, bottom), (left, bottom))

    waypoints = []
    endpoints = set(junctions)
    for corner in desired:
        waypoint = _nearest_open_tile(chunk, corner, endpoints)
        if waypoint is not None and waypoint not in waypoints:
            waypoints.append(waypoint)
    return waypoints


def _closed_street_route(
    chunk,
    junctions: list[tuple[int, int]],
    rng: random.Random,
) -> list[tuple[int, int]]:
    """Build a continuous circuit, leaving no arbitrary main-road endpoints."""
    waypoints = _street_loop_waypoints(chunk, junctions)
    if len(waypoints) < 3:
        return []

    route = []
    for start, goal in zip(waypoints, waypoints[1:] + waypoints[:1]):
        segment = _winding_route(chunk, start, goal, rng)
        if not segment:
            return []
        route.extend(segment if not route else segment[1:])
    return route


def _edge_offset(length: int, seed: int) -> int:
    """Keep ports away from corners while supporting tiny test chunks."""
    margin = min(3, max(0, (length - 1) // 3))
    span = max(1, length - margin * 2)
    return margin + seed % span


def _edge_ports(chunk, world_seed: int) -> dict[str, tuple[int, int]]:
    """Return passable cross-chunk ports shared with all four neighbors.

    Each edge key describes the boundary rather than either chunk, so both
    chunks independently choose the same coordinate along their shared edge.
    """
    chunk_x, chunk_y = chunk.coord
    width, height = chunk.chunk_size
    definitions = (
        ("left", "vertical", chunk_x - 1, chunk_y, (0, None), height),
        ("right", "vertical", chunk_x, chunk_y, (width - 1, None), height),
        ("top", "horizontal", chunk_x, chunk_y - 1, (None, 0), width),
        ("bottom", "horizontal", chunk_x, chunk_y, (None, height - 1), width),
    )
    ports = {}
    for direction, orientation, edge_x, edge_y, template, length in definitions:
        seed = chunk._stable_seed(world_seed, "path-edge", orientation, edge_x, edge_y)
        offset = _edge_offset(length, seed)
        tile = (
            offset if template[0] is None else template[0],
            offset if template[1] is None else template[1],
        )
        if _is_route_tile(chunk, tile):
            ports[direction] = tile
    return ports


def _transit_routes(
    chunk,
    ports: list[tuple[int, int]],
    rng: random.Random,
) -> tuple[list[list[tuple[int, int]]], tuple[int, int] | None]:
    """Join a road-only chunk's boundary ports through one central junction."""
    if len(ports) < 2:
        return [], None
    width, height = chunk.chunk_size
    hub = _nearest_open_tile(chunk, (width // 2, height // 2), set(ports))
    if hub is None:
        return [], None

    routes = []
    for port in ports:
        route = _winding_route(chunk, port, hub, rng)
        if not route:
            route = _a_star(chunk, port, hub)
        if route:
            routes.append(route)
    return routes, hub


def _clear_generated_path_data(chunk) -> None:
    generated_ids = {
        prop.get("id")
        for prop in chunk.props
        if isinstance(prop, dict) and prop.get("pathside")
    }
    if generated_ids:
        for index, decoration in enumerate(chunk.layers["decoration"]):
            if isinstance(decoration, dict) and decoration.get("id") in generated_ids:
                chunk.layers["decoration"][index] = None
                chunk.layers["collision"][index] = 0
        chunk.props = [
            prop for prop in chunk.props
            if not (isinstance(prop, dict) and prop.get("pathside"))
        ]
    chunk.layers["path"] = [PATH_EMPTY] * (chunk.chunk_size[0] * chunk.chunk_size[1])


def _roadside_candidates(chunk, anchor: tuple[int, int], path_tiles: set[tuple[int, int]]):
    candidates = []
    for radius in (1, 2):
        for offset_y in range(-radius, radius + 1):
            for offset_x in range(-radius, radius + 1):
                if max(abs(offset_x), abs(offset_y)) != radius:
                    continue
                tile = (anchor[0] + offset_x, anchor[1] + offset_y)
                if tile in path_tiles or not chunk.in_bounds(*tile):
                    continue
                index = chunk.get_index(*tile)
                if (
                    chunk.layers["terrain"][index] > 0
                    and chunk.layers["collision"][index] == 0
                    and chunk.layers["decoration"][index] is None
                    and chunk.layers["fence"][index] == 0
                    and chunk.layers["dock"][index] is None
                    and chunk.layers["soil"][index] == 0
                ):
                    candidates.append(tile)
    return candidates


def _place_pathside_prop(
    chunk,
    tile: tuple[int, int],
    *,
    prop_type: str,
    asset: str,
    variant: str,
    index: int,
    blocks: bool = False,
    scale: float = 2,
) -> dict:
    local_x, local_y = tile
    world_tile = chunk.get_world_tile(local_x, local_y)
    prop_id = f"pathside:{chunk.coord}:{index}:{prop_type}"
    record = {
        "type": "environment",
        "id": prop_id,
        "prop_type": prop_type,
        "variant": variant,
        "asset": asset,
        "chunk": chunk.coord,
        "local_tile": tile,
        "world_tile": world_tile,
        "world_pos": (
            world_tile[0] * chunk.tile_size + chunk.tile_size // 2,
            (world_tile[1] + 1) * chunk.tile_size,
        ),
        "blocks_movement": blocks,
        "health": 2 if prop_type == "crate" else 0,
        "scale": scale,
        "pathside": True,
    }
    chunk.props.append(record)
    chunk.layers["decoration"][chunk.get_index(*tile)] = {
        "type": "environment",
        "id": prop_id,
        "prop_type": prop_type,
    }
    if blocks:
        chunk.layers["collision"][chunk.get_index(*tile)] = 1
    return record


def _dress_paths(
    chunk,
    main_route: list[tuple[int, int]],
    junctions: list[tuple[int, int]],
    path_tiles: set[tuple[int, int]],
    rng: random.Random,
) -> list[dict]:
    lanterns = list_environment_assets("props", "lanterns")
    flowers = list_environment_assets("flowers")
    weeds = list_environment_assets("thickets", "weeds")
    crates = list_environment_assets("props", "crates")
    placed = []

    # Junction lights are first and guaranteed whenever a free roadside tile
    # exists. Duplicate junctions collapse to a single lantern.
    for junction in dict.fromkeys(junctions):
        candidates = _roadside_candidates(chunk, junction, path_tiles)
        if not candidates or not lanterns:
            continue
        tile = rng.choice(candidates)
        placed.append(_place_pathside_prop(
            chunk,
            tile,
            prop_type="lantern",
            asset=rng.choice(lanterns),
            variant="path_junction",
            index=len(placed),
            scale=1,
        ))

    dressing = []
    if weeds:
        dressing.append(("weed", weeds, False, 2))
    if flowers:
        dressing.append(("flower", flowers, False, 2))
    if crates:
        dressing.append(("crate", crates, True, 1))
    dressing.append(("hay", ["props/general/hay.png"], False, 1))
    if not dressing or not main_route:
        return placed

    sample_step = max(4, len(main_route) // 6)
    anchors = main_route[2::sample_step]
    rng.shuffle(anchors)
    target_count = min(8, max(2, len(main_route) // 7))
    for anchor_index, anchor in enumerate(anchors):
        if len(placed) >= len(dict.fromkeys(junctions)) + target_count:
            break
        candidates = _roadside_candidates(chunk, anchor, path_tiles)
        if not candidates:
            continue
        prop_type, assets, blocks, scale = dressing[anchor_index % len(dressing)]
        tile = rng.choice(candidates)
        placed.append(_place_pathside_prop(
            chunk,
            tile,
            prop_type=prop_type,
            asset=rng.choice(assets),
            variant="pathside",
            index=len(placed),
            blocks=blocks,
            scale=scale,
        ))
    return placed


def generate_path_network(chunk, world_seed: int = 0, *, clear_existing: bool = True) -> set[tuple[int, int]]:
    """Build one island-wide road graph through deterministic chunk ports."""
    if clear_existing:
        _clear_generated_path_data(chunk)

    houses = [
        prop for prop in chunk.props
        if isinstance(prop, dict)
        and prop.get("type") == "house"
        and prop.get("yard_gate_tile") is not None
    ]
    rng = random.Random(chunk._stable_seed(world_seed, "paths", chunk.coord))
    gates = [tuple(map(int, house["yard_gate_tile"])) for house in houses]
    junctions = [_gate_junction(chunk, house) for house in houses]
    edge_ports = _edge_ports(chunk, world_seed)
    edge_routes = []
    edge_junctions = []

    if junctions:
        main_route = _closed_street_route(chunk, junctions, rng)
        if not main_route:
            # A solid cliff formation may prevent the local circuit. Preserve
            # the reachable side without ever carving through the cliff.
            main_route = [junctions[0]]
        path_tiles = _paint_route(chunk, main_route, MAIN_STREET_WIDTH)
    else:
        edge_routes, hub = _transit_routes(chunk, list(edge_ports.values()), rng)
        main_route = max(edge_routes, key=len, default=[])
        path_tiles = set()
        for route in edge_routes:
            path_tiles.update(_paint_route(chunk, route, MAIN_STREET_WIDTH))
        if hub is not None:
            edge_junctions.append(hub)

    actual_junctions = []
    for gate in gates:
        junction = min(
            main_route,
            key=lambda tile: abs(tile[0] - gate[0]) + abs(tile[1] - gate[1]),
        )
        branch = _winding_route(chunk, gate, junction, rng)
        if not branch:
            branch = _a_star(chunk, gate, junction)
        path_tiles.update(_paint_route(chunk, branch or [gate], GATE_BRANCH_WIDTH))
        actual_junctions.append(junction)

    if main_route and junctions:
        for port in edge_ports.values():
            junction = min(
                main_route,
                key=lambda tile: abs(tile[0] - port[0]) + abs(tile[1] - port[1]),
            )
            route = _winding_route(chunk, port, junction, rng)
            if not route:
                route = _a_star(chunk, port, junction)
            if not route:
                continue
            edge_routes.append(route)
            edge_junctions.append(junction)
            path_tiles.update(_paint_route(chunk, route, MAIN_STREET_WIDTH))

    props = _dress_paths(
        chunk,
        main_route,
        actual_junctions + edge_junctions,
        path_tiles,
        rng,
    )
    chunk.metadata["path_count"] = len(path_tiles)
    chunk.metadata["path_main_width"] = MAIN_STREET_WIDTH
    chunk.metadata["path_branch_width"] = GATE_BRANCH_WIDTH
    chunk.metadata["path_gates"] = tuple(gates)
    chunk.metadata["path_junctions"] = tuple(actual_junctions)
    chunk.metadata["path_main_route"] = tuple(main_route)
    chunk.metadata["path_main_closed"] = len(main_route) > 1 and main_route[0] == main_route[-1]
    chunk.metadata["path_edge_ports"] = tuple(sorted(edge_ports.items()))
    chunk.metadata["path_edge_routes"] = tuple(tuple(route) for route in edge_routes)
    chunk.metadata["path_transit"] = not bool(houses)
    chunk.metadata["path_prop_count"] = len(props)
    chunk._invalidate_layer_runtime("path")
    chunk.mark_dirty()
    return path_tiles

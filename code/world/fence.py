"""Cardinal fence autotiling and mutable fence-layer helpers."""

import pygame

from TileMapManager import CARDINAL_TILE_KEYS, TileMap


FENCE_EMPTY = 0
FENCE_SEGMENT = 1
FENCE_GATE = 2
FENCE_CONNECTION_VALUES = frozenset((FENCE_SEGMENT, FENCE_GATE))
FENCE_ART_SIZE = 32
# Match the shared base-aligned environment-prop collision profile.
FENCE_COLLISION_INFLATE = (-0.58, -0.76)

# fence.png is a 6x3 atlas of 32x32 cells.  The two cells at (5, 0)
# and (5, 2) are not part of the cardinal set and remain available for a
# future animated gate.  Until then FENCE_GATE deliberately renders nothing.
FENCE_TILE_COORDS = {
    "o": (0, 1),
    "b": (3, 0),
    "r": (0, 2),
    "br": (1, 0),
    "l": (2, 2),
    "bl": (2, 0),
    "lr": (1, 2),
    "lrb": (0, 0),
    "t": (4, 2),
    "tb": (3, 1),
    "tr": (4, 0),
    "tbr": (1, 1),
    "tl": (3, 2),
    "tbl": (4, 1),
    "lrt": (5, 1),
    "x": (2, 1),
}


def get_fence_tile_coords(*, top=False, right=False, bottom=False, left=False):
    """Return the atlas cell for one cardinal neighbor configuration."""
    cardinal_mask = 0
    if bottom:
        cardinal_mask |= 1
    if right:
        cardinal_mask |= 2
    if left:
        cardinal_mask |= 4
    if top:
        cardinal_mask |= 8
    return FENCE_TILE_COORDS[CARDINAL_TILE_KEYS[cardinal_mask]]


def get_fence_piece_layout(
    tile_size,
    *,
    top=False,
    right=False,
    bottom=False,
    left=False,
):
    """Return native-size fence pieces needed inside one world tile.

    The world currently uses 96px cells, so a straight fence is composed of
    three 32px sprites.  A 64px world configuration naturally produces two.
    Corners and junctions add arms around the shared center so the cardinal
    autotile remains continuous without scaling its pixel art.
    """
    tile_size = int(tile_size)
    pieces_per_axis = max(1, tile_size // FENCE_ART_SIZE)
    native_span = pieces_per_axis * FENCE_ART_SIZE
    origin = (tile_size - native_span) // 2
    anchor = (pieces_per_axis - 1) // 2

    occupied = {(anchor, anchor)}
    if top:
        occupied.update((anchor, y) for y in range(0, anchor + 1))
    if right:
        occupied.update((x, anchor) for x in range(anchor, pieces_per_axis))
    if bottom:
        occupied.update((anchor, y) for y in range(anchor, pieces_per_axis))
    if left:
        occupied.update((x, anchor) for x in range(0, anchor + 1))

    pieces = []
    for piece_x, piece_y in sorted(occupied, key=lambda point: (point[1], point[0])):
        piece_top = (piece_x, piece_y - 1) in occupied or (piece_y == 0 and top)
        piece_right = (
            (piece_x + 1, piece_y) in occupied
            or (piece_x == pieces_per_axis - 1 and right)
        )
        piece_bottom = (
            (piece_x, piece_y + 1) in occupied
            or (piece_y == pieces_per_axis - 1 and bottom)
        )
        piece_left = (piece_x - 1, piece_y) in occupied or (piece_x == 0 and left)
        pieces.append(
            (
                origin + piece_x * FENCE_ART_SIZE,
                origin + piece_y * FENCE_ART_SIZE,
                get_fence_tile_coords(
                    top=piece_top,
                    right=piece_right,
                    bottom=piece_bottom,
                    left=piece_left,
                ),
            )
        )
    return tuple(pieces)


def get_fence_connections(chunk, index, world=None):
    """Return cardinal fence/gate connections for a chunk-layer index."""
    width, height = chunk.chunk_size
    local_x = index % width
    local_y = index // width
    world_x, world_y = chunk.get_world_tile(local_x, local_y)

    def is_connected(dx, dy):
        neighbor_local_x = local_x + dx
        neighbor_local_y = local_y + dy
        if 0 <= neighbor_local_x < width and 0 <= neighbor_local_y < height:
            neighbor_index = neighbor_local_y * width + neighbor_local_x
            value = chunk.layers["fence"][neighbor_index]
            return value in FENCE_CONNECTION_VALUES

        if world is None:
            return False
        chunk_w, chunk_h = world.chunk_size
        neighbor_world_x = world_x + dx
        neighbor_world_y = world_y + dy
        chunk_coord = (neighbor_world_x // chunk_w, neighbor_world_y // chunk_h)
        neighbor_chunk = world.loaded_chunks.get(chunk_coord)
        if neighbor_chunk is None:
            return False
        neighbor_x = neighbor_world_x % chunk_w
        neighbor_y = neighbor_world_y % chunk_h
        neighbor_index = neighbor_y * chunk_w + neighbor_x
        return neighbor_chunk.layers["fence"][neighbor_index] in FENCE_CONNECTION_VALUES

    return {
        "top": is_connected(0, -1),
        "right": is_connected(1, 0),
        "bottom": is_connected(0, 1),
        "left": is_connected(-1, 0),
    }


class FenceTileMap(TileMap):
    """TileMap variant where invisible gates still bind adjacent fences."""

    def __init__(self, filename, world, chunk, source_tile_size=FENCE_ART_SIZE):
        super().__init__(
            filename=filename,
            world=world,
            chunk=chunk,
            layer_name="fence",
            oob=FENCE_EMPTY,
            source_tile_size=source_tile_size,
        )
        self._piece_sprites = {}

    def get_world_layer_tile(self, world_tile_x, world_tile_y):
        value = super().get_world_layer_tile(world_tile_x, world_tile_y)
        return FENCE_SEGMENT if value in FENCE_CONNECTION_VALUES else FENCE_EMPTY

    def get_tile_coords(self, index):
        local_layer = self.get_chunk_layer(self.chunk)
        if local_layer[index] != FENCE_SEGMENT:
            return None
        return FENCE_TILE_COORDS[self.get_cardinal_tile_key(index)]

    def get_connections(self, index):
        return get_fence_connections(self.chunk, index, self.world)

    def get_piece_sprite(self, coords):
        sprite = self._piece_sprites.get(coords)
        if sprite is None:
            sprite = self.tile_set.get_sprite(
                coords[0],
                coords[1],
                self.source_tile_size,
                self.source_tile_size,
            )
            self._piece_sprites[coords] = sprite
        return sprite


class FenceCollision:
    """Lightweight solid fence piece used by the player collision pass."""

    name = "fence"

    def __init__(self, world_tile, tile_size, piece_offset=None):
        self.world_tile = tuple(world_tile)
        cell_rect = pygame.Rect(
            self.world_tile[0] * tile_size,
            self.world_tile[1] * tile_size,
            tile_size,
            tile_size,
        )
        if piece_offset is None:
            piece_offset = (
                (tile_size - FENCE_ART_SIZE) // 2,
                (tile_size - FENCE_ART_SIZE) // 2,
            )
        self.sprite_rect = pygame.Rect(
            cell_rect.x + int(piece_offset[0]),
            cell_rect.y + int(piece_offset[1]),
            FENCE_ART_SIZE,
            FENCE_ART_SIZE,
        )
        inflate_x, inflate_y = FENCE_COLLISION_INFLATE
        self.collision_box = self.sprite_rect.inflate(
            self.sprite_rect.width * inflate_x,
            self.sprite_rect.height * inflate_y,
        )
        self.collision_box.midbottom = self.sprite_rect.midbottom
        self.rect = self.sprite_rect


def ensure_chunk_fence_collisions(chunk, world=None):
    """Return cached player-collision objects for solid fence segments."""
    cached = chunk.runtime.get("fence_collision_objects")
    if cached is not None:
        return cached

    width, _ = chunk.chunk_size
    collisions = []
    for index, value in enumerate(chunk.layers.get("fence", ())):
        if value != FENCE_SEGMENT:
            continue
        connections = get_fence_connections(chunk, index, world)
        world_tile = chunk.get_world_tile(index % width, index // width)
        for offset_x, offset_y, _ in get_fence_piece_layout(
            chunk.tile_size,
            **connections,
        ):
            collisions.append(
                FenceCollision(
                    world_tile,
                    chunk.tile_size,
                    piece_offset=(offset_x, offset_y),
                )
            )
    collisions = tuple(collisions)
    chunk.runtime["fence_collision_objects"] = collisions
    return collisions


def can_place_fence_at(world, world_tile):
    """Return whether a player-built fence can occupy this world tile."""
    chunk_w, chunk_h = world.chunk_size
    world_x, world_y = int(world_tile[0]), int(world_tile[1])
    chunk = world.loaded_chunks.get((world_x // chunk_w, world_y // chunk_h))
    if chunk is None:
        return False
    local_x, local_y = world_x % chunk_w, world_y % chunk_h
    index = chunk.get_index(local_x, local_y)
    return (
        chunk.layers["terrain"][index] >= 0
        and chunk.layers["collision"][index] == 0
        and chunk.layers["decoration"][index] is None
        and chunk.layers["path"][index] == 0
        and chunk.layers["fence"][index] == FENCE_EMPTY
        and chunk.layers["dock"][index] is None
        and chunk.layers["soil"][index] == 0
        and chunk.layers["plant"][index] is None
    )


def set_fence_at(world, world_tile, value=FENCE_SEGMENT):
    """Persist one fence-layer value and refresh affected chunk boundaries.

    Collision policy is intentionally left to the caller: a solid farm fence,
    an open gate, and a future closable gate need different collision states.
    """
    if value not in (FENCE_EMPTY, FENCE_SEGMENT, FENCE_GATE):
        raise ValueError(f"Unknown fence value: {value}")

    chunk_w, chunk_h = world.chunk_size
    world_x, world_y = int(world_tile[0]), int(world_tile[1])
    chunk_coord = (world_x // chunk_w, world_y // chunk_h)
    chunk = world.loaded_chunks.get(chunk_coord)
    if chunk is None:
        return False

    local_x = world_x % chunk_w
    local_y = world_y % chunk_h
    index = chunk.get_index(local_x, local_y)
    if chunk.layers["fence"][index] == value:
        return False

    chunk.set_saved_tile("fence", local_x, local_y, value)
    chunk.set_saved_tile(
        "collision",
        local_x,
        local_y,
        1 if value == FENCE_SEGMENT else 0,
    )
    decoration_layer = chunk.layers.get("decoration")
    decoration = decoration_layer[index] if decoration_layer is not None else None
    if decoration_layer is not None and value in FENCE_CONNECTION_VALUES and decoration is None:
        chunk.set_saved_tile(
            "decoration",
            local_x,
            local_y,
            {"type": "fence", "player_placed": True},
        )
    elif (
        decoration_layer is not None
        and
        value == FENCE_EMPTY
        and isinstance(decoration, dict)
        and decoration.get("type") == "fence"
        and decoration.get("player_placed")
    ):
        chunk.set_saved_tile("decoration", local_x, local_y, None)
    world.invalidate_fence_chunk_and_neighbors(chunk_coord)
    return True

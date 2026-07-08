"""Autotile helpers for rendering chunk layer masks from tileset atlases."""

from sprites import TileMapSpriteSheet

TILEBITMASK = {
    0: (3, 3), 1: (3, 3), 2: (3, 0), 3: (3, 0), 4: (3, 3), 5: (3, 3), 6: (3, 0), 7: (3, 0), 8: (0, 3), 9: (0, 3), 10: (4, 4), 11: (0, 0), 12: (0, 3), 13: (0, 3), 14: (4, 4),
    15: (0, 0), 16: (2, 3), 17: (2, 3), 18: (6, 4), 19: (6, 4), 20: (2, 3), 21: (2, 3), 22: (2, 0), 23: (2, 0), 24: (1, 3), 25: (1, 3), 26: (5, 4), 27: (3, 4), 28: (1, 3), 29: (1, 3),
    30: (2, 4), 31: (1, 0), 32: (3, 3), 33: (3, 3), 34: (3, 0), 35: (3, 0), 36: (3, 3), 37: (3, 3), 38: (3, 0), 39: (3, 0), 40: (0, 3), 41: (0, 3), 42: (4, 4), 43: (0, 0), 44: (0, 3), 45: (0, 3),
    46: (4, 4), 47: (0, 0), 48: (2, 3), 49: (2, 3), 50: (6, 4), 51: (6, 4), 52: (2, 3), 53: (2, 3), 54: (2, 0), 55: (2, 0), 56: (1, 3), 57: (1, 3), 58: (5, 4), 59: (3, 4), 60: (1, 3),
    61: (1, 3), 62: (2, 4), 63: (1, 0), 64: (3, 2), 65: (3, 2), 66: (3, 1), 67: (3, 1), 68: (3, 2), 69: (3, 2), 70: (3, 1), 71: (3, 1), 72: (4, 6), 73: (4, 6), 74: (4, 5), 75: (0, 5),
    76: (4, 6), 77: (4, 6), 78: (4, 5), 79: (0, 5), 80: (6, 6), 81: (6, 6), 82: (6, 5), 83: (6, 5), 84: (6, 6), 85: (6, 6), 86: (1, 5), 87: (1, 5), 88: (5, 6), 89: (5, 6), 90: (5, 5),
    91: (5, 3), 92: (5, 6), 93: (5, 6), 94: (4, 2), 95: (6, 1), 96: (3, 2), 97: (3, 2), 98: (3, 1), 99: (3, 1), 100: (3, 2), 101: (3, 2), 102: (3, 1), 103: (3, 1), 104: (0, 2), 105: (0, 2),
    106: (0, 4), 107: (0, 1), 108: (0, 2), 109: (0, 2), 110: (0, 4), 111: (0, 1), 112: (6, 6), 113: (6, 6), 114: (6, 5), 115: (6, 5), 116: (6, 6), 117: (6, 6), 118: (1, 5), 119: (1, 5), 120: (3, 5),
    121: (3, 5), 122: (5, 2), 123: (6, 0), 124: (3, 5), 125: (3, 5), 126: (3, 6), 127: (5, 1), 128: (3, 3), 129: (3, 3), 130: (3, 0), 131: (3, 0), 132: (3, 3), 133: (3, 3), 134: (3, 0), 135: (3, 0),
    136: (0, 3), 137: (0, 3), 138: (4, 4), 139: (0, 0), 140: (0, 3), 141: (0, 3), 142: (4, 4), 143: (0, 0), 144: (2, 3), 145: (2, 3), 146: (6, 4), 147: (6, 4), 148: (2, 3), 149: (2, 3), 150: (2, 0),
    151: (2, 0), 152: (1, 3), 153: (1, 3), 154: (5, 4), 155: (3, 4), 156: (1, 3), 157: (1, 3), 158: (2, 4), 159: (1, 0), 160: (3, 3), 161: (3, 3), 162: (3, 0), 163: (3, 0), 164: (3, 3), 165: (3, 3),
    166: (3, 0), 167: (3, 0), 168: (0, 3), 169: (0, 3), 170: (4, 4), 171: (0, 0), 172: (0, 3), 173: (0, 3), 174: (4, 4), 175: (0, 0), 176: (2, 3), 177: (2, 3), 178: (6, 4), 179: (6, 4), 180: (2, 3),
    181: (2, 3), 182: (2, 0), 183: (2, 0), 184: (1, 3), 185: (1, 3), 186: (5, 4), 187: (3, 4), 188: (1, 3), 189: (1, 3), 190: (2, 4), 191: (1, 0), 192: (3, 2), 193: (3, 2), 194: (3, 1), 195: (3, 1),
    196: (3, 2), 197: (3, 2), 198: (3, 1), 199: (3, 1), 200: (4, 6), 201: (4, 6), 202: (4, 5), 203: (0, 5), 204: (4, 6), 205: (4, 6), 206: (4, 5), 207: (0, 5), 208: (2, 2), 209: (2, 2), 210: (1, 4),
    211: (1, 4), 212: (2, 2), 213: (2, 2), 214: (2, 1), 215: (2, 1), 216: (2, 5), 217: (2, 5), 218: (4, 3), 219: (2, 6), 220: (2, 5), 221: (2, 5), 222: (6, 2), 223: (4, 1), 224: (3, 2), 225: (3, 2),
    226: (3, 1), 227: (3, 1), 228: (3, 2), 229: (3, 2), 230: (3, 1), 231: (3, 1), 232: (0, 2), 233: (0, 2), 234: (0, 4), 235: (0, 1), 236: (0, 2), 237: (0, 2), 238: (0, 4), 239: (0, 1), 240: (2, 2),
    241: (2, 2), 242: (1, 4), 243: (1, 4), 244: (2, 2), 245: (2, 2), 246: (2, 1), 247: (2, 1), 248: (1, 2), 249: (1, 2), 250: (6, 3), 251: (5, 0), 252: (1, 2), 253: (1, 2), 254: (4, 0), 255: (1, 1),
}

NEIGHBOR_OFFSETS = [
    (1, 1),
    (0, 1),
    (-1, 1),
    (1, 0),
    (-1, 0),
    (1, -1),
    (0, -1),
    (-1, -1),
]

CARDINAL_TILE_KEYS = {
    0: "o",
    1: "b",
    2: "r",
    3: "br",
    4: "l",
    5: "bl",
    6: "lr",
    7: "lrb",
    8: "t",
    9: "tb",
    10: "tr",
    11: "tbr",
    12: "tl",
    13: "tbl",
    14: "lrt",
    15: "x",
}


def get_cardinal_mask_from_bitmask(bitmask):
    mask = 0
    if bitmask & (1 << 6):
        mask |= 1
    if bitmask & (1 << 3):
        mask |= 2
    if bitmask & (1 << 1):
        mask |= 4
    if bitmask & (1 << 4):
        mask |= 8
    return mask


def get_cardinal_tile_key(bitmask):
    return CARDINAL_TILE_KEYS[get_cardinal_mask_from_bitmask(bitmask)]


class TileMap:
    def __init__(
        self,
        filename: str,
        world,
        chunk,
        layer_name="base",
        oob=1,
        layer_data=None,
        world_layer_resolver=None,
        source_tile_size=32,
    ):
        self.world = world
        self.chunk = chunk
        self.layer_name = layer_name
        self.oob = oob
        self.layer_data = layer_data
        self.world_layer_resolver = world_layer_resolver
        self.source_tile_size = int(source_tile_size)

        self.width, self.height = chunk.chunk_size
        self.tile_set = TileMapSpriteSheet(filename)
        self._bitmasks = None

    def invalidate_cache(self):
        self._bitmasks = None

    def get_chunk_layer(self, chunk):
        if chunk is self.chunk and self.layer_data is not None:
            return self.layer_data
        return chunk.layers[self.layer_name]

    def get_world_layer_tile(self, world_tile_x: int, world_tile_y: int) -> int:
        chunk_w, chunk_h = self.world.chunk_size

        chunk_x = world_tile_x // chunk_w
        chunk_y = world_tile_y // chunk_h

        local_x = world_tile_x % chunk_w
        local_y = world_tile_y % chunk_h

        neighbor_chunk = self.world.loaded_chunks.get((chunk_x, chunk_y))
        if neighbor_chunk is None:
            return self.oob

        if self.world_layer_resolver is not None:
            return self.world_layer_resolver(neighbor_chunk, local_x, local_y)

        layer = self.get_chunk_layer(neighbor_chunk)
        return layer[local_y * chunk_w + local_x]

    def create_tile_map_bitmasks(self):
        bitmasks = [0] * (self.width * self.height)
        for i in range(self.width * self.height):
            bitmasks[i] = self.get_bitmask(i)
        return bitmasks

    def get_bitmask(self, index):
        bitmask = 0
        local_y = index // self.width
        local_x = index % self.width

        world_x, world_y = self.chunk.get_world_tile(local_x, local_y)

        for i, (dx, dy) in enumerate(NEIGHBOR_OFFSETS):
            nx = world_x + dx
            ny = world_y + dy

            value = self.get_world_layer_tile(nx, ny)
            if value == 1:
                bitmask |= 1 << i

        return bitmask

    def get_cached_bitmask(self, index):
        if self._bitmasks is None:
            self._bitmasks = self.create_tile_map_bitmasks()
        return self._bitmasks[index]

    def get_tile_coords(self, index):
        local_layer = self.get_chunk_layer(self.chunk)
        if local_layer[index] != 1:
            return None

        bitmask = self.get_cached_bitmask(index)
        return TILEBITMASK[bitmask]

    def get_tile_sprite(self, index):
        coords = self.get_tile_coords(index)
        if coords is None:
            return None

        tx, ty = coords
        return self.tile_set.get_sprite(tx, ty, self.source_tile_size, self.source_tile_size)

    def get_cardinal_tile_key(self, index):
        local_layer = self.get_chunk_layer(self.chunk)
        if local_layer[index] != 1:
            return None
        return get_cardinal_tile_key(self.get_cached_bitmask(index))

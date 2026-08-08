# `code/world/water.py` Documentation

`water.py` contains water-specific runtime world objects that were previously defined in `main.py`.

## Imports and Dependencies

- `pygame`: Used to scale water animation frames to the active chunk tile size.
- `AnimatedWorldObject`: Base animated sprite class from `sprites`.

## Constants

- `DEFAULT_WATER_ANIMATION_SPEED`: Default animation speed for water tiles, currently `4.0`.

## Classes

### `WaterTile`

Animated shallow-water runtime sprite. It scales all supplied water frames to the chunk tile size, anchors them at the tile top-left, loops the animation, and marks itself as a `"ground"` render-layer object.

#### `WaterTile.__init__(self, world_pos, tile_size, frames, animation_speed=DEFAULT_WATER_ANIMATION_SPEED)`

Creates a shallow-water animated tile.

- `world_pos`: World pixel position for the tile top-left.
- `tile_size`: Runtime tile size used to scale each frame.
- `frames`: Source animation frame surfaces.
- `animation_speed`: Animation playback speed; defaults to `DEFAULT_WATER_ANIMATION_SPEED`.

Side effects:

- Creates scaled frame surfaces.
- Initializes `AnimatedWorldObject`.
- Sets `self.render_layer = "ground"` so water is not included in y-sorted actor rendering.

#### `WaterTile.sort_y`

Property returning `self.rect.bottom`. This gives water tiles a valid y-sort value even though they are normally skipped by y-sorted rendering.

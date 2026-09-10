# Gameplay Runtime Architecture

The original `code/main.py` grew to 1,452 lines because it owned startup UI,
asset caches, terrain composition, world-object synchronization, contextual
hints, rendering, and the active game loop. Those responsibilities now live in
the `code/gameplay/` package. `code/main.py` is a small application entry point.

## Entry Point: `code/main.py`

`main.py` now has three jobs:

1. Initialize Pygame and create the borderless display.
2. Run `StartupFlow` until its world and player are ready.
3. Pass the startup state to `run_game_loop` and quit Pygame when it returns.

Keeping this file small makes the application's control flow visible without
mixing it with rendering or world-generation details.

## Gameplay Package

### `gameplay/config.py`

Contains display-independent gameplay constants, UI colors, tile settings,
world defaults, and contextual-hint key mappings.

Chunk generation is intentionally limited to one queued chunk per frame. A
chunk includes procedural generation, runtime-object construction, and terrain
pre-rendering, so processing the old batch size of `9999` could freeze the
loading screen while the entire island was built.

### `gameplay/assets.py`

Owns the lazy shared `LoadAssets` instance and cached water animation frames.
This preserves the original behavior where large sprite sheets are loaded once
and reused by startup, terrain, and runtime-object systems.

### `gameplay/terrain.py`

Builds and caches the static visual layers for a chunk:

- Shallow-water base tiles
- Deep-ocean autotiling
- Base land autotiling
- Biome overlays
- Soil and farming overlays

Tile maps, scaled tile sprites, biome surfaces, deep-ocean surfaces, and final
chunk surfaces remain cached in `chunk.runtime`. A dirty chunk rebuilds its
surface; a clean chunk reuses it.

### `gameplay/world_objects.py`

Synchronizes persistent chunk records with live runtime objects. It owns trees,
houses, environmental props, animated water tiles, and plant collection. It
also provides:

- Visible-object updates
- Y-sort collection
- Nearby collision collection
- Loose-item pickup handling
- Rock-piece drop creation
- Chunk runtime prewarming

### `gameplay/hints.py`

Selects and draws contextual world hints for resource gathering, pickups, and
fishing. It also owns the fishing-line and bobber overlay. Hint fonts and the
bobber icon are loaded lazily and cached.

### `gameplay/rendering.py`

Draws visible terrain chunks, animated water, actors, world overlays, debug
information, and island-transition overlays.

The renderer now caches each chunk's camera-scaled surface by source surface and
zoom level. Previously every visible chunk surface was scaled again on every
frame, even when neither the terrain nor zoom had changed.

### `gameplay/startup.py`

Contains the `StartupFlow` state machine and its title, mode, seed,
customization, and loading screens. It creates the initial `WorldRun`, world,
soil layer, camera, player, HUD, chunks, and NPC manager.

Expected stages are `title`, `mode`, `seed`, `customize`, and `loading`.

### `gameplay/session.py`

Owns the active game loop and island transitions. It coordinates:

- Input and HUD events
- Player, camera, weather, soil, and NPC updates
- Active-chunk tracking and incremental chunk loading
- Pickups and hint acknowledgement
- Drawing and display presentation
- Rebinding the existing player when sailing to another island

## Runtime Flow

```text
main.py
  -> StartupFlow
       -> assets
       -> world generation
       -> incremental chunk prewarming
  -> run_game_loop
       -> input and simulation
       -> chunk/object updates
       -> world rendering
       -> HUD and weather
```

## Performance Notes

Modularizing code does not inherently increase frame rate. The measurable
performance-related changes in this refactor are:

- Zoomed static chunk surfaces are reused until the source surface or zoom
  changes.
- The debug font is reused rather than reconstructed every frame.
- Initial and in-session chunk queues process incrementally, preventing a large
  all-chunks-in-one-frame stall.

The existing terrain, sprite, asset, and runtime-object caches were preserved.
Further optimization should be driven by profiling, particularly around chunk
generation, biome surface construction, object collection, and zoomed actor
rendering.

### Per-frame allocation audit

The gameplay runtime now also avoids several repeated operations found during a
focused FPS audit:

- Chunk runtime objects are synchronized once and their immutable result tuples
  are reused until the owning runtime dictionary is replaced.
- A frame collects each visible chunk's objects once, then shares that collection
  between updates, ground rendering, and y-sorted rendering.
- Objects outside the camera viewport are neither animated nor submitted for
  drawing; a two-tile margin prevents visible pop-in.
- Water tiles share scaled animation frames and no longer copy a 96x96 surface or
  rebuild a pixel mask every animation update.
- Hint lookup runs at 10 Hz for drawing, while hint text and fishing-message
  surfaces are cached by message and color.
- Soil-water artwork is loaded and scaled once per tile size.
- Soil maintenance runs once per ten game minutes instead of scanning every tile
  in every loaded chunk every display frame. Harvest checks inspect only the
  world tiles overlapped by the player's collision rectangle.
- Soil changes invalidate soil and final-composite surfaces without discarding
  ocean, biome, water-object, house, tree, or environment caches.
- Biome surfaces are composed in one tile pass instead of one complete chunk pass
  per biome.
- The development overlay is disabled by default through
  `gameplay.config.SHOW_DEBUG_OVERLAY`.

In the headless one-chunk benchmark used during this audit, 200 object
collections fell from 273.68 ms to 23.44 ms, and 200 direct hint queries fell
from 197.79 ms to 64.47 ms. After viewport culling, 30 representative world
draws fell from 3649.97 ms to 532.72 ms. Headless timings are not equivalent to
on-screen FPS, but they demonstrate that the targeted repeated work was removed.

### Chunk-generation profile

Chunk generation and runtime prewarming were profiled separately with seed `0`,
24x24-tile chunks, and a 96-pixel runtime tile size.

| Profiled operation | Initial | Optimized |
| --- | ---: | ---: |
| Cold `World.load_chunk((0, 0))` | 8.13 s | 1.14 s |
| Subsequent `World.load_chunk((1, 0))` | 1.83 s | 0.79 s |
| Cold runtime prewarm after shared asset loading | 4.18 s | 1.1-1.6 s |

The profiler identified and guided these changes:

- House and environment asset catalogs are cached instead of scanning the same
  filesystem directories for every placed prop.
- Deterministic value-noise corner samples are cached per world. Adjacent tiles
  reuse 668 unique corner values rather than constructing and seeding roughly
  44,000 `random.Random` objects for the first chunk.
- Water distance uses a bounded multi-source breadth-first search instead of a
  complete 13x13 neighborhood scan for every tile.
- Coastal scene queries use a summed-area table, replacing hundreds of thousands
  of repeated terrain lookups with constant-time rectangle queries.
- All systems use one process-wide `LoadAssets` instance.
- Autotile bitmasks are calculated only for tiles present in a layer, and raw and
  scaled autotile sprites are shared by tiles with the same tileset coordinates.
- The shallow-water base for a chunk size is tiled once and reused.
- `active_radius=1` controls a 3x3 gameplay update and draw window. With
  `gameplay.config.PREWARM_FULL_ISLAND` enabled, startup nevertheless generates
  and pre-renders all 25 island chunks so crossing a chunk boundary does not
  schedule new terrain work during play.

The water-distance implementation was checked against the previous brute-force
algorithm, coastal prefix queries were checked against direct rectangle scans,
and startup streaming, shared assets, chunk prewarming, and world drawing passed
headless smoke tests.

### Phased prewarming and runtime profiles

Chunk prewarming is now resumable. Each queued call performs one of eight
phases: trees, houses, environment props, animated water, ocean autotiles,
biome autotiles, soil, or the final terrain composite. Generated chunks remain
available while these phases run, and startup and in-game streaming both wait
for the generation and prewarm queues before treating the area as ready.

In a seed-0, nine-chunk startup smoke test, all chunks completed and retained a
final surface. With assets already initialized, the slowest generation unit was
348.84 ms. The final terrain composite is additionally divided into four-row
batches: its average step fell from 189.29 ms to 29.39 ms, with a 130.34 ms
worst step in the headless verification run. The largest measured step across
all prewarm phases was 136.78 ms.

NPC profiling showed that A* route searches were not the update bottleneck. A
100-route loaded-world run completed in 62.46 ms, while the old 15-NPC animation
path spent most of its time copying surfaces and rebuilding pixel masks. NPC
animation frames are now scaled once, shared, and swapped only when the visible
frame changes. The same 600 manager updates fell from 3.232 s to 63.77 ms.

Weather profiling found that the full-screen color multiply dominates particle
cost. Wind and cloud images are now prepared once, rain is submitted with one
batched blit call, the status panel is reused, and weather text and tint colors
are refreshed only when their displayed values change. A 300-frame rainy test
fell from 0.988 s to 0.760 s. The remaining 0.510 s is the required full-screen
tint blit, so a renderer/shader change would be needed for a much larger gain.

### Cross-chunk autotile continuity

Loading a new chunk now invalidates the terrain-dependent autotile caches in
that chunk and its eight neighbors. This matters because the first chunk at a
boundary may have been autotiled while its neighbor was still absent. The last
complete surface stays visible while the affected ocean and biome phases are
rebuilt, then the final phase swaps in the corrected composite. Soil-only edits
use a separate invalidation path so tilling does not trigger this broader work.

A synthetic adjacent-chunk regression check confirmed that a same-biome border
mask changed from `214` (no east neighbor) to `255` (fully connected) after the
neighbor loaded, and that the cached tile map was replaced while the old final
surface remained available during rebuilding.

### Full-island startup prewarm

Startup and later island transitions now request the complete island for
generation and prewarming while leaving only the nearby 3x3 window active for
updates and drawing. This shifts the cost into the loading screen instead of
briefly freezing gameplay as the player approaches an unprepared chunk.

The seed-0 headless verification generated and fully prewarmed all 25 chunks in
34.74 seconds after asset initialization. Moving the test position into the
next chunk changed the active window but left both work queues empty. Set
`gameplay.config.PREWARM_FULL_ISLAND` to `False` to restore incremental
streaming on lower-memory systems.

### Procedural beach docks

Coastal chunks can now generate one deterministic dock from a coast or beach
tile. A short two-to-four-tile access pier opens into an eight-row wooden
platform that tapers between five and nine tiles wide. Multiple asymmetric
profiles give the deck a narrow neck, uneven shoulders, and a tapered far end
instead of a rectangular footprint. The 64x64 cells from
`graphics/tilesets/dock.png` are used as a proper tileset: the row and column
strips form the directional access pier, while the upper-left 3x3 cells provide
platform corners, edges, entrance, and interior fill. Edge sprites are selected
from each deck tile's actual neighbors, so the outline works in all four dock
directions. Every piece is scaled to the current world tile size and composed
into the chunk's cached static terrain surface. This keeps docks out of the
per-frame rendering path and includes them in full-island startup prewarming.

Dock tiles reserve their locations before houses, trees, and environment props
are generated. Over-water sections have walkable collision, are treated as dry
ground by the player's swimming-depth resolver, and are valid NPC pathfinding
tiles. Other water remains blocked to NPCs. Animated shallow-water objects are
not created under dock pieces, preventing the water animation from covering the
planks. Each platform reserves a centered fisherman hut or beach cabin during
generation and leaves a walkable perimeter around its building footprint.

### Fence cardinal autotiling

`graphics/sprites/environment/fence/fence.png` is registered as a 6x3 atlas of
32x32 cells. `world/fence.py` maps all sixteen top/right/bottom/left
neighbor combinations to their atlas coordinates, including isolated posts,
end caps, corners, straight runs, T-junctions, and four-way crossings. Fence
lookups use world tile coordinates, so connections remain continuous across
chunk boundaries.

Chunks store fence state in a dedicated `fence` layer. Value `1` is a rendered
fence segment, while value `2` is a reserved gate: it renders as an empty cell
for now but still counts as connected when adjacent fence sprites are chosen.
`world.fence.set_fence_at` persists either value and invalidates the affected
chunk and neighboring fence caches. Collision remains a caller decision so a
future gate can switch cleanly between open and closed states.

The `farmstead` scene template now uses this layer for a 13x9 enclosure. Its
perimeter contains thirty-nine solid segments and one empty, walkable gate at
the bottom-center approach. Fence cells reserve their scene locations before
props and trees are placed, block both player and NPC movement, and are rebuilt
through the same cached cardinal autotiling path as manually placed fences.

Every primary-category house in the scene catalog also receives a partial
frontage fence. The standard layout uses two short side returns and a broken
front rail with a centered walking gap. Pieces that would overlap existing
scene props, trees, neighboring buildings, or explicit enclosures are omitted,
giving the yards varied, incomplete silhouettes while preserving their authored
dressing. Primary houses already inside the farmstead enclosure do not receive
a redundant inner frontage.

Fence art uses 32x32 source cells scaled to the active world tile size so rails
meet cleanly across neighboring cells. NPC pathfinding treats each solid fence
segment as a blocked logical tile. Player movement instead uses a small 14x8
bottom-aligned collision box derived from the same proportional profile used by
blocking environment props; gate cells have neither collision.

### NPC sprite and behavior system

`assets.LoadAssets` catalogs the folders under `graphics/sprites/npcs` and
loads an individual sheet only when its variant is selected for spawning. Cats
and dogs are deliberately excluded. The current import provides 145 human NPC
profiles across 18 roles.

Every NPC sheet uses 32x32 cells. The first 128x128 region supplies four-frame
walk animations in down, right, up, and left row order. The first frame of each
row is also the directional fallback idle. Role-specific states are registered
as follows:

| Role | Animation | Start | Frames |
| --- | --- | ---: | ---: |
| Bard | idle / singing | `(0,160)` / `(0,192)` | 1 / 4 |
| Dancer | idle / dancing | `(0,160)` / `(0,224)` | 1 / 3 |
| Merchant | sitting | `(0,160)` | 2 |
| King | finger-tapping idle | `(0,224)` | 2 |
| Queen | eyes-closed idle | `(0,224)` | 2 |
| Chef | drinking right / left | `(0,160)` / `(0,192)` | 4 / 4 |
| Nun | praying down / kneeling up | `(0,160)` / `(0,192)` | 2 / 2 |

The NPC manager selects 35 deterministic variants for an island and guarantees
that these featured roles are considered before filling the population with
other roles. NPCs wander within an 18-tile Manhattan radius, retain their last
walking direction for normal idles, and sometimes enter an appropriate special
state while resting. NPCs use the same 2x visual-scale multiplier as the player;
scaled frames and pixel masks remain shared across NPCs. Navigation accepts
non-water terrain and generated dock tiles with an empty collision tile, so
routes detour around coastlines instead of entering open ocean.

The automated headless check validated every walk row and supplied special
coordinate, confirmed all extracted frames contain pixels, and completed 9,000
NPC updates in 139.03 ms. A separate two-minute, 35-NPC route simulation found
no immobile NPCs, no walking state without a target, and no route that stopped
making progress. NPC foot positions now round-trip to their correct pathfinding
tile at tile boundaries, and a two-second route watchdog safely resets any
future path that genuinely stops progressing.

### Player collision and interaction boxes

The player now has two strictly separate collision responsibilities. The body
box is the only rectangle used for movement resolution against trees, rocks,
houses, and other blocking props. The smaller feet box never repositions the
player; it supplies the origin for tools, pickups, contextual prompts, crop
harvesting, planting, watering, tilling, fishing depth, and fruit collection.
This removes the former rock-only movement branch that could resolve upward
movement using the wrong player anchor.

Tree collision is anchored to the trunk base instead of the center of the full
canopy sprite. Environment collision profiles also use smaller base-aligned
rectangles for rocks, crates, barrels, and general blocking props. Set
`gameplay.config.SHOW_PLAYER_FEET_COLLISION` to `True` only when temporarily
debugging the interaction origin; it is disabled during normal play.

### PlayStation controller input

`gameplay/controls.py` uses Pygame's SDL game-controller mapping so DualShock
and DualSense controllers use standardized button positions and can be
connected or disconnected while the game is running. The keyboard remains
available at the same time. The left stick has a radial deadzone, and both the
left stick and D-pad work for movement and menu navigation.

| PlayStation control | Action |
| --- | --- |
| Left stick / D-pad | Move and navigate menus |
| Cross | Confirm, collect pickups, activate inventory choices |
| Circle | Cancel, close inventory, plant/use the selected seed |
| Square | Use the selected tool, cast, or reel in |
| Triangle | Open or close inventory |
| L1 | Cycle tools |
| R1 | Cycle seeds |

The inventory exposes a controller focus outline and spatial D-pad/stick
navigation across inventory slots, recipes, resources, crafting, paging, and
categories. Contextual world hints automatically switch from keyboard labels
to PlayStation labels while a controller is attached.

### Lantern lighting

Environment props with `prop_type="lantern"` automatically expose a warm light
source centered on the hanging lamp. `world/lighting.py` caches a radial
additive glow by radius, color, intensity, and camera zoom, so multiple lanterns
do not rebuild gradient surfaces every frame.

The gameplay render order is world objects, weather particles and night tint,
lantern light, then weather and HUD interface elements. This allows lanterns to
brighten the tinted world without washing out UI. Lanterns switch on at 18:00,
remain active overnight, and switch off at 07:00. Removed lantern props are
ignored automatically, and off-screen lights are culled before drawing.

The headless lighting check confirmed the day/evening/morning boundaries,
automatic lantern registration, visible additive illumination, and reuse of
the cached glow surface.

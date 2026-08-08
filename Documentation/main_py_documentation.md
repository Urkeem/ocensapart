# `code/main.py` Documentation

`main.py` is the current game entry point and runtime glue layer. It initializes Pygame, defines global rendering and world defaults, lazily loads shared assets, builds cached chunk surfaces, manages visible chunk objects, renders world/UI overlays, runs startup screens, and owns the active game loop.

The file currently contains several responsibilities that could later be split into rendering, world-object runtime caching, interaction hints, startup/menu flow, and game-session orchestration.

## Module-Level Imports and Dependencies

- `math`: Used for sine-based bobbing animation in world hints.
- `random`: Used to deterministicly scatter rock-piece drops.
- `pygame`: Core display, surfaces, input, fonts, rects, and transforms.
- `WorldRun`, `BIOME_TABLE`: World-run progression and biome metadata from `world.worldmanager`.
- `Player`: Player entity class.
- `TileMap`: Autotile/sprite lookup helper.
- `Camera`: Camera positioning and zoom.
- `LoadAssets`: Shared sprite and metadata loader.
- `Tree`: Tree entity factory and runtime object.
- `House`: House entity/runtime object.
- `EnvironmentProp`, `list_environment_assets`: Environment prop runtime object and asset lookup helper.
- `SoilLayer`, `get_soil_surface`, `ensure_chunk_plant_objects`: Farming/soil layer systems.
- `GameplayHUD`: Gameplay HUD rendering and input handling.
- `WeatherSystem`: Weather simulation and rendering.
- `NPCManager`: NPC spawning, visibility, and updates.
- `WaterTile`: Animated shallow-water tile runtime object from `world.water`.
- `rp`: Resource-path helper.

The module calls `pygame.init()` at import time.

## Constants and Global Variables

### Display and Timing

- `SCREEN_WIDTH`: Current display width from `pygame.display.Info().current_w`.
- `SCREEN_HEIGHT`: Current display height from `pygame.display.Info().current_h`.
- `FPS`: Target frame rate, currently `60`.

### Tilesets and World Rendering

- `BASE_LAND_TILESET_FILE`: Land tileset path, currently `"Tilesets/land.png"`.
- `DEEP_OCEAN_TILESET_FILE`: Deep-ocean tileset path, currently `"Tilesets/ocean.png"`.
- `AUTOTILED_BIOMES`: Set of biome IDs rendered with biome autotiling, currently `{1, 2, 3, 4, 5, 6, 7, 8, 9, 10}`.
- `DEEP_OCEAN_THRESHOLD`: Elevation cutoff for deep-ocean tiles, currently `0.30`.
- `TILESET_SOURCE_TILE_SIZE`: Source tileset cell size in pixels, currently `32`.
- `WORLD_SCALE`: Player visual scale passed during player creation, currently `2`.

### Colors

- `BACKGROUND_COLOR`: World clear color, `(20, 20, 30)`.
- `PLAYER_COLOR`: Fallback rectangle color for renderables without images, `(230, 70, 70)`.
- `TEXT_COLOR`: Debug overlay text color, `(255, 255, 255)`.
- `UI_BG`: Startup/menu background color, `(11, 16, 26)`.
- `UI_PANEL`: Startup/menu panel fill, `(22, 30, 45)`.
- `UI_PANEL_ALT`: Startup/menu panel border and secondary fills, `(30, 40, 60)`.
- `UI_ACCENT`: Primary UI accent, `(76, 145, 201)`.
- `UI_ACCENT_2`: Secondary UI accent, `(209, 177, 87)`.
- `UI_TEXT`: Primary UI text, `(236, 240, 245)`.
- `UI_MUTED`: Muted UI text, `(170, 180, 190)`.
- `UI_WARN`: Warning/disabled UI text, `(135, 135, 145)`.

### World Defaults

- `DEFAULT_CHUNK_SIZE`: Default chunk dimensions in tiles, `(24, 24)`.
- `DEFAULT_ACTIVE_RADIUS`: Active chunk radius around the player, currently `1`.
- `DEFAULT_TILE_SIZE`: Runtime tile size in pixels, `TILESET_SOURCE_TILE_SIZE * 3`, currently `96`.
- `INITIAL_LOAD_BATCH`: Number of chunks to process per loading frame, currently `9999`.

### Interaction Hint Constants

- `WORLD_HINT_KEYS`: Keyboard keys that can acknowledge contextual hints. Includes Space, left/right Ctrl, Q, E, and P.
- `WORLD_HINT_ACK_KEYS`: Maps hint IDs to the exact key set that marks that hint as seen:
  - `select_axe`: Q.
  - `break_resource`: Space.
  - `collect_loose_item`: E or P.
  - `select_fishing_rod`: Q.
  - `cast_fishing_line`: Space.
  - `reel_fishing_line`: Space.

### Lazy Global Caches

- `_WATER_FRAME_CACHE`: Starts as `None`; becomes the ordered list of water animation frame surfaces.
- `_SHARED_ASSETS`: Starts as `None`; becomes the shared `LoadAssets` instance.
- `_WORLD_HINT_FONT`: Starts as `None`; becomes the cached hint `pygame.font.Font`.
- `_BOBBER_ICON`: Starts as `None`; becomes the cached scaled fishing bobber icon.

## Classes

### `StartupFlow`

State machine for the pre-game startup UI. It owns title, mode selection, seed input, character customization, loading progress, initial world creation, and handoff data for the game loop.

Important instance fields created in `__init__`:

- `screen`: Main Pygame display surface.
- `stage`: Startup stage, initially `"title"`. Expected stages are `"title"`, `"mode"`, `"seed"`, `"customize"`, and `"loading"`.
- `mode_index`: Selected mode index.
- `modes`: Available mode labels: `"Island Voyage"` and `"Story Mode"`.
- `seed_text`: User-entered seed text.
- `world_run`: Current `WorldRun`, initialized during loading.
- `customization_categories`: Character customization categories: skin, clothes, hair, weapon.
- `customization_category_index`: Selected customization row.
- `customization`: Current customization option dictionary.
- `assets`: Shared `LoadAssets` instance, loaded lazily.
- `world`: Generated world for the first island.
- `soil_layer`: `SoilLayer` bound to the generated world.
- `hud`: `GameplayHUD` for the player.
- `npc_manager`: `NPCManager`, created after chunks load.
- `player`: Player instance created during loading.
- `camera`: Camera instance created during loading.
- `last_player_chunk`: Player chunk at startup completion.
- `loading_progress`: Float progress value between `0.0` and `1.0`.
- `loading_label`: Primary loading text.
- `loading_note`: Secondary loading/status text.
- `target_chunk_count`: Expected initial chunk count for progress reporting.
- `done`: Becomes `True` when startup is ready to enter gameplay.
- `big_font`, `title_font`, `body_font`, `small_font`: Cached Pygame fonts loaded from `font/LycheeSoda.ttf`.

#### `StartupFlow.__init__(self, screen)`

Initializes startup state, stores the screen, sets menu defaults, clears runtime object references, and creates the fonts used by startup screens.

#### `StartupFlow.handle_event(self, event)`

Handles keyboard input for the current startup stage.

- Title: Enter or Space moves to mode selection.
- Mode: Up/W and Down/S change selected mode; Enter selects a mode. Island Voyage advances to seed entry, while Story Mode shows a coming-soon note.
- Seed: Enter advances to customization; Backspace edits seed text; Escape returns to mode selection; digits and a leading minus sign are accepted.
- Customize: Left/A and Right/D cycle options; Up/W and Down/S change category; Enter starts loading; Escape returns to seed entry.

Non-keydown events are ignored.

#### `StartupFlow.get_selected_seed(self)`

Returns the selected seed as an integer. Empty seed text and a lone minus sign both resolve to `0`.

#### `StartupFlow.begin_loading(self)`

Switches to the `"loading"` stage and resets all loading/session fields so a fresh world can be initialized.

#### `StartupFlow.begin_customization(self)`

Switches to the `"customize"` stage, ensures shared assets are loaded, and normalizes the current customization dictionary through `LoadAssets`.

#### `StartupFlow.get_customization_options(self, category)`

Returns available customization options for a category. For `weapon`, `None` is prepended so the player can choose no weapon.

#### `StartupFlow.change_customization_option(self, direction)`

Moves the selected customization category forward or backward through its option list. If the current value is invalid, the first option is used as the starting point.

#### `StartupFlow.update(self)`

Advances loading work one step per call while `stage == "loading"` and `done == False`.

Loading sequence:

1. Load shared assets.
2. Create `WorldRun`, world, soil layer, camera, player, HUD, and initial active chunks.
3. Process the initial chunk load queue and prewarm chunk runtime data.
4. Create the initial `NPCManager`, set final progress, record the player's chunk, and mark startup as done.

#### `StartupFlow.draw(self)`

Clears the screen, draws the animated background swells, and delegates to the draw method for the current stage.

#### `StartupFlow.draw_background_swells(self)`

Draws translucent circular swell shapes behind the startup panel.

#### `StartupFlow.draw_center_panel(self, title, subtitle=None, footer=None, center_text=False, title_font=None, subtitle_font=None, size=None)`

Draws a centered startup panel with title, optional subtitle, optional footer, optional centered text layout, optional font overrides, and optional panel size. Returns the panel `pygame.Rect`.

#### `StartupFlow.draw_title_screen(self)`

Draws the title screen for `"Oceans Apart"` with a short subtitle and start prompt.

#### `StartupFlow.draw_mode_screen(self)`

Draws mode selection, highlights the selected mode, displays the Story Mode coming-soon badge, and shows `loading_note` if Story Mode was selected.

#### `StartupFlow.draw_seed_screen(self)`

Draws seed-entry UI with the current seed value and example seed text.

#### `StartupFlow.draw_customize_screen(self)`

Draws character customization UI, including an animated preview and rows for skin, clothes, hair, and weapon selection.

#### `StartupFlow.draw_loading_screen(self)`

Draws loading label, loading note, progress bar, and percentage.

## Functions

### `get_shared_assets()`

Returns the shared `LoadAssets` instance. The first call creates it and stores it in `_SHARED_ASSETS`; later calls reuse the same object to avoid repeated asset loading.

### `get_water_frames()`

Returns ordered shallow-water animation frames. It loads frames from `get_shared_assets().water_frames` and `water_sprites`, sorts frame metadata numerically by key, converts each frame with alpha, and caches the resulting surfaces in `_WATER_FRAME_CACHE`.

### `get_scaled_shallow_water_sprite(chunk)`

Returns a shallow-water still sprite scaled to `chunk.tile_size`. The result is cached on `chunk.runtime["water_sprite"]`.

### `get_chunk_tilemap(world, chunk)`

Returns the cached base land `TileMap` for a chunk, creating it from `BASE_LAND_TILESET_FILE` if needed. The tilemap is cached on `chunk.runtime["tilemap"]`.

### `is_deep_water_tile(chunk, local_x, local_y)`

Returns `1` when a local tile is deep ocean, otherwise `0`.

A tile counts as deep ocean when:

- Its terrain layer value is `-1`.
- Its elevation is less than or equal to `DEEP_OCEAN_THRESHOLD`.
- None of its in-bounds neighboring tiles contain land terrain.

### `build_deep_water_mask(chunk)`

Builds a flat list mask for the whole chunk where each entry is `1` for deep ocean and `0` otherwise.

### `get_neighbor_deep_water_mask_value(neighbor_chunk, local_x, local_y)`

Adapter used by `TileMap` neighbor resolution. It returns `is_deep_water_tile` for a neighboring chunk tile.

### `get_deep_ocean_tilemap(world, chunk)`

Returns the cached deep-ocean `TileMap` for a chunk, creating it from `DEEP_OCEAN_TILESET_FILE` and a deep-water mask if needed. The tilemap is cached on `chunk.runtime["deep_ocean_tilemap"]`.

### `get_scaled_deep_ocean_sprite(world, chunk, idx)`

Returns a scaled deep-ocean sprite for a chunk tile index. Uses `get_deep_ocean_tilemap`, scales the raw sprite to `chunk.tile_size`, and caches by tile index in `chunk.runtime["deep_ocean_sprite_cache"]`. Returns `None` when the tilemap has no sprite for the index.

### `get_deep_ocean_surface(world, chunk)`

Builds and returns the composited deep-ocean surface for a chunk. It reuses `chunk.runtime["deep_ocean_surface"]` while the chunk is not dirty, otherwise it redraws all deep-ocean sprites onto a transparent surface.

### `get_scaled_land_sprite(chunk, tilemap, idx)`

Returns a scaled base-land sprite for a chunk tile index. Scales raw tilemap sprites to `chunk.tile_size` and caches by index in `chunk.runtime["scaled_land_sprites"]`. Returns `None` if the tilemap has no sprite for the index.

### `build_biome_mask(chunk, biome_id)`

Builds a flat list mask where entries are `1` for tiles matching `biome_id` and `0` for all other biome values.

### `get_neighbor_biome_mask_value(neighbor_chunk, local_x, local_y, biome_id)`

Adapter used by biome `TileMap` neighbor resolution. It returns `1` if a neighboring chunk tile has the requested biome ID, otherwise `0`.

### `get_biome_tilemap(world, chunk, biome_id)`

Returns a cached biome-specific `TileMap` for a chunk. It looks up tileset metadata in `BIOME_TABLE`, builds a biome mask, wires neighbor resolution through `get_neighbor_biome_mask_value`, and caches the tilemap in `chunk.runtime["biome_tilemaps"][biome_id]`.

### `get_scaled_biome_sprite(world, chunk, biome_id, idx)`

Returns a scaled biome overlay sprite for a biome/tile index pair. Sprites are cached in nested dictionaries under `chunk.runtime["biome_sprite_cache"][biome_id][idx]`. Returns `None` if there is no raw sprite.

### `get_biome_surface(world, chunk)`

Builds and returns the composited biome overlay surface for a chunk. It skips biome IDs outside `AUTOTILED_BIOMES`, renders only matching biome tiles, caches the surface in `chunk.runtime["biome_surface"]`, and reuses the cache while the chunk is clean.

### `get_chunk_surface(world, chunk)`

Builds and returns the static terrain surface for a chunk. The surface includes:

- A shallow-water base fill.
- Deep-ocean overlay.
- Base land tiles where `chunk.layers["base"]` equals `1`.
- Biome overlays.
- Soil/farming overlay from `get_soil_surface`.

The result is cached in `chunk.runtime["surface"]`. The function sets `chunk.dirty = False` after rebuilding.

### `ensure_chunk_water_objects(chunk)`

Synchronizes animated shallow-water objects for a chunk. It creates `WaterTile` objects for water tiles that are not deep ocean, removes stale water objects from the runtime cache, and returns the active water objects.

Cache key: world tile coordinate in `chunk.runtime["water_objects"]`.

### `ensure_chunk_tree_objects(chunk)`

Synchronizes runtime `Tree` objects from tree records in `chunk.props`. It removes stale entries, creates missing trees with `Tree.from_tree_record`, and returns the active tree objects.

Cache key: `(world_tile, species)` in `chunk.runtime["tree_objects"]`.

### `ensure_chunk_house_objects(chunk)`

Synchronizes runtime `House` objects from house records in `chunk.props`. It removes stale entries, creates missing houses with `House(record)`, and returns the active house objects.

Cache key: record `id` in `chunk.runtime["house_objects"]`.

### `ensure_chunk_environment_objects(chunk)`

Synchronizes runtime `EnvironmentProp` objects from environment records in `chunk.props`.

It also finalizes removed blocking props:

- Finds removed environment records whose map tile has not yet been cleared.
- Clears matching decoration-layer entries.
- Clears collision-layer entries for movement-blocking props.
- Marks the chunk dirty.
- Sets `record["tile_cleared"] = True`.

Then it removes stale runtime props, creates missing `EnvironmentProp` instances, and returns only props whose `alive` attribute is truthy.

Cache key: record `id` in `chunk.runtime["environment_objects"]`.

### `collect_chunk_objects(chunk, soil_layer=None)`

Collects all runtime/renderable objects associated with one chunk:

- Shallow-water objects.
- Trees.
- Houses.
- Environment props.
- Plant objects when `soil_layer` is provided.
- Direct prop objects that already expose `rect` and `image`.
- Chunk entities that expose `rect`.

### `prewarm_chunk_runtime(chunk, world=None)`

Creates common runtime caches for a chunk before gameplay needs them. It ensures tree, house, environment, and water objects exist. If `world` is supplied, it also builds the chunk surface.

### `update_world_objects(visible_chunks, player, dt, soil_layer=None)`

Updates runtime objects in all visible chunks once per frame. It avoids duplicate updates by object identity and passes `near_chunks` when an object's `update` method accepts that signature, falling back to `update(dt)` when needed.

### `collect_y_sorted_objects(visible_chunks, player, soil_layer=None, npc_manager=None)`

Returns the list of objects that should be y-sorted for actor-style rendering. It includes the player, visible NPCs, non-ground chunk objects, and attached objects returned by `iter_attached_objects`.

Duplicate objects are skipped by identity.

### `collect_player_collision_objects(world)`

Returns nearby collision objects for player movement. It checks chunks within radius `1` around the current player chunk and includes living trees, houses, and environment props with non-empty collision boxes.

### `collect_rock_collision_objects(world)`

Returns nearby environment props whose `prop_type` is `"rock"`. This helper is specific to rock collisions/interactions.

### `collect_pickups_near_player(world, player)`

Attempts to pick up nearby loose items. It checks shell and rock-piece props in chunks near the player, calls `prop.pickup(player.inventory)`, marks the chunk dirty, invalidates the chunk render cache, and returns `True` after the first successful pickup. Returns `False` if nothing was collected.

### `spawn_rock_piece_drops(chunk, rock, amount)`

Creates rock-piece environment records when a rock breaks.

Behavior:

- Does nothing when `amount <= 0`.
- Chooses small rock-piece assets from `list_environment_assets("rocks", "small")`, falling back to `"rocks/small/r1.png"`.
- Uses a deterministic `random.Random` seeded by `rock.prop_id`.
- Places pieces around the rock using fixed offsets plus small jitter.
- Appends new environment records to `chunk.props`.
- Resets `chunk.runtime["environment_objects"]` and marks the chunk dirty.

### `get_world_hint_font()`

Returns the cached world-hint font. The first call loads `font/LycheeSoda.ttf` at size `20` into `_WORLD_HINT_FONT`.

### `get_bobber_icon()`

Returns the cached fishing bobber icon. The first call loads `graphics/icons/bobber.png`, converts it with alpha, scales it to `24x24`, and stores it in `_BOBBER_ICON`.

### `get_player_fishing_water_rect(world, player)`

Returns a `pygame.Rect` for a fishable water tile in front of the player, checking distance `1` then `2`. Returns `None` if the player does not expose fishing helpers or no facing tile is fishable.

### `get_contextual_world_hint(world, player)`

Determines the next contextual hint to display near the player. It tracks seen hints on `player.world_hint_seen`.

Priority:

1. Nearby loose shell or rock-piece pickup: `"collect_loose_item"`.
2. Nearby rock or tree resource requiring axe selection: `"select_axe"`.
3. Nearby rock or tree resource ready to break: `"break_resource"`.
4. Fishable water while no resource is nearby:
   - Active fishing with bite: `"reel_fishing_line"`.
   - Fishing rod not selected: `"select_fishing_rod"`.
   - Ready to cast: `"cast_fishing_line"`.

Returns a tuple of `(hint_id, message, target_rect)` or `None`.

### `draw_player_world_hint(screen, world, player, camera, dt)`

Draws the active contextual hint bubble above the target object/tile. It updates `player.world_hint_elapsed`, renders text, draws a rounded bubble with a pointer, and applies a small sine-wave bobbing offset.

### `draw_fishing_overlay(screen, player, camera)`

Draws fishing UI in the world when the player is actively fishing. It renders the bobber icon, line from player to bobber, and optional fishing message above the bobber.

### `draw_world(screen, world, player, camera, dt, soil_layer=None, npc_manager=None)`

Main world-rendering function.

Responsibilities:

- Clears the screen.
- Finds loaded chunks visible in the camera viewport.
- Updates visible world objects.
- Draws each visible chunk's cached terrain surface.
- Draws animated shallow-water objects.
- Draws active chunk coordinate labels.
- Collects and y-sorts player, NPCs, and world objects.
- Draws sprite images, fallback rectangles, swim visuals, and debug collision boxes for rocks/player feet.
- Draws fishing overlay and contextual hint bubble.
- Draws debug text for player position, chunk, island difficulty, loaded chunks, active chunks, next-island key, and NPC count.

### `draw_transition_overlay(screen, message, subtitle=None, alpha=170)`

Draws a translucent full-screen transition overlay with a centered message and optional subtitle.

### `get_chunk_biome_name(chunk)`

Returns the dominant biome name for a chunk. It counts all biome IDs in `chunk.layers["biome"]`, selects the most frequent ID, and looks up its `"name"` in `BIOME_TABLE`.

### `bind_player_to_world(player, world, soil_layer)`

Repositions and rebinds an existing player to a new world.

It:

- Moves the player to `world.get_spawn_position()`.
- Syncs the player's main and collision rects.
- Clears movement direction.
- Reassigns `player.soil_layer`.
- Binds the swim visual to the new world.
- Sets `player.rock_drop_callback` to `spawn_rock_piece_drops`.

### `load_next_island(world_run, player, assets, screen)`

Advances the `WorldRun`, creates the next world, creates a new `SoilLayer`, rebinds the existing player, creates a new `GameplayHUD`, updates active chunks, and returns:

`(world, soil_layer, hud, None, player_chunk)`

The fourth value is `None` for `npc_manager`, causing NPCs to be recreated after the new world's chunk queue finishes loading.

### `run_game_loop(screen, clock, world_run, world, player, camera, last_player_chunk, assets, soil_layer=None, hud=None, npc_manager=None)`

Runs the active gameplay loop until the player quits or presses Escape.

Per-frame responsibilities:

- Computes `dt` from `clock.tick(FPS)`.
- Handles quit, HUD input, Escape, camera zoom, next-island loading, pickup input, and hint acknowledgement.
- Updates player, weather, soil, camera, active chunks, and NPCs.
- Processes pending chunk loads with `prewarm_chunk_runtime`.
- Creates an `NPCManager` once chunks finish loading.
- Draws the world, weather, HUD, transition overlay, and flips the display.

Special controls:

- Escape quits gameplay.
- `=` or `+` zooms in.
- `-` zooms out.
- `N` advances to the next island.
- `E` or `P` picks up nearby loose items.

### `main()`

Program entry point.

It:

- Creates a borderless display at `SCREEN_WIDTH x SCREEN_HEIGHT`.
- Sets the window caption to `"Oceans Apart"`.
- Creates the clock and `StartupFlow`.
- Runs the startup loop until startup is complete or the user quits.
- Passes startup-created objects into `run_game_loop`.
- Calls `pygame.quit()` after gameplay exits.

### `if __name__ == "__main__": main()`

Runs `main()` when `code/main.py` is executed directly.

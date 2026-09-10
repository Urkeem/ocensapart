"""Oceans Apart application entry point.

Gameplay responsibilities live in the gameplay package. This module only
initializes Pygame, runs the startup flow, and hands the resulting state to the
active game session.
"""

import asyncio
import multiprocessing

import pygame

from gameplay.config import FPS
from gameplay.session import run_game_loop
from gameplay.startup import StartupFlow


async def main():
    pygame.init()
    display_info = pygame.display.Info()
    screen = pygame.display.set_mode(
        (display_info.current_w, display_info.current_h),
        pygame.NOFRAME,
    )
    pygame.display.set_caption("Oceans Apart")
    clock = pygame.time.Clock()
    startup = StartupFlow(screen)

    while not startup.done:
        clock.tick(FPS)
        for event in startup.controller_input.get_events():
            if event.type == pygame.QUIT:
                pygame.quit()
                return
            if (
                event.type == pygame.KEYDOWN
                and event.key == pygame.K_ESCAPE
                and startup.stage == "title"
            ):
                pygame.quit()
                return
            startup.handle_event(event)
            if startup.quit_requested:
                pygame.quit()
                return

        await startup.update()
        startup.draw()
        pygame.display.flip()

    await run_game_loop(
        screen,
        clock,
        startup.world_run,
        startup.world,
        startup.player,
        startup.camera,
        startup.last_player_chunk,
        startup.assets,
        startup.soil_layer,
        startup.hud,
        startup.npc_manager,
        startup.loaded_save_data,
    )
    pygame.quit()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    asyncio.run(main())

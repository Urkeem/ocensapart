"""Settings screen widgets and configuration constants."""

import pygame
from typing import Tuple, Union

import random
# screen

SCREEN_WIDTH = 1280
SCREEN_HEIGHT = 720
TILE_SIZE = 64
CHUNK_SIZE = (9, 12)

# overlay positions 
OVERLAY_POSITIONS = {
	'tool': (40, SCREEN_HEIGHT - 15),
	'seed': (80, SCREEN_HEIGHT - 5)}

PLAYER_TOOL_OFFSET = {
	'left': pygame.Vector2(-50, 40),
	'right': pygame.Vector2(50, 40),
	'up': pygame.Vector2(0, -10),
	'down': pygame.Vector2(0, 50)
}

LAYERS = {
	'water': 0,
	'ground': 1,
	'soil': 2,
	'soil water': 3,
	'dock': 4,
	'rain floor': 5,
	'house bottom': 6,
	'ground plant': 7,
	'main': 8,
	'house top': 9,
	'fruit': 10,
	'wind': 11,
	'rain drops': 12,
	'clouds': 13
}

APPLE_POS = {
	'coconut': [(18, 17), (30, 37), (12, 50), (30, 45), (20, 30), (30, 10)],
	'Large': [(30, 24), (60, 65), (50, 50), (16, 40), (45, 50), (42, 70)]
}

GROW_SPEED = {
	'corn': 1,
	'tomato': 0.7
}

SALE_PRICES = {
	'wood': 4,
	'apple': 2,
	'corn': 10,
	'tomato': 20
}
PURCHASE_PRICES = {
	'corn': 4,
	'tomato': 5
}

loaded = []  # --> use it to look up the interior name
focus = 1.6  # focuses the player in the center.


class Button:
	def __init__(self, image, pos: Tuple[int, int],
				 scale: Union[float, Tuple[int, int]], display_surface: pygame.Surface,
				 anchor: str = "center"):
		"""
		image: Surface or file path
		pos: (x, y) position; interpreted by 'anchor'
		scale: float (uniform) or (width, height) in pixels
		display_surface: where to blit the button
		anchor: 'center' or 'topleft' (how pos is applied)
		"""
		img = image

		# Scale image
		if isinstance(scale, (int, float)):
			w, h = img.get_size()
			size = (max(1, int(w * scale)), max(1, int(h * scale)))
		else:
			size = (int(scale[0]), int(scale[1]))
		self.image = pygame.transform.smoothscale(img, size)

		self.display_surface = display_surface
		self.rect = self.image.get_rect()
		if anchor == "center":
			self.rect.center = pos
		else:
			self.rect.topleft = pos

		# For edge-triggered click detection
		self._was_down_last_frame = False

		# Optional visual tweak sizes
		self._hover_border_inflate = 6  # pixels
		self._hover_border_width = 2
		self._hover_border_radius = 8
		self.show = True

	def is_hovered(self) -> bool:
		"""Return True if mouse is over the button."""
		return self.rect.collidepoint(pygame.mouse.get_pos())

	def is_clicked(self) -> bool:
		"""
		Return True exactly once when the left mouse button is pressed
		while the cursor is over the button (edge-triggered).
		"""
		mouse_down = pygame.mouse.get_pressed()[0]
		hovered = self.is_hovered()
		clicked = hovered and mouse_down and not self._was_down_last_frame
		self._was_down_last_frame = mouse_down
		return clicked

	def display_button(self):
		"""
		Draw the button. If hovered, draw a subtle border around it.
		Call this every frame before flipping the display.
		"""
		# Optional hover outline
		if self.show:
			if self.is_hovered():
				outline_rect = self.rect.inflate(self._hover_border_inflate, self._hover_border_inflate)
				pygame.draw.rect(self.display_surface, (255, 255, 255), outline_rect, width=self._hover_border_width, border_radius=self._hover_border_radius)
			# Draw the button image itself
			self.display_surface.blit(self.image, self.rect)


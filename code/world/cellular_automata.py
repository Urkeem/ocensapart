"""Cellular automata utilities used to smooth generated terrain masks."""

import random


class CellularAutomata:
    def __init__(
        self,
        map_dim=(100, 100),
        wall_chance=0.52,
        oob="wall",
        cutoff=(3, 5),
        rng=None
    ):
        self.width = map_dim[0]
        self.height = map_dim[1]
        self.wall_chance = wall_chance
        self.oob = oob
        self.cutoff = cutoff
        self.rng = rng if rng is not None else random.Random()  # Random number Generator
        self.map = self.generate_base_map()

    def generate_base_map(self):
        """
        Generates the random map through which cellular automata iterates.
        :return:
        """
        map_data = []
        for _ in range(self.width * self.height):
            if self.rng.random() < self.wall_chance:
                map_data.append(1)
            else:
                map_data.append(0)
        return map_data

    def count_adjacent_walls(self, map_data, index):
        """
        This functon takes in the base map and the index under inspection
        :param map_data:
        :param index:
        :return:
        """
        count = 0

        y = index // self.width
        x = index % self.width

        for dy in range(-1, 2):
            for dx in range(-1, 2):
                if dx == 0 and dy == 0:
                    continue

                new_y = y + dy
                new_x = x + dx

                if 0 <= new_y < self.height and 0 <= new_x < self.width:
                    adjacent_index = new_y * self.width + new_x
                    if map_data[adjacent_index] == 1:
                        count += 1
                else:
                    if self.oob == "floor":
                        pass
                    elif self.oob == "wall":
                        count += 1
                    elif self.oob == "random":
                        if self.rng.random() > 0.5:
                            count += 1
                    elif self.oob == "mirror":
                        if map_data[index] == 1:
                            count += 1
                    else:
                        count += 1

        return count

    def apply_cellular_automata_rules(self, map_data):
        new_map = [0] * (self.width * self.height)

        zero_limit = 4
        if self.cutoff[0] is not None:
            zero_limit = self.cutoff[0] + 1

        one_limit = 5
        if self.cutoff[1] is not None:
            one_limit = self.cutoff[1]

        for i in range(self.width * self.height):
            wall_count = self.count_adjacent_walls(map_data, i)

            if map_data[i] == 1:
                new_map[i] = 0 if wall_count < zero_limit else 1
            else:
                new_map[i] = 1 if wall_count >= one_limit else 0

        return new_map

    def get_map(self, steps=5):
        map_data = self.map[:]

        for _ in range(steps):
            map_data = self.apply_cellular_automata_rules(map_data)

        self.map = map_data
        return map_data

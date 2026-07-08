#include <stdlib.h>
#include <time.h>

#ifdef _WIN32
#define EXPORT __declspec(dllexport)
#else
#define EXPORT
#endif

EXPORT void seed_ca(unsigned int seed) {
    srand(seed);
}

static int get_cell(const int *grid, int width, int height, int row, int col) {
    if (row < 0 || row >= height || col < 0 || col >= width) {
        return 0;
    }
    return grid[row * width + col];
}

static int count_neighbors(const int *grid, int width, int height, int row, int col) {
    int count = 0;

    for (int dr = -1; dr <= 1; dr++) {
        for (int dc = -1; dc <= 1; dc++) {
            if (dr == 0 && dc == 0) continue;
            count += get_cell(grid, width, height, row + dr, col + dc);
        }
    }

    return count;
}

static void step_ca_2d_internal(const int *src, int *dst, int width, int height) {
    for (int row = 0; row < height; row++) {
        for (int col = 0; col < width; col++) {
            int index = row * width + col;
            int current = src[index];
            int neighbors = count_neighbors(src, width, height, row, col);

            if (current == 1) {
                dst[index] = (neighbors >= 4) ? 1 : 0;
            } else {
                dst[index] = (neighbors >= 5) ? 1 : 0;
            }
        }
    }
}

EXPORT int* generate_ca_world(int width, int height, float fill_chance, int steps) {
    if (width <= 0 || height <= 0 || steps < 0) return NULL;

    int size = width * height;

    int *grid_a = (int *)malloc(size * sizeof(int));
    int *grid_b = (int *)malloc(size * sizeof(int));

    if (grid_a == NULL || grid_b == NULL) {
        free(grid_a);
        free(grid_b);
        return NULL;
    }

    for (int i = 0; i < size; i++) {
        float r = (float)rand() / (float)RAND_MAX;
        grid_a[i] = (r < fill_chance) ? 1 : 0;
    }

    for (int s = 0; s < steps; s++) {
        step_ca_2d_internal(grid_a, grid_b, width, height);

        int *tmp = grid_a;
        grid_a = grid_b;
        grid_b = tmp;
    }

    free(grid_b);
    return grid_a;
}

EXPORT void free_ca_world(int *grid) {
    free(grid);
}
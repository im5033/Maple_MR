import time
import numpy as np
import cv2 as cv
import os
import math

# DEFINE CV Variables
RUNE_BGRA = (255, 102, 221, 255)

def find_arrow_directions(img, debug=False):
    bgr = cv.cvtColor(img, cv.COLOR_BGRA2BGR)
    hsv = cv.cvtColor(bgr, cv.COLOR_BGR2HSV)
    h, s, v = cv.split(hsv)
    m, n = len(h), len(h[0])
    valid_gradient = []
    directions = []

    if debug:
        visited = [[False for _ in range(n)] for _ in range(m)]
        canvas = np.zeros(img.shape[:2], dtype="uint8")

    def hue_is_red(r, c):
        return 5 <= h[r][c] <= 12 and s[r][c] >= 65 and v[r][c] >= 128

    def hue_is_valid(r1, c1, r2, c2, diff):
        return abs(int(h[r1][c1]) - int(h[r2][c2])) <= diff and s[r2][c2] >= 150 and v[r2][c2] >= 150 and h[r2][c2] <= 70

    def near_gradient(r, c):
        for i, j in valid_gradient:
            if abs(i-r) < 15 and abs(c-j) < 15:
                return True
        return False

    def gradient_exists(r1, c1, delta_r, delta_c):
        if near_gradient(r1, c1):
            return False

        tmp_r1, tmp_c1 = r1, c1
        rune_gradient = False
        # The directional arrows that appear in runes are around 30 pixels long.
        for _ in range(30):
            r2 = tmp_r1 + delta_r
            c2 = tmp_c1 + delta_c
            if 0 <= r2 < m and 0 <= c2 < n:
                # Check if the next pixel maintains the gradient.
                if hue_is_valid(tmp_r1, tmp_c1, r2, c2, 10):
                    # If the pixel is a green-ish color, it is a possible arrow.
                    if 50 <= h[r2][c2] <= 70:
                        rune_gradient = True
                        valid_gradient.append((r1, c1))
                        break
                    tmp_r1 = r2
                    tmp_c1 = c2
                else:
                    break
            else:
                break

        return rune_gradient

    def expand_gradient(r1, c1, direction):
        stack = [(r1, c1)]
        while stack:
            r2, c2 = stack.pop()
            visited[r2][c2] = True
            if r2 + 1 < m:
                if not visited[r2 + 1][c2] and hue_is_valid(r2, c2, r2 + 1, c2, 2 if direction else 10):
                    stack.append((r2 + 1, c2))
            if r2 - 1 >= 0:
                if not visited[r2 - 1][c2] and hue_is_valid(r2, c2, r2 - 1, c2, 2 if direction else 10):
                    stack.append((r2 - 1, c2))
            if c2 + 1 < n:
                if not visited[r2][c2 + 1] and hue_is_valid(r2, c2, r2, c2 + 1, 10 if direction else 2):
                    stack.append((r2, c2 + 1))
            if c2 - 1 >= 0:
                if not visited[r2][c2 - 1] and hue_is_valid(r2, c2, r2, c2 - 1, 10 if direction else 2):
                    stack.append((r2, c2 - 1))
            canvas[r2][c2] = 180

    def find_direction(r, c):
        if gradient_exists(r, c, 0, -1):
            return "right"
        elif gradient_exists(r, c, 0, 1):
            return "left"
        elif gradient_exists(r, c, -1, 0):
            return "down"
        elif gradient_exists(r, c, 1, 0):
            return "up"
        else:
            return None

    _, imw, _ = img.shape
    rune_left_bound = math.trunc((imw - 500)/2)
    rune_right_bound = rune_left_bound + 500

    # The rune captcha was observed to appear within this part of the application window on 1366x768 resolution.
    for r in range(150, 300):
        for c in range(rune_left_bound, rune_right_bound):
            # Arrows start at a red-ish color and are around 15 pixels apart.
            if hue_is_red(r, c) and not near_gradient(r, c):
                direction = find_direction(r, c)
                if direction:
                    directions.append((direction, (r, c)))
                    if debug:
                        if direction == "LEFT" or direction == "RIGHT":
                            expand_gradient(r, c, 1)
                        else:
                            expand_gradient(r, c, 0)

    if debug:
        cv.imshow("Hue", h)
        cv.imshow("Saturation", s)
        cv.imshow("Value", v)
        cv.imshow("Original", img)
        cv.imshow("Parsed", canvas)
        cv.waitKey(0)

    return sorted(directions, key=lambda x: x[1][1])

def solve_rune_raw():
    #assumes user is already at rune
    output = "A.png"
    for filename in os.listdir(r"C:\Users\MR\Documents\auto_maple_MR"):
        if filename.lower().endswith((".png", ".jpg")):  # 過濾圖片格式
            output = os.path.join(r"C:\Users\MR\Documents\auto_maple_MR", filename)
            data = find_arrow_directions(cv.imread(output))
            print(data)
            if len(data) == 4:
                directions = [direction for direction, _ in data]
                print(f"{filename} Directions: {directions}")

if __name__ == "__main__":
    solve_rune_raw()
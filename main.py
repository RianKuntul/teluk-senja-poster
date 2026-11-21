#!/usr/bin/env python3
"""Teluk Senja - a travel poster for a place that isn't there.

A bay where every hour is golden hour: the sun never quite sets, a
lighthouse stands on a black-rock pinnacle, and the shore glows at night
with bioluminescent plankton.

Standard library only (struct + zlib PNG encoder, hand-rolled raster
engine, hand-drawn 5x7 bitmap font). No network. Deterministic: the same
seed always paints the same bay. Writes /output/entry.png (1024x1024).
"""

import math
import os
import random
import struct
import zlib

W = 1024
H = 1024
HORIZON = 600
OUT = "/output/entry.png"

# One fixed seed, so every run paints the identical poster.
RNG = random.Random(20261121)


def clamp(v, lo=0, hi=255):
    return lo if v < lo else hi if v > hi else int(v)


def lerp(a, b, t):
    return a + (b - a) * t


def lerp_color(c1, c2, t):
    return tuple(clamp(round(lerp(a, b, t))) for a, b in zip(c1, c2))


# ---------------------------------------------------------------- canvas

class Canvas:
    """A plain RGB frame buffer with the drawing primitives we need."""

    def __init__(self, w, h):
        self.w = w
        self.h = h
        self.px = bytearray(w * h * 3)

    def set(self, x, y, color):
        if 0 <= x < self.w and 0 <= y < self.h:
            i = (y * self.w + x) * 3
            self.px[i:i + 3] = bytes(color)

    def blend(self, x, y, color, alpha):
        """Paint color over the pixel with the given opacity (0..1)."""
        if 0 <= x < self.w and 0 <= y < self.h and 0.0 < alpha <= 1.0:
            i = (y * self.w + x) * 3
            for k in range(3):
                self.px[i + k] = clamp(
                    round(self.px[i + k] * (1.0 - alpha) + color[k] * alpha))

    def hline(self, x0, x1, y, color):
        if x1 < x0:
            x0, x1 = x1, x0
        x0 = max(0, x0)
        x1 = min(self.w - 1, x1)
        for x in range(x0, x1 + 1):
            self.set(x, y, color)

    def vline(self, x, y0, y1, color):
        if y1 < y0:
            y0, y1 = y1, y0
        y0 = max(0, y0)
        y1 = min(self.h - 1, y1)
        for y in range(y0, y1 + 1):
            self.set(x, y, color)

    def line(self, x0, y0, x1, y1, color):
        """Bresenham line."""
        dx = abs(x1 - x0)
        dy = -abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        while True:
            self.set(x0, y0, color)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy

    def fill_rect(self, x0, y0, x1, y1, color):
        for y in range(max(0, y0), min(self.h, y1 + 1)):
            self.hline(x0, x1, y, color)

    def fill_circle(self, cx, cy, r, color):
        for y in range(cy - r, cy + r + 1):
            dy = y - cy
            dx = int(math.sqrt(max(0, r * r - dy * dy)))
            self.hline(cx - dx, cx + dx, y, color)

    def glow_circle(self, cx, cy, r, color, peak_alpha):
        """Soft radial glow: brightest at the centre, fading to nothing."""
        for y in range(cy - r, cy + r + 1):
            for x in range(cx - r, cx + r + 1):
                d = math.hypot(x - cx, y - cy)
                if d < r:
                    self.blend(x, y, color, peak_alpha * (1.0 - d / r))

    def fill_poly(self, points, color):
        """Scanline polygon fill (even-odd rule)."""
        ys = [p[1] for p in points]
        y0 = max(0, min(ys))
        y1 = min(self.h - 1, max(ys))
        n = len(points)
        for y in range(y0, y1 + 1):
            xs = []
            for i in range(n):
                x0, yy0 = points[i]
                x1, yy1 = points[(i + 1) % n]
                if (yy0 <= y < yy1) or (yy1 <= y < yy0):
                    t = (y - yy0) / (yy1 - yy0)
                    xs.append(x0 + t * (x1 - x0))
            xs.sort()
            for i in range(0, len(xs) - 1, 2):
                self.hline(int(math.ceil(xs[i])), int(math.floor(xs[i + 1])),
                           y, color)


# ---------------------------------------------------------------- PNG out

def _chunk(tag, data):
    return (struct.pack(">I", len(data)) + tag + data +
            struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))


def write_png(canvas, path):
    """Encode the canvas as a plain 8-bit RGB PNG (filter 0 scanlines)."""
    raw = bytearray()
    stride = canvas.w * 3
    for y in range(canvas.h):
        raw.append(0)
        raw += canvas.px[y * stride:(y + 1) * stride]
    png = b"\x89PNG\r\n\x1a\n"
    png += _chunk(b"IHDR", struct.pack(">IIBBBBB",
                                       canvas.w, canvas.h, 8, 2, 0, 0, 0))
    png += _chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    png += _chunk(b"IEND", b"")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(png)


# ---------------------------------------------------------------- palette

SKY_TOP = (46, 22, 86)        # dusk violet, high up
SKY_MID = (150, 64, 124)      # rose band
SKY_HORIZON = (255, 158, 66)  # golden orange at the waterline
SUN_CORE = (255, 226, 140)
SUN_EDGE = (255, 172, 82)
SEA_TOP = (18, 46, 76)        # dark teal where sea meets sky
SEA_DEEP = (6, 18, 40)        # almost-black water at the bottom
ROCK = (16, 12, 28)           # black-rock silhouettes
GOLD = (255, 196, 96)         # sun glitter on the water
GLOW_CYAN = (110, 255, 214)   # bioluminescent sparkle
GLOW_GREEN = (140, 255, 150)


# ---------------------------------------------------------------- sky, sun, sea

def paint_sky(cv):
    """Vertical sunset gradient, violet above, gold at the horizon."""
    for y in range(HORIZON):
        t = y / HORIZON
        if t < 0.55:
            color = lerp_color(SKY_TOP, SKY_MID, t / 0.55)
        else:
            color = lerp_color(SKY_MID, SKY_HORIZON, (t - 0.55) / 0.45)
        cv.hline(0, W - 1, y, color)
    # A few thin, slow cloud streaks catching the last light.
    for _ in range(26):
        cy = RNG.randint(60, 480)
        cx = RNG.randint(0, W - 300)
        length = RNG.randint(120, 320)
        thick = RNG.randint(2, 5)
        tint = lerp_color(SKY_MID, (255, 190, 130), RNG.random() * 0.7)
        for dy in range(thick):
            for x in range(cx, cx + length):
                fade = 1.0 - abs(x - (cx + length / 2)) / (length / 2)
                cv.blend(x, cy + dy, tint, 0.10 * fade)


def paint_sun(cv):
    """Low round sun sitting on the horizon, with a soft halo."""
    cx, cy = 512, HORIZON - 16
    cv.glow_circle(cx, cy, 190, (255, 150, 70), 0.28)
    cv.glow_circle(cx, cy, 120, (255, 190, 100), 0.35)
    cv.fill_circle(cx, cy, 64, SUN_EDGE)
    cv.fill_circle(cx, cy, 56, SUN_CORE)
    cv.fill_circle(cx, cy, 38, (255, 240, 185))


def paint_sea(cv):
    """Dark bay water, deepening toward the bottom of the frame."""
    for y in range(HORIZON, H):
        t = (y - HORIZON) / (H - HORIZON)
        color = lerp_color(SEA_TOP, SEA_DEEP, t)
        cv.hline(0, W - 1, y, color)
    # Gentle swell lines, barely lighter than the water around them.
    for y in range(HORIZON + 12, H, 14):
        shade = lerp_color(SEA_TOP, (70, 110, 150),
                           0.10 + 0.08 * math.sin(y * 0.05))
        cv.hline(0, W - 1, y, shade)


def paint_reflection(cv):
    """The sun's glittering path: a widening column of gold dashes."""
    cx = 512
    for _ in range(520):
        y = RNG.randint(HORIZON + 6, H - 8)
        depth = (y - HORIZON) / (H - HORIZON)
        half = int(46 + depth * 150)
        x = cx + RNG.randint(-half, half)
        length = RNG.randint(6, 34)
        strength = (1.0 - abs(x - cx) / max(1, half)) * (1.0 - depth * 0.55)
        alpha = 0.25 + 0.65 * strength * RNG.random()
        for dx in range(length):
            cv.blend(x + dx, y, GOLD, alpha)
    # A brighter, steadier core right under the sun.
    for _ in range(160):
        y = RNG.randint(HORIZON + 4, HORIZON + 150)
        x = 512 + RNG.randint(-52, 52)
        cv.blend(x, y, (255, 225, 150), 0.75)


# ------------------------------------------------------- land & light

def paint_headland(cv):
    """A distant black headland closing the bay on the left."""
    cv.fill_poly([(0, HORIZON), (0, 560), (60, 540), (150, 566),
                  (240, 548), (330, 580), (420, 592), (430, HORIZON)],
                 ROCK)
    # A second, lower ridge on the right, far away.
    cv.fill_poly([(700, HORIZON), (760, 572), (850, 580), (940, 566),
                  (1024, 584), (1024, HORIZON)], ROCK)


def paint_rock_and_lighthouse(cv):
    """Black-rock pinnacle on the right, lighthouse on top, beam sweeping."""
    # The pinnacle: a steep jagged rock rising out of the water.
    cv.fill_poly([(742, HORIZON + 30), (760, 520), (742, 470), (770, 430),
                  (800, 448), (812, 500), (836, 560), (858, HORIZON + 30)],
                 ROCK)
    cv.fill_poly([(770, 430), (788, 420), (806, 430)], (30, 22, 46))
    # Lighthouse tower: cream body with dark red bands, slightly tapered.
    tower_x = 768
    tower_top = 330
    tower_base = 432
    for y in range(tower_top, tower_base):
        t = (y - tower_top) / (tower_base - tower_top)
        half = int(lerp(13, 19, t))
        if 18 <= (y - tower_top) % 34 < 30:
            color = (168, 52, 48)      # red band
        else:
            color = (238, 226, 205)    # cream
        cv.hline(tower_x - half, tower_x + half, y, color)
    # Gallery rail and lamp room.
    cv.fill_rect(tower_x - 17, tower_top - 8, tower_x + 17, tower_top - 2,
                 (40, 34, 52))
    cv.fill_rect(tower_x - 11, tower_top - 30, tower_x + 11, tower_top - 8,
                 (255, 226, 140))
    cv.fill_rect(tower_x - 13, tower_top - 36, tower_x + 13, tower_top - 30,
                 (40, 34, 52))
    # Dome cap.
    cv.fill_poly([(tower_x - 13, tower_top - 36), (tower_x, tower_top - 50),
                  (tower_x + 13, tower_top - 36)], (168, 52, 48))
    # The beam: a wide wedge of light sweeping left across the bay.
    lamp_x, lamp_y = tower_x, tower_top - 19
    for step in range(420):
        t = step / 420.0
        bx = int(lamp_x - 30 - t * 560)
        spread = int(8 + t * 46)
        alpha = 0.30 * (1.0 - t * 0.75)
        for dy in range(-spread, spread + 1):
            cv.blend(bx, lamp_y + dy, (255, 240, 190), alpha)
    # A fainter second beam to the right, over open water.
    for step in range(180):
        t = step / 180.0
        bx = int(lamp_x + 20 + t * 190)
        spread = int(6 + t * 22)
        alpha = 0.16 * (1.0 - t * 0.7)
        for dy in range(-spread, spread + 1):
            cv.blend(bx, lamp_y + dy, (255, 240, 190), alpha)
    # Lamp glow halo.
    cv.glow_circle(lamp_x, lamp_y, 46, (255, 230, 160), 0.55)


def paint_shoreline_sparkle(cv):
    """Bioluminescent plankton glowing along a curving shore, bottom left."""
    # The shore curve: from the left edge, sweeping down-right.
    for x in range(0, 560, 3):
        y = int(760 + 150 * math.sin(x / 560.0 * math.pi * 0.62)
                + 40 * math.sin(x * 0.02))
        y = min(H - 12, max(HORIZON + 90, y))
        for _ in range(3):
            dx = RNG.randint(-4, 4)
            dy = RNG.randint(-3, 6)
            color = GLOW_CYAN if RNG.random() < 0.6 else GLOW_GREEN
            cv.blend(x + dx, y + dy, color, 0.55 + 0.45 * RNG.random())
    # Scattered glowing dots drifting in the shallows near the shore.
    for _ in range(240):
        x = RNG.randint(0, 620)
        y = RNG.randint(820, H - 10)
        color = GLOW_CYAN if RNG.random() < 0.5 else GLOW_GREEN
        cv.blend(x, y, color, 0.35 + 0.55 * RNG.random())
        if RNG.random() < 0.3:
            cv.blend(x + 1, y, color, 0.4)


def paint_sailboat(cv):
    """A small sailboat drifting on the bay, left of the sun's path."""
    bx, by = 380, 700  # waterline under the hull
    # Hull: dark silhouette with a warm rim where the sun catches it.
    cv.fill_poly([(bx - 34, by), (bx + 34, by), (bx + 22, by + 12),
                  (bx - 22, by + 12)], (24, 16, 36))
    cv.hline(bx - 34, bx + 34, by, (255, 190, 110))
    # Mast and boom.
    cv.vline(bx, by - 66, by, (24, 16, 36))
    cv.line(bx, by - 62, bx + 26, by - 8, (24, 16, 36))
    # Two sails glowing in the sunset: a tall main sail and a small jib.
    cv.fill_poly([(bx + 3, by - 62), (bx + 3, by - 10), (bx + 26, by - 10)],
                 (255, 226, 178))
    cv.fill_poly([(bx - 3, by - 58), (bx - 3, by - 10), (bx - 24, by - 10)],
                 (240, 196, 140))
    # Its own little gold reflection on the water.
    for _ in range(26):
        x = bx + RNG.randint(-26, 26)
        y = by + 14 + RNG.randint(0, 26)
        cv.blend(x, y, GOLD, 0.5)


def paint_birds(cv):
    """A few distant birds, simple dark chevrons in the sky."""
    for (bx, by, s) in [(300, 220, 14), (352, 196, 11), (700, 180, 13),
                        (742, 214, 9), (210, 300, 10), (820, 260, 11)]:
        cv.line(bx - s, by, bx, by - s // 2, (28, 18, 40))
        cv.line(bx, by - s // 2, bx + s, by, (28, 18, 40))


# ------------------------------------------------------------------- font

# Hand-drawn 5x7 bitmap glyphs, one string per row, '#' = ink.
GLYPHS = {
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "D": ("11110", "10001", "10001", "10001", "10001", "10001", "11110"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "G": ("01110", "10001", "10000", "10111", "10001", "10001", "01110"),
    "H": ("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
    "I": ("11111", "00100", "00100", "00100", "00100", "00100", "11111"),
    "J": ("00111", "00010", "00010", "00010", "00010", "10010", "01100"),
    "K": ("10001", "10010", "10100", "11000", "10100", "10010", "10001"),
    "L": ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    "N": ("10001", "11001", "10101", "10011", "10001", "10001", "10001"),
    "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    "S": ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "U": ("10001", "10001", "10001", "10001", "10001", "10001", "01110"),
    "V": ("10001", "10001", "10001", "10001", "10001", "01010", "00100"),
    "W": ("10001", "10001", "10001", "10101", "10101", "10101", "01010"),
    "Y": ("10001", "10001", "01010", "00100", "00100", "00100", "00100"),
}


def text_width(text, scale):
    """Total pixel width of text at the given scale (incl. spacing)."""
    return len(text) * (5 * scale + scale) - scale


def draw_text(cv, text, x, y, scale, color):
    """Stamp a string with the bitmap font, top-left corner at (x, y)."""
    cx = x
    for ch in text:
        glyph = GLYPHS.get(ch)
        if glyph is None:  # space or unknown: advance one character width
            cx += 6 * scale
            continue
        for row in range(7):
            for col in range(5):
                if glyph[row][col] == "1":
                    cv.fill_rect(cx + col * scale, y + row * scale,
                                 cx + (col + 1) * scale - 1,
                                 y + (row + 1) * scale - 1, color)
        cx += 6 * scale


def paint_title(cv):
    """Big readable place name at the top, subtitle beneath it."""
    title = "TELUK SENJA"
    scale = 9
    tw = text_width(title, scale)
    tx = (W - tw) // 2
    ty = 56
    # Soft dark halo so the cream letters read against the bright sky.
    draw_text(cv, title, tx + 3, ty + 4, scale, (40, 16, 60))
    draw_text(cv, title, tx, ty, scale, (255, 240, 214))
    subtitle = "WHERE EVERY HOUR IS GOLDEN HOUR"
    sscale = 3
    sw = text_width(subtitle, sscale)
    sx = (W - sw) // 2
    sy = ty + 7 * scale + 22
    draw_text(cv, subtitle, sx + 2, sy + 2, sscale, (40, 16, 60))
    draw_text(cv, subtitle, sx, sy, sscale, (255, 214, 150))


# -------------------------------------------------------------------- main

def main():
    cv = Canvas(W, H)
    paint_sky(cv)
    paint_sun(cv)
    paint_sea(cv)
    paint_reflection(cv)
    paint_headland(cv)
    paint_rock_and_lighthouse(cv)
    paint_shoreline_sparkle(cv)
    paint_sailboat(cv)
    paint_birds(cv)
    paint_title(cv)
    write_png(cv, OUT)
    print("wrote", OUT)


if __name__ == "__main__":
    main()


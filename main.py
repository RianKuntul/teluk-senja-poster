#!/usr/bin/env python3
"""TELUK SENJA — poster generator (stdlib only, no network, deterministic).

Draws a travel poster for an invented place: Teluk Senja, the bay where
every hour is golden hour. A lighthouse stands on a black-rock pinnacle
above a bioluminescent shore. Writes /output/entry.png (1024x1024).
"""
import math
import os
import random
import struct
import zlib

W = H = 1024
OUT = "/output/entry.png"

# ---------- tiny raster engine ----------
buf = bytearray(W * H * 3)


def px(x, y, r, g, b):
    if 0 <= x < W and 0 <= y < H:
        i = (y * W + x) * 3
        buf[i] = r
        buf[i + 1] = g
        buf[i + 2] = b


def blend(x, y, r, g, b, a):
    if 0 <= x < W and 0 <= y < H and a > 0:
        i = (y * W + x) * 3
        ia = 1.0 - a
        buf[i] = int(buf[i] * ia + r * a)
        buf[i + 1] = int(buf[i + 1] * ia + g * a)
        buf[i + 2] = int(buf[i + 2] * ia + b * a)


def lerp(c1, c2, t):
    return tuple(int(c1[k] + (c2[k] - c1[k]) * t) for k in range(3))


def vgrad(y0, y1, stops):
    for y in range(y0, y1):
        t = (y - y0) / max(1, (y1 - y0 - 1))
        for si in range(len(stops) - 1):
            t0, c0 = stops[si]
            t1, c1 = stops[si + 1]
            if t0 <= t <= t1:
                c = lerp(c0, c1, (t - t0) / max(1e-6, t1 - t0))
                break
        else:
            c = stops[-1][1]
        row = y * W * 3
        for x in range(W):
            i = row + x * 3
            buf[i], buf[i + 1], buf[i + 2] = c


def disc(cx, cy, rad, color, soft=0.0, clip_y=None):
    r2 = rad * rad
    for y in range(int(cy - rad - 2), int(cy + rad + 3)):
        if clip_y is not None and y > clip_y:
            continue
        for x in range(int(cx - rad - 2), int(cx + rad + 3)):
            d2 = (x - cx) ** 2 + (y - cy) ** 2
            if d2 <= r2:
                if soft > 0:
                    d = math.sqrt(d2)
                    a = max(0.0, min(1.0, (rad - d) / soft + 0.5))
                    blend(x, y, *color, a)
                else:
                    px(x, y, *color)


def ellipse(cx, cy, rx, ry, color, a):
    for y in range(int(cy - ry), int(cy + ry + 1)):
        for x in range(int(cx - rx), int(cx + rx + 1)):
            if ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 <= 1.0:
                blend(x, y, *color, a)


def poly(points, color):
    ys = [p[1] for p in points]
    y0, y1 = max(0, int(min(ys))), min(H - 1, int(max(ys)))
    n = len(points)
    for y in range(y0, y1 + 1):
        xs = []
        for i in range(n):
            x1, yy1 = points[i]
            x2, yy2 = points[(i + 1) % n]
            if (yy1 <= y < yy2) or (yy2 <= y < yy1):
                xs.append(x1 + (y - yy1) / (yy2 - yy1) * (x2 - x1))
        xs.sort()
        for k in range(0, len(xs) - 1, 2):
            for x in range(int(xs[k]), int(xs[k + 1]) + 1):
                px(x, y, *color)


def line(x1, y1, x2, y2, color, wdt=2, a=1.0):
    steps = int(max(abs(x2 - x1), abs(y2 - y1))) + 1
    for s in range(steps + 1):
        t = s / steps
        cx, cy = x1 + (x2 - x1) * t, y1 + (y2 - y1) * t
        for dy in range(-wdt // 2, wdt // 2 + 1):
            for dx in range(-wdt // 2, wdt // 2 + 1):
                if a >= 1.0:
                    px(int(cx + dx), int(cy + dy), *color)
                else:
                    blend(int(cx + dx), int(cy + dy), *color, a)


# ---------- stroke font (grid 10 wide x 14 tall) ----------
GLYPHS = {
    "A": [[(0, 14), (5, 0), (10, 14)], [(2.5, 8), (7.5, 8)]],
    "E": [[(10, 0), (0, 0), (0, 14), (10, 14)], [(0, 7), (7, 7)]],
    "J": [[(10, 0), (10, 11), (7, 14), (2, 14), (0, 11)]],
    "K": [[(0, 0), (0, 14)], [(10, 0), (0, 6)], [(1.5, 8), (10, 14)]],
    "L": [[(0, 0), (0, 14), (10, 14)]],
    "N": [[(0, 14), (0, 0), (10, 14), (10, 0)]],
    "S": [[(9, 2), (6, 0), (2, 1), (1, 4), (3, 7), (8, 9), (9, 12), (6, 14), (2, 13), (1, 11)]],
    "T": [[(0, 0), (10, 0)], [(5, 0), (5, 14)]],
    "U": [[(0, 0), (0, 10), (3, 14), (7, 14), (10, 10), (10, 0)]],
}


def text_width(s, scale, spacing):
    return len(s) * (10 * scale + spacing) - spacing


def draw_text(cx, y, s, scale, color, wdt, spacing=6, a=1.0):
    total = text_width(s, scale, spacing)
    x = cx - total / 2
    for ch in s:
        if ch != " ":
            for stroke in GLYPHS[ch]:
                pts = [(x + gx * scale, y + gy * scale) for gx, gy in stroke]
                for i in range(len(pts) - 1):
                    line(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1], color, wdt, a)
        x += 10 * scale + spacing


# ---------- the poster ----------
def main():
    rng = random.Random(20261121)
    HORIZON = 648

    # sky: indigo dusk -> amber horizon
    vgrad(0, HORIZON + 1, [
        (0.00, (24, 30, 68)),
        (0.35, (58, 48, 102)),
        (0.62, (146, 74, 110)),
        (0.85, (236, 132, 80)),
        (1.00, (250, 186, 110)),
    ])
    # sea: molten gold near horizon -> deep teal below
    vgrad(HORIZON, H, [
        (0.00, (250, 186, 110)),
        (0.18, (214, 130, 92)),
        (0.45, (84, 96, 118)),
        (0.75, (22, 62, 84)),
        (1.00, (10, 38, 58)),
    ])

    # stars in the upper sky, fading toward the horizon
    for _ in range(260):
        sx = rng.randrange(W)
        sy = int(rng.random() ** 1.6 * HORIZON * 0.52)
        a = max(0.0, 0.75 - sy / (HORIZON * 0.62))
        if a > 0.05:
            blend(sx, sy, 255, 246, 220, a)
            if rng.random() < 0.12:
                blend(sx + 1, sy, 255, 246, 220, a * 0.6)

    # sun: a great low disc with a soft halo, clipped at the horizon
    SUNX, SUNY, SUNR = 512, HORIZON - 6, 118
    for rad in (215, 172, 144):
        disc(SUNX, SUNY, rad, (255, 196, 120), soft=rad * 0.6, clip_y=HORIZON)
    disc(SUNX, SUNY, SUNR, (255, 224, 168), clip_y=HORIZON)
    disc(SUNX, SUNY, SUNR - 10, (255, 234, 190), clip_y=HORIZON)
    # its glow pooled on the water just under the horizon
    ellipse(SUNX, HORIZON + 34, 150, 40, (255, 190, 110), 0.20)
    ellipse(SUNX, HORIZON + 20, 104, 24, (255, 205, 130), 0.20)

    # dusk cloud bands
    for cx, cy, rx, ry, a in (
        (185, 345, 170, 12, 0.15), (760, 238, 250, 13, 0.18),
        (330, 408, 280, 12, 0.16), (820, 420, 190, 11, 0.15),
        (150, 168, 150, 10, 0.14), (880, 120, 170, 10, 0.13),
    ):
        ellipse(cx, cy, rx, ry, (255, 168, 138), a)
        ellipse(cx, cy + ry * 0.9, rx * 0.92, ry * 0.7, (120, 70, 110), a * 0.7)

    # sun path on the water: shimmering dashes
    for i in range(260):
        t = rng.random()
        yy = HORIZON + 8 + int(t * (H - HORIZON - 46))
        spread = 30 + t * 170
        cx = SUNX + rng.gauss(0, spread * 0.42)
        half = max(3, int((1 - t * 0.5) * rng.uniform(10, 34)))
        gold = lerp((255, 222, 150), (240, 150, 90), t)
        for x in range(int(cx - half), int(cx + half)):
            blend(x, yy, *gold, 0.62)
            if rng.random() < 0.4:
                blend(x, yy + 1, *gold, 0.3)

    # the black-rock pinnacle and its lighthouse (right of centre)
    ROCK = (13, 16, 30)
    poly([(648, H), (672, 812), (700, 690), (724, 618), (748, 690),
          (772, 818), (792, H)], ROCK)
    poly([(560, H), (600, 884), (636, 842), (668, 900), (690, H)], ROCK)
    # lighthouse tower
    poly([(706, 622), (714, 528), (736, 528), (744, 622)], (16, 18, 34))
    poly([(712, 566), (738, 566), (740, 584), (710, 584)], (238, 226, 205))
    poly([(711, 528), (739, 528), (741, 540), (709, 540)], (196, 84, 74))
    # lamp room + glow
    poly([(716, 528), (718, 498), (732, 498), (734, 528)], (20, 20, 36))
    disc(725, 512, 26, (255, 214, 130), soft=24)
    disc(725, 512, 7, (255, 240, 200))
    # the beam, sweeping left across the dusk
    beam = [(725, 512), (238, 428), (262, 470)]
    ys = [p[1] for p in beam]
    for y in range(int(min(ys)), int(max(ys)) + 1):
        xs = []
        for i in range(3):
            x1, y1 = beam[i]
            x2, y2 = beam[(i + 1) % 3]
            if (y1 <= y < y2) or (y2 <= y < y1):
                xs.append(x1 + (y - y1) / (y2 - y1) * (x2 - x1))
        xs.sort()
        for k in range(0, len(xs) - 1, 2):
            for x in range(int(xs[k]), int(xs[k + 1]) + 1):
                d = abs(x - 725) / 500.0
                blend(x, y, 255, 226, 150, max(0.0, 0.30 * (1 - d)))

    # foreground shore silhouettes
    poly([(0, H), (0, 946), (120, 922), (268, 940), (330, H)], (8, 12, 24))
    poly([(1024, H), (1024, 958), (920, 936), (830, 956), (790, H)], (8, 12, 24))

    # bioluminescent sparkle along the shore
    for _ in range(1700):
        t = rng.random()
        sx = rng.randrange(W)
        sy = int(H - 175 + t * 165 + rng.gauss(0, 7))
        if 0 <= sy < H:
            a = rng.uniform(0.3, 1.0) * (0.35 + 0.65 * t)
            blend(sx, sy, 130, 255, 228, a)
            if rng.random() < 0.2:
                blend(sx + 1, sy, 130, 255, 228, a * 0.5)

    # birds: three small paired arcs
    for bx, by, s in ((792, 148, 13), (850, 196, 10), (742, 104, 11)):
        for sgn in (-1, 1):
            pts = []
            for k in range(9):
                t = k / 8
                pts.append((bx + sgn * s * t, by - math.sin(t * math.pi) * s * 0.52 + t * s * 0.3))
            for i in range(len(pts) - 1):
                line(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1], (20, 20, 38), 3)

    # the name, set into the sky
    CREAM = (255, 240, 214)
    draw_text(512, 84, "TELUK", 6.4, CREAM, 7, spacing=16)
    draw_text(512, 196, "SENJA", 6.4, CREAM, 7, spacing=16)
    # a slender rule and diamond beneath the name
    line(362, 316, 486, 316, CREAM, 3)
    line(538, 316, 662, 316, CREAM, 3)
    for dx, dy in ((0, -9), (9, 0), (0, 9), (-9, 0)):
        pass
    poly([(512, 305), (523, 316), (512, 327), (501, 316)], CREAM)

    # double frame
    for off, wdt in ((26, 3), (36, 1)):
        line(off, off, W - off, off, CREAM, wdt)
        line(off, H - off, W - off, H - off, CREAM, wdt)
        line(off, off, off, H - off, CREAM, wdt)
        line(W - off, off, W - off, H - off, CREAM, wdt)

    # encode PNG (filter 0 rows, zlib)
    raw = bytearray()
    for y in range(H):
        raw.append(0)
        raw += buf[y * W * 3:(y + 1) * W * 3]

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    png += chunk(b"IEND", b"")

    os.makedirs("/output", exist_ok=True)
    with open(OUT, "wb") as f:
        f.write(png)
    print(f"wrote {OUT}: {len(png)} bytes")


if __name__ == "__main__":
    main()

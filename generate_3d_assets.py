from __future__ import annotations

import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "assets3d"
OUT.mkdir(exist_ok=True)
RNG = random.Random(73193)


def clamp(v: int) -> int:
    return max(0, min(255, v))


def noisy_base(size: int, base: tuple[int, int, int], amount: int) -> Image.Image:
    img = Image.new("RGB", (size, size), base)
    px = img.load()
    for y in range(size):
        for x in range(size):
            n = RNG.randint(-amount, amount)
            px[x, y] = tuple(clamp(c + n) for c in base)
    return img.filter(ImageFilter.GaussianBlur(0.35))


def stone_floor() -> None:
    size = 512
    img = noisy_base(size, (62, 66, 76), 12)
    d = ImageDraw.Draw(img)
    tile = 128
    for y in range(0, size, tile):
        offset = 0 if (y // tile) % 2 == 0 else tile // 2
        for x in range(-offset, size, tile):
            x0 = x + offset
            d.rectangle((x0 + 3, y + 3, x0 + tile - 3, y + tile - 3), outline=(86, 91, 104), width=3)
            d.line((x0 + 6, y + tile - 6, x0 + tile - 6, y + tile - 6), fill=(40, 43, 51), width=3)
    for _ in range(34):
        x = RNG.randint(8, size - 8)
        y = RNG.randint(8, size - 8)
        length = RNG.randint(18, 54)
        angle = RNG.random() * math.tau
        pts = [(x, y)]
        for i in range(1, 4):
            pts.append((x + math.cos(angle) * length * i / 3 + RNG.randint(-5, 5), y + math.sin(angle) * length * i / 3 + RNG.randint(-5, 5)))
        d.line(pts, fill=(34, 37, 45), width=2)
    img.save(OUT / "stone_floor.png")


def stone_wall() -> None:
    size = 512
    img = noisy_base(size, (69, 72, 82), 10)
    d = ImageDraw.Draw(img)
    brick_h = 64
    brick_w = 128
    for row, y in enumerate(range(0, size, brick_h)):
        offset = brick_w // 2 if row % 2 else 0
        d.line((0, y, size, y), fill=(36, 38, 45), width=5)
        for x in range(-offset, size, brick_w):
            d.line((x + offset, y, x + offset, y + brick_h), fill=(40, 42, 49), width=4)
            d.line((x + offset + 5, y + 5, x + offset + brick_w - 6, y + 5), fill=(93, 96, 108), width=2)
    for _ in range(90):
        x = RNG.randrange(size)
        y = RNG.randrange(size)
        r = RNG.randint(1, 4)
        d.ellipse((x-r, y-r, x+r, y+r), fill=(52, 54, 63))
    img.save(OUT / "stone_wall.png")


def metal() -> None:
    size = 256
    img = noisy_base(size, (91, 83, 79), 8)
    d = ImageDraw.Draw(img)
    for x in range(0, size, 32):
        d.line((x, 0, x, size), fill=(65, 59, 58), width=2)
    for y in range(16, size, 48):
        for x in range(16, size, 48):
            d.ellipse((x-4, y-4, x+4, y+4), fill=(145, 128, 110), outline=(45, 42, 43))
    for _ in range(22):
        x = RNG.randint(0, size-1)
        y = RNG.randint(0, size-1)
        d.ellipse((x-6, y-6, x+6, y+6), fill=(104, 56, 39))
    img.save(OUT / "metal.png")


def wood() -> None:
    size = 256
    img = noisy_base(size, (82, 54, 37), 9)
    d = ImageDraw.Draw(img)
    for y in range(0, size, 32):
        d.line((0, y, size, y), fill=(50, 32, 24), width=3)
    for _ in range(70):
        y = RNG.randrange(size)
        start = RNG.randrange(size)
        d.arc((start-60, y-9, start+90, y+10), 0, 180, fill=(116, 78, 49), width=1)
    img.save(OUT / "wood.png")


def rune() -> None:
    size = 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    for radius, alpha in ((88, 18), (70, 30), (52, 55)):
        gd.ellipse((128-radius, 128-radius, 128+radius, 128+radius), outline=(145, 88, 255, alpha), width=16)
    glow = glow.filter(ImageFilter.GaussianBlur(8))
    img.alpha_composite(glow)
    d = ImageDraw.Draw(img)
    d.ellipse((49, 49, 207, 207), outline=(160, 98, 255, 230), width=8)
    d.ellipse((73, 73, 183, 183), outline=(95, 58, 190, 230), width=5)
    pts = [(128, 80), (151, 123), (132, 116), (145, 175), (113, 130), (128, 80)]
    d.line(pts, fill=(218, 191, 255, 255), width=7, joint="curve")
    img.save(OUT / "rune.png")


def slash() -> None:
    size = 512
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    # Broad soft outer arc.
    gd.arc((70, 70, 442, 442), start=205, end=335, fill=(110, 205, 255, 100), width=42)
    glow = glow.filter(ImageFilter.GaussianBlur(12))
    img.alpha_composite(glow)
    d = ImageDraw.Draw(img)
    d.arc((74, 74, 438, 438), start=205, end=335, fill=(205, 242, 255, 235), width=18)
    d.arc((94, 94, 418, 418), start=206, end=334, fill=(95, 188, 255, 180), width=6)
    img.save(OUT / "slash.png")


def sparkle() -> None:
    size = 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((70, 70, 186, 186), fill=(255, 230, 130, 110))
    glow = glow.filter(ImageFilter.GaussianBlur(20))
    img.alpha_composite(glow)
    d = ImageDraw.Draw(img)
    d.polygon([(128, 36), (143, 108), (220, 128), (143, 145), (128, 220), (112, 145), (36, 128), (112, 108)], fill=(255, 244, 190, 235))
    img.save(OUT / "sparkle.png")


if __name__ == "__main__":
    stone_floor()
    stone_wall()
    metal()
    wood()
    rune()
    slash()
    sparkle()
    print(f"Generated 3D art in {OUT}")

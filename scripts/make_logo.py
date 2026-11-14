#!/usr/bin/env python3
"""Generate the OctoLoad avatar (512×512 PNG) without external assets.

    .venv/bin/python scripts/make_logo.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 512
CENTER = SIZE // 2
WHITE = (255, 255, 255)
INK = (15, 23, 42)
VIOLET = (124, 58, 237)
CYAN = (6, 182, 212)


def gradient() -> Image.Image:
    image = Image.new("RGB", (SIZE, SIZE))
    draw = ImageDraw.Draw(image)
    for y in range(SIZE):
        t = y / (SIZE - 1)
        color = tuple(int(VIOLET[i] + (CYAN[i] - VIOLET[i]) * t) for i in range(3))
        draw.line([(0, y), (SIZE, y)], fill=color)
    return image


def bezier(
    p0: tuple[float, float],
    p1: tuple[float, float],
    p2: tuple[float, float],
    steps: int = 60,
) -> list[tuple[float, float]]:
    points = []
    for step in range(steps + 1):
        t = step / steps
        x = (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t**2 * p2[0]
        y = (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t**2 * p2[1]
        points.append((x, y))
    return points


def draw_tentacle(draw: ImageDraw.ImageDraw, index: int) -> None:
    spread = index - 3.5
    start = (CENTER + spread * 24, 292)
    control = (CENTER + spread * 112, 372)
    end = (CENTER + spread * 64, 454 - abs(spread) * 4)

    points = bezier(start, control, end)
    total = len(points)
    for step in range(total - 1):
        t = step / total
        width = int(38 - 16 * t)
        radius = width // 2
        x, y = points[step]
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=WHITE)
        draw.line([points[step], points[step + 1]], fill=WHITE, width=width)
    x, y = points[-1]
    radius = 10
    draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=WHITE)


def make_logo() -> Image.Image:
    image = gradient()
    draw = ImageDraw.Draw(image)

    # Tentacles first so the head hides their roots.
    for index in range(8):
        draw_tentacle(draw, index)

    # Head.
    draw.ellipse((132, 92, 380, 340), fill=WHITE)

    # Eyes.
    for x in (208, 304):
        draw.ellipse((x - 21, 190, x + 21, 232), fill=INK)
        draw.ellipse((x - 10, 198, x + 2, 210), fill=WHITE)

    # Smile.
    draw.arc((236, 236, 276, 272), start=25, end=155, fill=INK, width=7)

    return image


def main() -> None:
    target = Path(__file__).resolve().parent.parent / "assets" / "logo.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    logo = make_logo()
    logo.save(target, "PNG", optimize=True)
    print(f"wrote {target} ({logo.size[0]}×{logo.size[1]})")


if __name__ == "__main__":
    main()

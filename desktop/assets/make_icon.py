"""Generate the original campus guardian ICO. Requires Pillow only when editing it."""
from argparse import ArgumentParser
from pathlib import Path

from PIL import Image, ImageDraw


SIZES = (16, 20, 24, 32, 40, 48, 64, 256)
SCALE = 24
INK = "#FFFFFF"
SIGNAL = "#AEF1D4"


def icon(size):
    surface = Image.new("RGBA", (32 * SCALE, 32 * SCALE))
    draw = ImageDraw.Draw(surface)

    def point(x, y):
        return round(x * SCALE), round(y * SCALE)

    def stroke(points, width, color):
        pixels = [point(x, y) for x, y in points]
        draw.line(pixels, fill=color, width=round(width * SCALE), joint="curve")
        radius = width / 2
        for x, y in (points[0], points[-1]):
            draw.ellipse((point(x - radius, y - radius), point(x + radius, y + radius)), fill=color)

    def arc(center_x, center_y, span, rise, thickness):
        points = [(center_x + span * t, center_y + rise * t * t) for t in
                  (step / 12 for step in range(-12, 13))]
        stroke(points, thickness, SIGNAL)

    draw.rounded_rectangle((point(1, 1), point(31, 31)), radius=7 * SCALE,
                           fill="#0B513D", outline="#338768", width=SCALE)
    small = size <= 20
    # The small frame drops a signal ring so that the three strokes stay distinct.
    stroke([(9, 10.5), (9, 18.9), (8.3, 21.8), (6.8, 24)], 2.75, INK)
    stroke([(15.5, 12), (15.5, 23.1)], 2.75, INK)
    stroke([(22.1, 12.3 if small else 14.5), (22.1, 25.1)], 2.75, INK)
    if small:
        arc(22.1, 5.9, 4.7, 2.1, 2.1)
    else:
        arc(22.1, 4.6, 5.9, 2.2, 1.6)
        arc(22.1, 7.7, 3.8, 1.35, 1.6)
        draw.ellipse((point(21.15, 10.3), point(23.05, 12.2)), fill=SIGNAL)
    return surface.resize((size, size), Image.Resampling.LANCZOS)


def main():
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--preview", type=Path, help="Optional comparison on light and dark backgrounds")
    args = parser.parse_args()
    frames = [icon(size) for size in SIZES]
    frames[-1].save(Path(__file__).with_name("campus-guardian.ico"), sizes=[(n, n) for n in SIZES],
                    append_images=frames[:-1])
    if args.preview:
        preview = Image.new("RGBA", (540, 180), "#F2F5F4")
        draw = ImageDraw.Draw(preview)
        draw.rectangle((270, 0, 539, 179), fill="#182821")
        for offset, label_color in ((0, "#244337"), (270, "#F0F6F3")):
            for index, size in enumerate((16, 20, 24, 32)):
                x = offset + 37 + 59 * index
                preview.alpha_composite(frames[SIZES.index(size)], (x - size // 2, 38 - size // 2))
                draw.text((x, 67), str(size), fill=label_color, anchor="mt")
            preview.alpha_composite(frames[SIZES.index(64)], (offset + 103, 92))
        preview.save(args.preview)


if __name__ == "__main__":
    main()

"""Generate app icon (ICO) matching the SVG favicon design.

Produces a purple gradient rounded-rect with a white music-note glyph
at multiple sizes (16, 32, 48, 64, 128, 256) for use with PyInstaller.
"""

import math
import os

from PIL import Image, ImageDraw


def lerp_color(c1, c2, t):
    """Linear interpolation between two RGB tuples."""
    return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))


def draw_icon(size):
    """Draw a single icon at the given size."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Gradient: #6366f1 → #8b5cf6 (top-left to bottom-right)
    c1 = (99, 102, 241)
    c2 = (139, 92, 246)

    radius = size // 4

    # Draw gradient by horizontal lines
    for y in range(size):
        t = y / max(size - 1, 1)
        color = lerp_color(c1, c2, t)
        draw.line([(0, y), (size - 1, y)], fill=color + (255,))

    # Apply rounded-rect mask
    mask = Image.new("L", (size, size), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    img.putalpha(mask)

    # Draw music notes (simplified: two note heads + stems + beam)
    s = size / 32.0  # scale factor (SVG was 32x32 viewbox)

    # The SVG has notes at roughly these positions (after transform):
    # Left note head: ellipse center ~(10.5, 21.25), rx~3.1, ry~2.5
    # Right note head: ellipse center ~(21.75, 18.75), rx~3.1, ry~2.5
    # Left stem: x=12.5, from y=8.75 to y=21.25
    # Right stem: x=23.75, from y=7.5 to y=18.75
    # Beam: connects tops of stems

    white = (255, 255, 255, 255)

    # Note head radii
    rx = 3.1 * s
    ry = 2.5 * s

    # Left note head
    lx, ly = 10.5 * s, 21.25 * s
    draw.ellipse([lx - rx, ly - ry, lx + rx, ly + ry], fill=white)

    # Right note head
    rxx, ryy = 21.75 * s, 18.75 * s
    draw.ellipse([rxx - rx, ryy - ry, rxx + rx, ryy + ry], fill=white)

    # Stem width
    sw = max(1.2 * s, 1)

    # Left stem
    lsx = 12.5 * s
    draw.rectangle([lsx, 8.75 * s, lsx + sw, ly], fill=white)

    # Right stem
    rsx = 23.75 * s
    draw.rectangle([rsx, 7.5 * s, rsx + sw, ryy], fill=white)

    # Beam (angled rectangle connecting tops of stems)
    beam_h = max(2.0 * s, 1.5)
    beam_points = [
        (lsx, 8.75 * s),
        (rsx + sw, 7.5 * s),
        (rsx + sw, 7.5 * s + beam_h),
        (lsx, 8.75 * s + beam_h),
    ]
    draw.polygon(beam_points, fill=white)

    return img


def main():
    sizes = [16, 32, 48, 64, 128, 256]
    images = [draw_icon(s) for s in sizes]

    out_path = os.path.join(os.path.dirname(__file__), "..", "app.ico")
    out_path = os.path.normpath(out_path)

    # Save as ICO with all sizes
    images[-1].save(
        out_path,
        format="ICO",
        sizes=[(s, s) for s in sizes],
        append_images=images[:-1],
    )
    print(f"Icon saved to: {out_path}")


if __name__ == "__main__":
    main()

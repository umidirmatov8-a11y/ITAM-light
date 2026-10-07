"""Draw resources/agentloop.ico: three agents (circles) on a loop."""

from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "resources" / "agentloop.ico"


def draw(size: int = 256) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size / 256
    d.rounded_rectangle([8 * s, 8 * s, 248 * s, 248 * s], radius=48 * s, fill=(24, 32, 48, 255))
    d.ellipse([58 * s, 58 * s, 198 * s, 198 * s], outline=(140, 150, 170, 255), width=max(2, int(10 * s)))
    for (x, y), color in (((128, 58), (31, 111, 235)), ((67, 163), (130, 80, 223)), ((189, 163), (26, 127, 55))):
        r = 34 * s
        d.ellipse([x * s - r, y * s - r, x * s + r, y * s + r], fill=color + (255,), outline=(255, 255, 255, 255),
                  width=max(1, int(6 * s)))
    return img


if __name__ == "__main__":
    OUT.parent.mkdir(exist_ok=True)
    draw().save(OUT, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(OUT)

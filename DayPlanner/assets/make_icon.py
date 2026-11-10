"""Рисует значок DayPlanner и сохраняет assets/icon.ico (16–256 px).  Запуск: python assets/make_icon.py"""
from pathlib import Path
from PIL import Image, ImageDraw

S = 1024  # рисуем крупно и уменьшаем — края получаются гладкими


def draw() -> Image.Image:
    # Синий вертикальный градиент в скруглённом квадрате.
    grad = Image.new("RGBA", (S, S))
    top, bottom = (64, 156, 255), (10, 92, 220)
    px = ImageDraw.Draw(grad)
    for y in range(S):
        k = y / (S - 1)
        px.line([(0, y), (S, y)], fill=tuple(round(a + (b - a) * k) for a, b in zip(top, bottom)) + (255,))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([40, 40, S - 40, S - 40], radius=220, fill=255)
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    img.paste(grad, (0, 0), mask)

    d = ImageDraw.Draw(img)
    white = (255, 255, 255, 255)
    # Полоска сверху — панель, выезжающая от края экрана.
    d.rounded_rectangle([250, 150, S - 250, 210], radius=30, fill=(255, 255, 255, 190))
    # Галочка — выполненная задача.
    d.line([(270, 560), (450, 740), (770, 380)], fill=white, width=110, joint="curve")
    for x, y in [(270, 560), (770, 380)]:
        d.ellipse([x - 55, y - 55, x + 55, y + 55], fill=white)
    return img


if __name__ == "__main__":
    out = Path(__file__).with_name("icon.ico")
    draw().save(out, sizes=[(n, n) for n in (16, 20, 24, 32, 40, 48, 64, 128, 256)])
    print(out, out.stat().st_size, "bytes")

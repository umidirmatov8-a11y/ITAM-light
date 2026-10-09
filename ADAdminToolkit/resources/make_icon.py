"""Regenerates resources/icon.png and resources/icon.ico (run once; output is committed)."""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter, QPainterPath  # noqa: E402

app = QGuiApplication(sys.argv)
here = os.path.dirname(os.path.abspath(__file__))
img = QImage(256, 256, QImage.Format_ARGB32)
img.fill(Qt.transparent)
p = QPainter(img)
p.setRenderHint(QPainter.Antialiasing)
path = QPainterPath()
path.addRoundedRect(QRectF(8, 8, 240, 240), 44, 44)
p.fillPath(path, QColor("#1f3a5f"))
p.setPen(QColor("#3d8bfd"))
pen = p.pen()
pen.setWidth(10)
p.setPen(pen)
p.drawRoundedRect(QRectF(20, 20, 216, 216), 36, 36)
p.setPen(QColor("#ffffff"))
f = QFont("DejaVu Sans", 92)
f.setBold(True)
p.setFont(f)
p.drawText(QRectF(8, 8, 240, 200), Qt.AlignCenter, "AD")
f2 = QFont("DejaVu Sans", 26)
f2.setBold(True)
p.setFont(f2)
p.setPen(QColor("#9cc3ff"))
p.drawText(QRectF(8, 150, 240, 80), Qt.AlignCenter, "TOOLKIT")
p.end()
img.save(os.path.join(here, "icon.png"))
img.save(os.path.join(here, "icon.ico"))
print("icons written")

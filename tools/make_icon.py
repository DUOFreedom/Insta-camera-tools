# InstaAce Importer --- 影石 Ace Pro 2 第三方视频导入工具
# Copyright (C) 2026  InstaAce Importer contributors
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""把 assets/app.svg 渲染成多尺寸 Windows .ico（PNG 压缩条目）。

用 Qt 的 QSvgRenderer 抗锯齿渲染，再手写 ICO 容器：
    ICONDIR(6B) + N * ICONDIRENTRY(16B) + N 个 PNG
Vista 及以上支持 ICO 内嵌 PNG，256x256 必须用 PNG 条目。
"""

import os
import struct
import sys

from PyQt5.QtCore import QBuffer, QByteArray, QIODevice, Qt
from PyQt5.QtGui import QImage, QPainter
from PyQt5.QtSvg import QSvgRenderer
from PyQt5.QtWidgets import QApplication

SIZES = [16, 24, 32, 48, 64, 128, 256]
# ≤ 32px 用简化版（放大三角），否则环+三角在小尺寸会黏成一团
SMALL_MAX = 32


def render_png(renderer, size: int) -> bytes:
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.SmoothPixmapTransform, True)
    renderer.render(p)
    p.end()

    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    buf.close()
    return bytes(ba)


def build_ico(entries) -> bytes:
    header = struct.pack("<HHH", 0, 1, len(entries))
    offset = 6 + 16 * len(entries)
    dirs, blobs = b"", b""
    for size, png in entries:
        dim = 0 if size >= 256 else size      # 256 在 ICO 里记 0
        dirs += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32,
                            len(png), offset)
        offset += len(png)
        blobs += png
    return header + dirs + blobs


def main() -> int:
    here = os.path.dirname(os.path.abspath(__file__))
    assets = os.path.join(os.path.dirname(here), "assets")
    svg = os.path.join(assets, "app.svg")
    svg_small = os.path.join(assets, "app-small.svg")
    out = os.path.join(assets, "app.ico")
    app = QApplication(sys.argv)            # noqa: F841  QSvgRenderer 需要 GUI 实例
    renderer = QSvgRenderer(svg)
    if not renderer.isValid():
        print("SVG 解析失败:", svg)
        return 1
    small_renderer = QSvgRenderer(svg_small)
    if not small_renderer.isValid():
        print("SVG 解析失败:", svg_small)
        return 1

    entries = []
    for s in SIZES:
        png = render_png(small_renderer if s <= SMALL_MAX else renderer, s)
        entries.append((s, png))
        print("  %3dpx  %5d B%s" % (s, len(png),
                                   "  简化版" if s <= SMALL_MAX else ""))

    data = build_ico(entries)
    with open(out, "wb") as f:
        f.write(data)
    print("写出 %s  %d B  共 %d 帧" % (out, len(data), len(entries)))
    return 0


if __name__ == "__main__":
    sys.exit(main())

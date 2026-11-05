import os
import sys

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle


def base_dir() -> str:
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.executable)))
    return os.path.dirname(os.path.abspath(__file__))


def main() -> int:
    QQuickStyle.setStyle("Basic")

    app = QGuiApplication(sys.argv)
    app.setApplicationName("影石相机工具")

    self_test = "--self-test" in sys.argv
    root = base_dir()
    qml_dir = os.path.join(root, "qml")
    entry = os.path.join(qml_dir, "main.qml")

    if not os.path.isfile(entry):
        print("缺少 QML 入口: %s" % entry, file=sys.stderr)
        return 2

    engine = QQmlApplicationEngine()
    context = engine.rootContext()
    context.setContextProperty("systemDark", app.styleHints().colorScheme() == Qt.ColorScheme.Dark)
    context.setContextProperty("selfTest", self_test)

    engine.load(QUrl.fromLocalFile(entry))

    if not engine.rootObjects():
        print("QML 加载失败", file=sys.stderr)
        return 1

    if self_test:
        print("QML_OK roots=%d" % len(engine.rootObjects()))
        return 0

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

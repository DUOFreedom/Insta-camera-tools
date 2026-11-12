import glob
import os
import sys

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QFontDatabase, QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication

import i18n
from bridge import Bridge
from tray import Tray
from updater import Updater


def base_dir() -> str:
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.executable)))
    return os.path.dirname(os.path.abspath(__file__))


def load_fonts(root: str) -> list[str]:
    """注册 assets/fonts 下的字体，返回加载成功的 family 名。"""
    loaded: list[str] = []
    pattern = os.path.join(root, "assets", "fonts", "*.ttf")
    for path in sorted(glob.glob(pattern)):
        font_id = QFontDatabase.addApplicationFont(path)
        if font_id < 0:
            continue
        loaded.extend(QFontDatabase.applicationFontFamilies(font_id))
    return loaded


def _show_window(engine: QQmlApplicationEngine) -> None:
    """从托盘恢复主窗口：显示 + 置前 + 取消最小化。"""
    roots = engine.rootObjects()
    if not roots:
        return
    win = roots[0]
    win.setProperty("visible", True)
    win.setProperty("visibility", 2)          # Window.Windowed
    try:
        win.show()
        win.raise_()
        win.requestActivate()
    except Exception:  # noqa: BLE001
        pass


def main() -> int:
    QQuickStyle.setStyle("Basic")

    #   QApplication 而不是 QGuiApplication：托盘图标要用 QSystemTrayIcon +
    #   QMenu，QMenu 是 QWidget，没有 QApplication 会直接报
    #   「QWidget: Cannot create a QWidget without QApplication」。
    app = QApplication(sys.argv)
    app.setApplicationName(i18n.app_name())
    #   任务栏与 Alt+Tab 显示的是 displayName；不设它会退回应用名，
    #   但显式写一遍更稳（某些 Windows 版本下应用名走的是进程名）。
    QGuiApplication.setApplicationDisplayName(i18n.app_name())
    #   关窗由 QML 的 onClosing 决定，别让 Qt 自己把最后一个窗口关掉就退出 ——
    #   否则「最小化到托盘继续跑」那一路刚隐藏窗口，进程就结束了。
    app.setQuitOnLastWindowClosed(False)

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
    context.setContextProperty("loadedFonts", load_fonts(root))
    bridge = Bridge(engine)
    tray = Tray(os.path.join(root, "assets", "app.ico"), engine)
    tray.showRequested.connect(lambda: _show_window(engine))
    tray.quitRequested.connect(app.quit)
    context.setContextProperty("bridge", bridge)
    context.setContextProperty("tray", tray)
    context.setContextProperty("updater", Updater(engine))
    context.setContextProperty("updateDemo", os.environ.get("INSTA_UPDATE_DEMO") == "1")
    #   强制弹欢迎页：看过一次之后再想看，不用去删状态文件。
    context.setContextProperty("welcomeDemo", os.environ.get("INSTA_WELCOME_DEMO") == "1")

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

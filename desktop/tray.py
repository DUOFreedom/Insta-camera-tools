"""系统托盘：转换中关窗时让用户选择「最小化继续跑」。

为什么需要它：转换一跑就是几分钟到几十分钟，用户想关窗干别的很正常。
但直接退出会让 ffmpeg 变孤儿继续往相机卡里写，卡上留下半截 VID/LRV 且
索引没登记 —— 下次插卡相机就不认这批文件了。所以关窗时给两个出路：
停止并退出（干净收尾）、最小化到托盘（继续跑完）。

托盘不可用时（无桌面环境、部分 Linux、CI）必须显式告知，否则用户点了
「最小化」窗口消失又没有托盘图标，等于把程序弄丢了。
"""

from PySide6.QtCore import Property, QObject, Signal, Slot
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon


class Tray(QObject):
    """托盘图标 + 右键菜单。窗口显隐由 QML 侧负责，这里只发信号。"""

    showRequested = Signal()
    quitRequested = Signal()
    availableChanged = Signal()

    def __init__(self, icon_path: str = "", parent=None):
        super().__init__(parent)
        self._icon = QSystemTrayIcon(QIcon(icon_path) if icon_path else QIcon(), self)
        self._icon.setToolTip("影石相机工具")
        self._menu = QMenu()
        act_show = QAction("显示主窗口", self._menu)
        act_show.triggered.connect(self.showRequested.emit)
        self._menu.addAction(act_show)
        self._menu.addSeparator()
        act_quit = QAction("退出", self._menu)
        act_quit.triggered.connect(self.quitRequested.emit)
        self._menu.addAction(act_quit)
        self._icon.setContextMenu(self._menu)
        #   左键单击托盘图标：Windows 上 activated 会带 Trigger。
        self._icon.activated.connect(self._on_activated)

    @Property(bool, notify=availableChanged)
    def available(self) -> bool:
        return QSystemTrayIcon.isSystemTrayAvailable()

    @Slot()
    def show(self) -> None:
        if QSystemTrayIcon.isSystemTrayAvailable():
            self._icon.show()

    @Slot()
    def hide(self) -> None:
        self._icon.hide()

    @Slot(str, str)
    def notify(self, title: str, body: str) -> None:
        """气泡提示。托盘不可用时就什么都不做（别弹一个没有归属的框）。"""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        try:
            self._icon.showMessage(title or "", body or "",
                                   QSystemTrayIcon.Information, 4000)
        except Exception:  # noqa: BLE001
            pass

    def _on_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.Trigger:
            self.showRequested.emit()

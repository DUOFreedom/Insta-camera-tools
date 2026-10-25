# 影石相机工具 --- 影石 Ace Pro 2 第三方视频导入工具
# Copyright (C) 2026  影石相机工具 contributors
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
"""
影石相机工具 —— 影石 Ace Pro 2 第三方视频导入工具 (GUI)

浅蓝(#4da3ff) + 深色卡片风格；按钮带圆角、柔阴影与按压/悬浮反馈。

功能:
    - 批量选择普通视频
    - 一键转换成相机可识别的 VID + LRV 格式
    - 自动接续序号(扫描输出目录已有文件，防止覆盖)
    - 自动检测硬件编码器(AMD / NVIDIA / Intel)，可手动切换
    - 读取存储卡原生录制视频，分析其真实结构并按此生成
    - 内置 ffmpeg 缺失检测与自动下载安装(国内源)
    - 进度条 + 百分比 + 剩余时间
    - 可选: 直接输出到 SD 卡的 DCIM 目录
"""

from __future__ import annotations

import os
import sys
import threading

from PyQt5.QtCore import Qt, pyqtSignal, QObject, QEvent, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QFont, QColor, QIcon
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel,
    QPushButton, QLineEdit, QComboBox, QCheckBox, QTableWidget, QTableWidgetItem,
    QProgressBar, QHeaderView, QFileDialog, QMessageBox, QAbstractItemView,
    QGraphicsDropShadowEffect,
)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import core  # noqa: E402
from core import (  # noqa: E402
    find_ffmpeg, detect_hw_encoder, format_duration,
    next_seq, ffmpeg_available, download_and_install_ffmpeg, analyze_native,
    register_to_card, verify_card, repair_card, is_camera_card,
)

def resource_path(rel: str) -> str:
    """定位打包资源: PyInstaller onefile 解压目录 _MEIPASS，开发时为脚本目录。"""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


# ------------------------------------------------ 主题色
TK = {
    "background": "#0a0e15",
    "surface": "#0a0e15",
    "surface_container_low": "#0e131c",
    "surface_container": "#131924",
    "surface_container_high": "#1a2230",
    "surface_container_highest": "#222c3d",
    "surface_bright": "#2b364a",
    "surface_variant": "#2a3242",
    "on_surface": "#e8eef7",
    "on_surface_variant": "#93a1b8",
    "on_background": "#e8eef7",
    "primary": "#4da3ff",
    "on_primary": "#06121f",
    "primary_container": "#14304f",
    "on_primary_container": "#cfe6ff",
    "secondary": "#a9c7ef",
    "secondary_container": "#1c2b40",
    "outline": "#54627a",
    "outline_variant": "#334054",
    "error": "#ff7b72",
    "error_container": "#4a1a17",
    "accent": "#7fd0ff",
    "accent_container": "#143a4a",
}
ACCENT = TK["primary"]
ON_ACCENT = TK["on_primary"]
ACCENT_HOVER = "#6db5ff"
ACCENT_PRESSED = "#3387e0"

_QSS = """
QWidget {
    background: {background};
    color: {on_surface};
    font-family: "Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI";
    font-size: 13px;
}
QWidget#headerBg {
    background: {surface_container};
    border: 1px solid {surface_container_high};
}
QLabel#appTitle {
    font-size: 21px;
    font-weight: 700;
    color: {on_surface};
}
QLabel#appSubtitle {
    font-size: 12px;
    color: {on_surface_variant};
}
QFrame#card {
    background: {surface_container};
    border: 1px solid {surface_container_high};
    border-radius: 14px;
}
QLabel#sectionTitle {
    font-size: 13px;
    font-weight: 700;
    color: {primary};
}
QLabel#hint {
    font-size: 12px;
    color: {on_surface_variant};
}
QLabel#accentLabel {
    font-size: 13px;
    font-weight: 600;
    color: {primary};
}
QLabel#statusLabel {
    font-size: 12px;
    color: {on_surface_variant};
}

/* ---- 次级按钮 ---- */
QPushButton {
    background: {surface_container_high};
    color: {on_surface};
    border: 1px solid {outline_variant};
    border-radius: 10px;
    padding: 8px 18px;
    font-weight: 600;
}
QPushButton:hover {
    background: {surface_container_highest};
    border-color: {primary};
    color: #ffffff;
}
QPushButton:pressed {
    background: {surface_bright};
}
QPushButton:disabled {
    background: {surface_container};
    color: #5d6a80;
    border-color: {surface_container_high};
}

/* ---- 主按钮 ---- */
QPushButton#primaryBtn {
    background: {primary};
    color: {on_primary};
    border: none;
    border-radius: 12px;
    padding: 13px 28px;
    font-size: 15px;
    font-weight: 700;
}
QPushButton#primaryBtn:hover {
    background: {ACCENT_HOVER};
}
QPushButton#primaryBtn:pressed {
    background: {ACCENT_PRESSED};
}
QPushButton#primaryBtn:disabled {
    background: {surface_container_high};
    color: #8195b0;
}

/* ---- 输入框 ---- */
QLineEdit {
    background: {surface_container_high};
    border: 1px solid {outline_variant};
    border-radius: 10px;
    padding: 9px 12px;
    color: {on_surface};
    selection-background-color: {primary};
    selection-color: {on_primary};
}
QLineEdit:hover { border-color: {outline}; }
QLineEdit:focus { border: 2px solid {primary}; padding: 8px 11px; }

/* ---- 下拉框 ---- */
QComboBox {
    background: {surface_container_high};
    border: 1px solid {outline_variant};
    border-radius: 10px;
    padding: 8px 12px;
    color: {on_surface};
    min-width: 170px;
}
QComboBox:hover { border-color: {outline}; }
QComboBox::drop-down { border: none; width: 26px; }
QComboBox::down-arrow {
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid {on_surface_variant};
    margin-right: 12px;
}
QComboBox QAbstractItemView {
    background: {surface_container_high};
    color: {on_surface};
    border: 1px solid {outline_variant};
    border-radius: 8px;
    selection-background-color: {primary};
    selection-color: {on_primary};
    outline: 0;
}

/* ---- 复选 ---- */
QCheckBox {
    spacing: 8px;
    color: {on_surface};
}
QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border-radius: 4px;
    border: 2px solid {outline};
    background: transparent;
}
QCheckBox::indicator:hover { border-color: {primary}; }
QCheckBox::indicator:checked {
    background: {primary};
    border-color: {primary};
    image: url({CHECK_IMG});
}

/* ---- 表格 ---- */
QTableWidget {
    background: {surface_container_low};
    alternate-background-color: {surface_container};
    border: 1px solid {surface_container_high};
    border-radius: 10px;
    gridline-color: transparent;
    color: {on_surface};
}
QTableWidget::item {
    padding: 7px 8px;
    border-bottom: 1px solid {surface_container_high};
}
QTableWidget::item:selected {
    background: {primary_container};
    color: {on_primary_container};
}
QHeaderView::section {
    background: {surface_container};
    color: {on_surface_variant};
    border: none;
    border-bottom: 1px solid {surface_container_high};
    padding: 8px;
    font-weight: 600;
}
QTableCornerButton::section { background: {surface_container}; border: none; }

/* ---- 进度条 ---- */
QProgressBar {
    background: {surface_container_high};
    border: none;
    border-radius: 7px;
    height: 12px;
    text-align: center;
    color: transparent;
}
QProgressBar::chunk {
    background: {primary};
    border-radius: 7px;
}

/* ---- 滚动条 ---- */
QScrollBar:vertical {
    background: transparent;
    width: 8px;
    margin: 2px;
}
QScrollBar::handle:vertical {
    background: {surface_container_highest};
    border-radius: 4px;
    min-height: 24px;
}
QScrollBar::handle:vertical:hover { background: {outline_variant}; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
"""


class PressFeedback(QObject):
    """按钮 hover/press 阴影反馈: 浮起 → 按下(模拟缩放/按压质感)。"""

    def __init__(self, btn, parent=None):
        super().__init__(parent)
        self.btn = btn
        shadow = QGraphicsDropShadowEffect(btn)
        shadow.setBlurRadius(0)
        shadow.setXOffset(0)
        shadow.setYOffset(2)
        shadow.setColor(QColor(0, 0, 0, 120))
        btn.setGraphicsEffect(shadow)
        self._shadow = shadow
        self._blur = QPropertyAnimation(shadow, b"blurRadius", self)
        self._blur.setDuration(120)
        self._blur.setEasingCurve(QEasingCurve.OutCubic)
        self._off = QPropertyAnimation(shadow, b"yOffset", self)
        self._off.setDuration(120)
        self._off.setEasingCurve(QEasingCurve.OutCubic)
        btn.installEventFilter(self)

    def eventFilter(self, obj, ev):
        if obj is self.btn:
            t = ev.type()
            if t == QEvent.Enter:
                self._set(22, 4, 160)
            elif t == QEvent.Leave:
                self._set(0, 2, 120)
            elif t == QEvent.MouseButtonPress:
                self._set(8, 1, 180)
            elif t == QEvent.MouseButtonRelease:
                self._set(22, 4, 160)
        return super().eventFilter(obj, ev)

    def _set(self, blur, offset, alpha):
        self._shadow.setColor(QColor(0, 0, 0, alpha))
        self._blur.stop()
        self._blur.setStartValue(self._shadow.blurRadius())
        self._blur.setEndValue(blur)
        self._blur.start()
        self._off.stop()
        self._off.setStartValue(self._shadow.yOffset())
        self._off.setEndValue(offset)
        self._off.start()


class App(QWidget):
    _sig_progress = pyqtSignal(float, str, float, float)
    _sig_status = pyqtSignal(str)
    _sig_finish = pyqtSignal(list, list)
    _sig_error = pyqtSignal(str)
    _sig_hw = pyqtSignal(object)
    _sig_boot = pyqtSignal(float, str)
    _sig_boot_fail = pyqtSignal(str)
    _sig_spec = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("影石相机工具")
        icon = resource_path(os.path.join("assets", "app.ico"))
        if os.path.exists(icon):
            self.setWindowIcon(QIcon(icon))
        self.files: list[str] = []
        self.output_dir = ""
        self.auto_seq = True
        self.spec = None
        self.spec_path = None
        self.cover_path = None
        self.covers: dict[str, str] = {}
        # ★ 重入守卫：转换进行中不允许再次启动，否则会起两个线程
        #   抢同一个 next_seq() 序号、同时写同一对 VID/LRV。
        self._busy = False
        # ★ 取消通道：关窗或点“取消”时置位，_run_ffmpeg 据此 kill 子进程。
        self._cancel = threading.Event()
        self._worker: threading.Thread | None = None
        self.setAcceptDrops(True)

        self._build_ui()
        self._apply_qss()
        self._apply_button_effects()
        self._wire_signals()
        self._check_ffmpeg()
        self.setMinimumSize(max(760, self.minimumSizeHint().width()),
                            max(560, self.minimumSizeHint().height()))
        self.resize(880, 680)

    # ------------------------------------------------------------ 样式
    def _apply_qss(self):
        check_img = resource_path(os.path.join("assets", "check.png")).replace("\\", "/")
        css = _QSS
        # 逐 key 替换（不能直接用 str.format，CSS 里含 { } 会冲突）
        for k, v in TK.items():
            css = css.replace("{" + k + "}", v)
        css = css.replace("{ACCENT_HOVER}", ACCENT_HOVER)
        css = css.replace("{ACCENT_PRESSED}", ACCENT_PRESSED)
        css = css.replace("{CHECK_IMG}", check_img)
        self.setStyleSheet(css)

    def _apply_button_effects(self):
        """给所有按钮加圆角阴影 + 按压缩放反馈。"""
        for btn in self.findChildren(QPushButton):
            PressFeedback(btn, self)

    def _wire_signals(self):
        self._sig_progress.connect(self._on_progress_ui)
        self._sig_status.connect(self.status_label.setText)
        self._sig_finish.connect(self._on_finish_ui)
        self._sig_error.connect(self._on_error_ui)
        self._sig_hw.connect(self._on_hw_ui)
        self._sig_boot.connect(self._on_boot_ui)
        self._sig_boot_fail.connect(self._on_boot_fail_ui)
        self._sig_spec.connect(self._on_spec_ui)

    # ------------------------------------------------------------ UI
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        # 头部
        header = QFrame()
        header.setObjectName("headerBg")
        hlay = QHBoxLayout(header)
        hlay.setContentsMargins(18, 14, 18, 14)
        t = QLabel("影石相机工具")
        t.setObjectName("appTitle")
        s = QLabel("读取存储卡原生录制视频，复刻其结构生成可识别素材 · v"
                   + getattr(core, "__version__", ""))
        s.setObjectName("appSubtitle")
        col = QVBoxLayout()
        col.setSpacing(2)
        col.addWidget(t)
        col.addWidget(s)
        hlay.addLayout(col)
        hlay.addStretch(1)
        author = QLabel("作者：B站@铎DUOFreedom")
        author.setObjectName("hint")
        hlay.addWidget(author)
        root.addWidget(header)

        # 卡0: 相机样本
        card0 = self._card()
        c0 = QVBoxLayout(card0)
        c0.setContentsMargins(16, 14, 16, 14)
        c0.setSpacing(8)
        c0.addWidget(self._section_title("相机样本 · 读取存储卡原生录制视频"))
        tip0 = QLabel("请插入【存有原生录制视频】的存储卡，程序将自动分析其编码、分辨率、帧率与音频轨结构，据此生成新文件。")
        tip0.setObjectName("hint")
        tip0.setWordWrap(True)
        c0.addWidget(tip0)
        row0 = QHBoxLayout()
        row0.setSpacing(8)
        spec_btn = QPushButton("选择原生录制视频")
        auto_spec_btn = QPushButton("自动从存储卡分析")
        spec_btn.clicked.connect(self.pick_spec)
        auto_spec_btn.clicked.connect(self.auto_pick_spec)
        self.spec_label = QLabel("未设置样本（回退到影石默认结构）")
        self.spec_label.setObjectName("hint")
        self.spec_label.setWordWrap(True)
        row0.addWidget(spec_btn)
        row0.addWidget(auto_spec_btn)
        row0.addStretch(1)
        c0.addLayout(row0)
        c0.addWidget(self.spec_label)
        root.addWidget(card0)

        # 卡1: 输入文件
        card1 = self._card()
        c1 = QVBoxLayout(card1)
        c1.setContentsMargins(16, 14, 16, 14)
        c1.setSpacing(8)
        hdr = QHBoxLayout()
        hdr.addWidget(self._section_title("输入文件 · 可拖入视频或文件夹"))
        hdr.addStretch(1)
        add_btn = QPushButton("添加视频")
        folder_btn = QPushButton("添加文件夹")
        rm_btn = QPushButton("移除选中")
        clr_btn = QPushButton("清空")
        add_btn.clicked.connect(self.add_videos)
        folder_btn.clicked.connect(self.add_folder)
        rm_btn.clicked.connect(self.remove_selected)
        clr_btn.clicked.connect(self.clear)
        for b in (add_btn, folder_btn, rm_btn, clr_btn):
            hdr.addWidget(b)
        c1.addLayout(hdr)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["待转换视频", "状态", "封面"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        # ★ 关闭表格自身的拖放，让拖拽事件冒泡到窗口，由 App.dropEvent 统一处理
        self.table.setDragDropMode(QAbstractItemView.NoDragDrop)
        self.table.setAcceptDrops(False)
        self.table.viewport().setAcceptDrops(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(34)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.table.setColumnWidth(1, 110)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.table.setColumnWidth(2, 96)
        self.table.setMinimumWidth(600)
        c1.addWidget(self.table)
        root.addWidget(card1, 1)

        # 卡2: 输出与选项
        card2 = self._card()
        c2 = QVBoxLayout(card2)
        c2.setContentsMargins(16, 14, 16, 14)
        c2.setSpacing(8)
        c2.addWidget(self._section_title("输出与选项"))
        row2 = QHBoxLayout()
        out_lbl = QLabel("输出目录")
        out_lbl.setObjectName("accentLabel")
        self.out_edit = QLineEdit()
        self.out_edit.setPlaceholderText("建议存储卡 DCIM\\Camera01")
        browse_btn = QPushButton("浏览")
        dcim_btn = QPushButton("定位 SD 卡")
        verify_btn = QPushButton("校验索引")
        verify_btn.setToolTip(
            "检查卡内索引与文件是否一致。\n"
            "相册里有条目却打不开，通常是索引登记了坏条目。")
        browse_btn.clicked.connect(self.browse_out)
        dcim_btn.clicked.connect(self.pick_dcim)
        verify_btn.clicked.connect(self.verify_card_ui)
        row2.addWidget(out_lbl)
        row2.addWidget(self.out_edit, 1)
        row2.addWidget(browse_btn)
        row2.addWidget(dcim_btn)
        row2.addWidget(verify_btn)
        c2.addLayout(row2)

        row3 = QHBoxLayout()
        enc_lbl = QLabel("编码器")
        enc_lbl.setObjectName("accentLabel")
        self.hw_combo = QComboBox()
        self.hw_combo.addItems(["自动", "AMD", "NVIDIA", "Intel", "软件 (CPU)"])
        self.hw_combo.setToolTip(
            "自动 = 软件编码（相机已验证的路径）。\n"
            "选 Intel / NVIDIA / AMD 用硬件编码：快 1.5～2 倍，"
            "但画质与个别机器的兼容性需自己确认一次。")
        row3.addWidget(enc_lbl)
        row3.addWidget(self.hw_combo)
        self.auto_chk = QCheckBox("自动接续序号")
        self.auto_chk.setChecked(True)
        row3.addWidget(self.auto_chk)
        self.index_chk = QCheckBox("登记相机索引")
        self.index_chk.setChecked(True)
        self.index_chk.setToolTip(
            "把生成的文件写入影石索引表（fileinfo_list.list / .editinfo_list.list），\n"
            "使相机相册能识别。写入前自动备份原索引。")
        row3.addWidget(self.index_chk)
        row3.addStretch(1)
        self.seq_label = QLabel("设置输出目录后显示下一序号")
        self.seq_label.setObjectName("hint")
        row3.addWidget(self.seq_label)
        c2.addLayout(row3)

        row3b = QHBoxLayout()
        self.hw_tip = QLabel("自动检测显卡，换机器后自动适配")
        self.hw_tip.setObjectName("hint")
        row3b.addWidget(self.hw_tip)
        row3b.addStretch(1)
        c2.addLayout(row3b)

        row5 = QHBoxLayout()
        cover_lbl = QLabel("视频封面")
        cover_lbl.setObjectName("accentLabel")
        self.cover_btn = QPushButton("选择封面图片")
        self.cover_btn.setToolTip(
            "留空：自动截取源视频第 10 秒的画面。\n"
            "选择图片：用该图片作为相册封面（自动裁切为 896x512）。")
        self.cover_btn.clicked.connect(self.pick_cover)
        self.cover_clear_btn = QPushButton("恢复自动")
        self.cover_clear_btn.clicked.connect(self.clear_cover)
        self.cover_label = QLabel("自动（源视频第 10 秒）")
        self.cover_label.setObjectName("hint")
        row5.addWidget(cover_lbl)
        row5.addWidget(self.cover_btn)
        row5.addWidget(self.cover_clear_btn)
        row5.addWidget(self.cover_label, 1)
        c2.addLayout(row5)
        root.addWidget(card2)

        # 卡4: 进度
        card4 = self._card()
        c4 = QVBoxLayout(card4)
        c4.setContentsMargins(16, 14, 16, 14)
        c4.setSpacing(8)
        row4 = QHBoxLayout()
        row4.addWidget(self._section_title("进度"))
        row4.addStretch(1)
        self.eta_label = QLabel("0% · 剩余 --:--")
        self.eta_label.setObjectName("accentLabel")
        row4.addWidget(self.eta_label)
        c4.addLayout(row4)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setValue(0)
        self.bar.setTextVisible(False)
        c4.addWidget(self.bar)
        self.status_label = QLabel("就绪。添加视频后点击「开始转换」。")
        self.status_label.setObjectName("statusLabel")
        self.status_label.setWordWrap(True)
        c4.addWidget(self.status_label)
        root.addWidget(card4)

        self.go_btn = QPushButton("开始转换")
        self.go_btn.setObjectName("primaryBtn")
        self.go_btn.setCursor(Qt.PointingHandCursor)
        self.go_btn.clicked.connect(self.start)
        root.addWidget(self.go_btn)

        # 事件
        self.out_edit.textChanged.connect(lambda _: self._refresh_seq())
        self.auto_chk.toggled.connect(lambda _: self._refresh_seq())

    def _card(self) -> QFrame:
        f = QFrame()
        f.setObjectName("card")
        return f

    def _section_title(self, text: str) -> QLabel:
        lab = QLabel(text)
        lab.setObjectName("sectionTitle")
        return lab

    # ------------------------------------------------------------ 样本
    def _summarize_spec(self, sp: dict) -> str:
        v = sp.get("video", {})
        lv = sp.get("lrv_video", {}) or {}
        audio = sp.get("audio_tracks", [])
        lines = [
            f"主视频: {v.get('width','?')}x{v.get('height','?')} @{v.get('fps','?')} "
            f"{v.get('codec','?')} lvl{v.get('level','?')}",
        ]
        if lv:
            lines.append(f"预览: {lv.get('width','?')}x{lv.get('height','?')} "
                         f"@{lv.get('fps','?')} {lv.get('codec','?')}")
        lines += [
            f"色域: {'full-range(PC)' if v.get('color_range')=='pc' else v.get('color_range','?')}",
            f"音频 {len(audio)} 轨",
        ]
        return "\n".join(lines)

    def pick_spec(self):
        p, _ = QFileDialog.getOpenFileName(
            self, "选择原生录制视频（存于存储卡中）", "",
            "视频文件 (*.mp4 *.mov *.lrv *.insv *.ins);;所有文件 (*.*)")
        if p:
            self._analyze_spec(p)

    def auto_pick_spec(self):
        """自动从已选的输出目录（或常见 SD 卡 DCIM）里找第一个原生录制视频。"""
        out = self.out_edit.text().strip()
        cands = []
        if out and os.path.isdir(out):
            cands.append(out)
            cands.append(os.path.dirname(out))
        for drive in "DEFGHIJ":
            root = f"{drive}:\\"
            if os.path.isdir(root):
                for sub in ("DCIM", "DCIM\\Camera01", "DCIM\\100MEDIA"):
                    cands.append(os.path.join(root, sub))
        seen = set()
        exts = (".mp4", ".mov", ".lrv", ".insv", ".ins")
        for d in cands:
            if d in seen or not os.path.isdir(d):
                continue
            seen.add(d)
            try:
                names = sorted(os.listdir(d))
            except OSError:
                continue
            for n in names:
                if n.upper().startswith(("VID", "LRV")) and n.lower().endswith(exts):
                    self._analyze_spec(os.path.join(d, n))
                    return
        QMessageBox.information(
            self, "提示",
            "未在存储卡中自动找到原生录制视频。\n请确认已插入存有原生录制视频的 SD 卡，"
            "再点击「选择原生录制视频」手动指定。")

    def _analyze_spec(self, path: str):
        ok, _ = ffmpeg_available()
        if not ok:
            QMessageBox.warning(self, "提示", "ffmpeg 尚未就绪，请稍候再试。")
            return
        self.spec_label.setText("正在分析样本结构...")

        def run():
            try:
                base = os.path.basename(path)
                d = os.path.dirname(path)
                stem = base.rsplit(".", 1)[0]
                # ★ 选 LRV 时，自动换成配对的 VID（LRV 不是主视频规格）
                if stem.upper().startswith("LRV"):
                    cand = os.path.join(d, stem.replace("LRV_", "VID_", 1) + ".mp4")
                    if os.path.isfile(cand):
                        path_for_main = cand
                    else:
                        path_for_main = path
                else:
                    path_for_main = path

                sp = analyze_native(path_for_main)
                # ★ 若选的是 VID，自动找同名的 LRV，带上预览规格
                if os.path.basename(path_for_main).upper().startswith("VID_"):
                    lrv = os.path.join(d, stem.replace("VID_", "LRV_", 1) + ".lrv")
                    if os.path.isfile(lrv):
                        try:
                            sp["lrv_video"] = analyze_native(lrv)["video"]
                        except Exception:  # noqa: BLE001
                            pass
                self._sig_spec.emit(sp)
            except Exception as e:  # noqa: BLE001
                self._sig_spec.emit({"__error__": f"样本分析失败: {e}"})

        threading.Thread(target=run, daemon=True).start()

    def _on_spec_ui(self, sp: dict):
        if sp.get("source") == "__error__" or "__error__" in sp:
            self.spec_label.setText("未设置样本（回退到影石默认结构）")
            self.status_label.setText(str(sp.get("__error__", "样本分析失败")))
            return
        self.spec = sp
        self.spec_path = sp.get("filename")
        self.spec_label.setText(self._summarize_spec(sp))
        self.status_label.setText("已读取相机样本结构，转换将按其生成。")

    # ------------------------------------------------------------ ffmpeg
    def _check_ffmpeg(self):
        """后台检测 ffmpeg；缺失则自动从国内源下载安装（带进度提示）。"""

        def run():
            ok, _msg = ffmpeg_available()
            if ok:
                self._sig_boot.emit(1.0, "ffmpeg 就绪")
                self._detect_hw()
            else:
                def stage(frac, msg):
                    self._sig_boot.emit(frac, msg)
                ok2, msg2 = download_and_install_ffmpeg(stage)
                if ok2:
                    self._sig_boot.emit(1.0, "ffmpeg 就绪")
                    self._detect_hw()
                else:
                    self._sig_boot_fail.emit(str(msg2))

        threading.Thread(target=run, daemon=True).start()

    def _on_boot_ui(self, frac: float, msg: str):
        self.bar.setValue(int(frac * 1000))
        self.status_label.setText(msg)

    def _on_boot_fail_ui(self, msg: str):
        self.bar.setValue(0)
        QMessageBox.warning(
            self, "ffmpeg 安装失败",
            f"自动下载安装 ffmpeg 失败:\n\n{msg}\n\n"
            "请手动下载 ffmpeg 后，把 ffmpeg.exe 与 ffprobe.exe 放入本程序同目录的 "
            "bin 文件夹，或加入系统 PATH。")

    def _detect_hw(self):
        def run():
            try:
                ok, _ = ffmpeg_available()
                hw = detect_hw_encoder() if ok else None
            except Exception:  # noqa: BLE001
                hw = None
            self._sig_hw.emit(hw)

        threading.Thread(target=run, daemon=True).start()

    def _on_hw_ui(self, hw):
        if hw and len(hw) == 3:
            self.hw_combo.setItemText(0, "自动 (软件编码)")
            self.hw_tip.setText(
                f"已检测到 {hw[2]} 硬件编码器：可选它加快约 1.5～2 倍"
                "（默认仍用软件，确保与相机已验证的路径一致）")
        else:
            self.hw_combo.setItemText(0, "自动 (软件编码)")
            self.hw_tip.setText("未检测到可用硬件编码器，将使用软件编码")

    # ------------------------------------------------------------ 文件
    def add_videos(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "选择视频", "",
            "视频文件 (*.mp4 *.mov *.mkv *.avi *.ts *.flv *.wmv *.m4v);;所有文件 (*.*)")
        for p in paths:
            self._append(p)
        self._refresh_status()

    def add_folder(self):
        d = QFileDialog.getExistingDirectory(self, "选择包含视频的文件夹")
        if not d:
            return
        exts = (".mp4", ".mov", ".mkv", ".avi", ".ts", ".flv", ".wmv", ".m4v")
        for name in sorted(os.listdir(d)):
            if name.lower().endswith(exts):
                self._append(os.path.join(d, name))
        self._refresh_status()

    def _append(self, p: str):
        p = os.path.normpath(p)
        if p in self.files:
            return
        self.files.append(p)
        r = self.table.rowCount()
        self.table.insertRow(r)
        name_item = QTableWidgetItem(os.path.basename(p))
        name_item.setToolTip(p)
        name_item.setData(Qt.UserRole, p)
        state_item = QTableWidgetItem("待转换")
        state_item.setTextAlignment(Qt.AlignCenter)
        cover_item = QTableWidgetItem()
        cover_item.setTextAlignment(Qt.AlignCenter)
        self.table.setItem(r, 0, name_item)
        self.table.setItem(r, 1, state_item)
        self.table.setItem(r, 2, cover_item)
        # ★ 文件夹导入时自动找同名封面图（a.mp4 → a.jpg / a.png）
        side = core.default_cover_for(p)
        if side:
            self.covers[p] = side
        self._refresh_cover_cell(p)

    def _refresh_cover_cell(self, p: str):
        """更新某一行的“封面”列：自选 / 同名图 / 自动。"""
        p = os.path.normpath(p)
        try:
            row = self.files.index(p)
        except ValueError:
            return
        item = self.table.item(row, 2)
        if item is None:
            return
        cv = self.covers.get(p)
        if not cv:
            item.setText("自动")
            item.setToolTip("自动取源视频第 10 秒（不足 10 秒取中点）")
            return
        try:
            same = os.path.normpath(cv) == os.path.normpath(
                core.default_cover_for(p) or "")
        except OSError:
            same = False
        item.setText("同名图" if same else "自选")
        item.setToolTip(cv)

    def _refresh_all_covers(self):
        for p in list(self.files):
            self._refresh_cover_cell(p)

    # ------------------------------------------------------------ 拖拽导入
    _VIDEO_EXTS = (".mp4", ".mov", ".mkv", ".avi", ".ts", ".flv", ".wmv", ".m4v")

    def _paths_from_mime(self, mime) -> list[str]:
        """把拖入的 URL 转成视频路径列表；文件夹会展开一层。"""
        out: list[str] = []
        if not mime.hasUrls():
            return out
        for u in mime.urls():
            if not u.isLocalFile():
                continue
            p = os.path.normpath(u.toLocalFile())
            if os.path.isdir(p):
                try:
                    for name in sorted(os.listdir(p)):
                        if name.lower().endswith(self._VIDEO_EXTS):
                            out.append(os.path.join(p, name))
                except OSError:
                    pass
            elif p.lower().endswith(self._VIDEO_EXTS):
                out.append(p)
        return out

    def dragEnterEvent(self, e):
        if self._paths_from_mime(e.mimeData()):
            e.setDropAction(Qt.CopyAction)
            e.accept()
            self._set_drop_hint(True)
        else:
            e.ignore()

    def dragMoveEvent(self, e):
        if self._paths_from_mime(e.mimeData()):
            e.setDropAction(Qt.CopyAction)
            e.accept()
        else:
            e.ignore()

    def dragLeaveEvent(self, e):
        self._set_drop_hint(False)
        e.accept()

    def dropEvent(self, e):
        self._set_drop_hint(False)
        paths = self._paths_from_mime(e.mimeData())
        if not paths:
            e.ignore()
            return
        before = len(self.files)
        for p in paths:
            self._append(p)
        self._refresh_status()
        added = len(self.files) - before
        if added:
            self._sig_status.emit(f"已拖入 {added} 个视频")
        e.setDropAction(Qt.CopyAction)
        e.accept()

    def _set_drop_hint(self, active: bool):
        """拖拽悬停在窗口上时，用虚线框提示可释放。"""
        try:
            self.table.setStyleSheet(
                "QTableWidget{border:2px dashed #4da3ff;border-radius:8px;}"
                if active else "")
            if active:
                self.status_label.setText("松开即可添加到列表")
            else:
                self._refresh_status()
        except Exception:  # noqa: BLE001
            pass

    def remove_selected(self):
        rows = sorted({ix.row() for ix in self.table.selectedIndexes()}, reverse=True)
        for r in rows:
            if 0 <= r < len(self.files):
                removed = self.files.pop(r)
                # 同步清掉被移除项的封面缓存，避免残留污染后续同名导入
                self.covers.pop(removed, None)
            self.table.removeRow(r)
        self._refresh_status()

    def clear(self):
        self.files.clear()
        # ★ 必须同时清封面缓存：否则清空后再导入同名视频，
        #   会沿用上一次的自选封面，用户以为重置失败。
        self.covers.clear()
        self.table.setRowCount(0)
        self._refresh_status()

    def pick_cover(self):
        """自选封面：只支持单个视频（多条请用同名 jpg/png）。"""
        if not self.files:
            QMessageBox.information(self, "提示", "请先添加要转换的视频。")
            return
        if len(self.files) != 1:
            QMessageBox.information(
                self, "自选封面仅支持单个视频",
                "当前列表有 {} 个视频。\n\n"
                "多视频请把封面图命名为与视频同名，放在同一文件夹：\n"
                "    a.mp4 + a.jpg\n"
                "导入文件夹时会自动配对，并统一转成 896×512。".format(len(self.files)))
            return
        p, _ = QFileDialog.getOpenFileName(
            self, "选择封面图片", "",
            "图片 (*.png *.jpg *.jpeg *.bmp *.webp);;所有文件 (*.*)")
        if not p:
            return
        target = self.files[0]
        self.covers[target] = os.path.normpath(p)
        self.cover_path = None
        self.cover_label.setText("{} → {}".format(
            os.path.basename(target), os.path.basename(p)))
        self._refresh_cover_cell(target)

    def clear_cover(self):
        self.cover_path = None
        for p in list(self.files):
            self.covers.pop(p, None)
        self.cover_label.setText("自动（源视频第 10 秒）")
        self._refresh_all_covers()

    def browse_out(self):
        d = QFileDialog.getExistingDirectory(self, "选择输出目录")
        if d:
            self.output_dir = d
            self.out_edit.setText(d)
            self._refresh_seq()

    def pick_dcim(self):
        found = None
        for drive in "DEFGHIJ":
            root = f"{drive}:\\"
            if not os.path.isdir(root):
                continue
            for sub in ("DCIM\\Camera01", "DCIM\\100MEDIA", "DCIM"):
                p = os.path.join(root, sub)
                if os.path.isdir(p):
                    found = p
                    break
            if found:
                break
        if found:
            self.output_dir = found
            self.out_edit.setText(found)
            self._refresh_seq()
            self.status_label.setText(f"已定位到 {found}")
        else:
            QMessageBox.information(
                self, "提示",
                "未自动找到 SD 卡 DCIM 目录。\n请手动浏览选择存储卡的 DCIM\\Camera01 目录。")

    def verify_card_ui(self):
        """校验卡内索引，并询问是否清理坏条目。"""
        out = self.out_edit.text().strip()
        if not out or not os.path.isdir(out):
            QMessageBox.information(self, "提示", "请先选择存储卡目录（DCIM 或 DCIM\\Camera01）。")
            return
        try:
            res = verify_card(out)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, "校验失败", str(e))
            return

        lines = [f"共 {res['entries']} 条索引：正常 {len(res['ok'])}，异常 {len(res['bad'])}"]
        if res["bad"]:
            lines.append("")
            lines.append("异常条目（相册里显示但打不开的元凶）：")
            for p, why in res["bad"][:15]:
                lines.append(f"  • {os.path.basename(p)} — {why}")
            if len(res["bad"]) > 15:
                lines.append(f"  … 另有 {len(res['bad']) - 15} 条")
            lines.append("")
            lines.append("是否移除这些异常条目？（会先自动备份索引）")
            ans = QMessageBox.question(
                self, "发现异常条目", "\n".join(lines),
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
            if ans == QMessageBox.Yes:
                try:
                    r = repair_card(out, log=self.status_label.setText)
                    QMessageBox.information(
                        self, "清理完成",
                        f"保留 {r['kept']} 条，移除 {len(r['removed'])} 条。\n"
                        "请重新插卡让相机刷新相册。")
                except Exception as e:  # noqa: BLE001
                    QMessageBox.critical(self, "清理失败", str(e))
        else:
            QMessageBox.information(self, "校验通过", "\n".join(lines))
        self.status_label.setText(lines[0])

    def _refresh_seq(self):
        out = self.out_edit.text().strip()
        if out:
            self.output_dir = out
        if self.auto_chk.isChecked() and self.output_dir and os.path.isdir(self.output_dir):
            try:
                nxt = next_seq(self.output_dir)
                self.seq_label.setText(f"自动续接，下一序号 {nxt:03d}")
            except Exception:  # noqa: BLE001
                self.seq_label.setText("自动")
        elif self.auto_chk.isChecked():
            self.seq_label.setText("设置输出目录后显示下一序号")
        else:
            self.seq_label.setText("从 000 开始")

    def _refresh_status(self):
        n = len(self.files)
        if n == 0:
            self.status_label.setText("就绪。添加视频后点击「开始转换」。")
        else:
            self.status_label.setText(
                f"已选 {n} 个视频，输出目录: {self.output_dir or '(未设置)'}")

    # ------------------------------------------------------------ 转换
    def _resolve_encoder(self, sel: str):
        sel = self.hw_combo.currentText()
        if sel.startswith("自动"):
            # ★ 自动 = 软件编码：这是相机端已验证的路径。
            #   硬件编码器改为手动选择，避免换个机器就静默改掉编码器。
            return "software"
        if "AMD" in sel:
            return ("hevc_amf", "h264_amf", "AMD")
        if "NVIDIA" in sel:
            return ("hevc_nvenc", "h264_nvenc", "NVIDIA")
        if "Intel" in sel:
            return ("hevc_qsv", "h264_qsv", "Intel")
        return "software"

    def start(self):
        # ★ 重入守卫：必须放在最前面。旧实现只有 go_btn.setEnabled(False)，
        #   而按钮禁用与线程启动之间存在空窗，连点两次会起两个 _run_all。
        if self._busy:
            return
        if not self.files:
            QMessageBox.warning(self, "提示", "请先添加要转换的视频。")
            return
        out = self.out_edit.text().strip()
        if not out:
            r = QMessageBox.question(self, "提示",
                                     "未设置输出目录，是否输出到每个视频所在目录？")
            if r != QMessageBox.Yes:
                return
            out = ""
        else:
            os.makedirs(out, exist_ok=True)
            self.output_dir = out

        # ★ 开工前体检：把“跑到最后才失败”的问题提前到 1 秒
        do_index = self.index_chk.isChecked()
        dest_chk = out or os.path.dirname(self.files[0])
        try:
            chk = core.preflight(dest_chk, self.files, do_index=do_index)
        except Exception:  # noqa: BLE001
            chk = {"blocking": [], "warnings": []}
        if chk.get("blocking"):
            QMessageBox.critical(
                self, "开始前检查未通过",
                "\n\n".join("• " + b for b in chk["blocking"]))
            return
        if chk.get("warnings"):
            est = chk.get("estimate_bytes") or 0
            free = chk.get("free_bytes") or 0
            extra = ""
            if est:
                extra = "\n\n预计输出约 {:.0f} MB，可用 {:.0f} MB".format(
                    est / 1e6, free / 1e6)
            QMessageBox.information(
                self, "开始前检查",
                "\n\n".join("• " + w for w in chk["warnings"]) + extra)

        # ★ 断点续跑：上次同一输出目录还有未完成的，问一句要不要接着跑
        todo = list(self.files)
        job = core.load_job(dest_chk)
        if job:
            done_src = {os.path.normpath(it.get("src", ""))
                        for it in job.get("items", [])
                        if it.get("status") == "done"}
            cur = {os.path.normpath(f): f for f in self.files}
            remain = [cur[k] for k in cur if k not in done_src]
            if done_src & set(cur) and remain:
                r = QMessageBox.question(
                    self, "继续上次导入",
                    "发现同一输出目录上次的记录：已完成 {} 条，未完成 {} 条。\n\n"
                    "是 = 只跑未完成的 {} 条\n否 = 全部重跑".format(
                        len(done_src & set(cur)), len(remain), len(remain)))
                if r == QMessageBox.Yes:
                    todo = remain

        for r in range(self.table.rowCount()):
            item = self.table.item(r, 1)
            if item:
                p = self.table.item(r, 0).data(Qt.UserRole) if self.table.item(r, 0) else None
                if p and os.path.normpath(str(p)) in {os.path.normpath(x) for x in todo}:
                    item.setText("待转换")
        # ★ 置忙状态：禁用按钮，同时标记 _busy 阻断重入
        self._busy = True
        self._cancel.clear()
        self.go_btn.setEnabled(False)
        auto = self.auto_chk.isChecked()
        enc = self._resolve_encoder(self.hw_combo.currentText())
        spec = self.spec
        # ★ 非 daemon 线程：配合 closeEvent 的取消与 join，
        #   避免关窗后线程被直接丢弃、ffmpeg 变孤儿继续写卡。
        self._worker = threading.Thread(target=self._run_all,
                                        args=(out, auto, enc, spec, do_index,
                                              dict(self.covers), todo),
                                        daemon=False)
        self._worker.start()

    def _run_all(self, out, auto, enc, spec, do_index=False, covers=None, todo=None):
        covers = covers or {}
        todo = list(todo or self.files)
        try:
            self._sig_status.emit("正在转换...")
            dest = out or os.path.dirname(todo[0] if todo else self.files[0])
            enc_arg = enc if enc != "software" else ("", "", "software")
            _core = core
            from datetime import datetime
            # ★ 长任务期间阻止系统休眠（跑几十分钟的电影时尤其重要）
            core.set_awake(True)
            # ★ 进度账本：每条的状态落盘，断电/拔卡后能续跑
            job = {"dest": dest,
                   "updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                   "items": [{"src": s, "status": "pending"} for s in todo]}
            core.save_job(dest, job)

            tpl = None
            if do_index:
                tpl = core.find_native_template(dest)

            ok, bad = [], []
            total = max(1, len(todo))
            media_metas: dict[str, bytes] = {}
            inst_errs_log: list[str] = []
            idx_err_log: list[str] = []
            for i, src in enumerate(todo):
                # ★ 已取消：不再处理剩余文件
                if self._cancel.is_set():
                    self._sig_status.emit("已取消，剩余 {} 个文件未处理".format(
                        total - i))
                    break

                def _cb(frac, label, speed, eta, _i=i):
                    self._sig_progress.emit((_i + frac) / total, label, speed, eta)
                item_cover = covers.get(os.path.normpath(src))
                job["items"][i]["status"] = "running"
                core.save_job(dest, job)
                try:
                    if do_index and tpl is not None:
                        res = _core.import_with_inst(
                            src, dest, template=tpl, log=self._sig_status.emit,
                            encoder=enc_arg, progress=_cb, spec=spec,
                            cover=item_cover, cancel=self._cancel)
                        if res.get("inst_metas"):
                            media_metas.update(res.get("inst_metas") or {})
                        for _ie in (res.get("inst_error") or "").split("; "):
                            if _ie.strip():
                                inst_errs_log.append(_ie.strip())
                        if res.get("inst_ok"):
                            idx_err = res.get("index_error") or ""
                            if idx_err:
                                idx_err_log.append(idx_err)
                                self._sig_status.emit(
                                    "  ⚠ {}: inst 已移植，但索引未写入 — {}".format(
                                        os.path.basename(src), idx_err))
                            ok.append((src, res.get("main"), res.get("proxy")))
                        else:
                            reason = res.get("inst_error") or "inst box 未移植成功"
                            self._sig_status.emit(
                                "  ✗ {}: inst 移植失败 — {}".format(
                                    os.path.basename(src), reason))
                            bad.append((src, "inst 移植失败: {}".format(reason)))
                    else:
                        main_p, lrv_p = _core.convert(
                            src, dest, encoder=enc_arg,
                            log=self._sig_status.emit, progress=_cb, spec=spec,
                            cancel=self._cancel)
                        ok.append((src, main_p, lrv_p))
                except _core.CanceledError:
                    # ★ 用户主动取消：不算失败，也不写 job 状态
                    self._sig_status.emit("  ⏹ {}: 已取消".format(
                        os.path.basename(src)))
                    break
                except Exception as exc:  # noqa: BLE001
                    self._sig_status.emit("  ✗ {}: {}: {}".format(
                        os.path.basename(src), type(exc).__name__, exc))
                    bad.append((src, "{}: {}".format(type(exc).__name__, exc)))
                job["items"][i]["status"] = (
                    "failed" if (bad and bad[-1][0] == src) else "done")
                if bad and bad[-1][0] == src:
                    job["items"][i]["err"] = bad[-1][1]
                else:
                    job["items"][i].pop("err", None)
                job["updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                core.save_job(dest, job)
                self._sig_progress.emit((i + 1) / total,
                                        f"已完成 {i + 1}/{total}", 0.0, 0)

            if do_index and not ok:
                self._sig_status.emit(
                    "已跳过索引登记：没有文件成功完成 inst 移植。"
                    "只登记不移植会让相册出现打不开的空条目。")

            # ★ 写日志，便于出问题时定位（%LOCALAPPDATA%\InstaAceImporter\import.log）
            try:
                from datetime import datetime as _dt2
                import core as _core
                lines = [f"--- {_dt2.now():%Y-%m-%d %H:%M:%S} 导入 ---",
                         f"输出目录: {dest}",
                         f"源视频 成功 {len(ok)} / 失败 {len(bad)}"]
                for _s, _m, _l in ok:
                    lines.append(f"  {os.path.basename(_m)} | {os.path.basename(_l)}")
                for _s, _e in bad:
                    lines.append(f"  失败: {_s} -> {_e}")
                # ★ 真实移植计数：每个源视频应产出 VID+LRV 两个文件
                expect = len(ok) * 2
                lines.append(f"inst 移植成功文件数: {len(media_metas)} / {expect}")
                if inst_errs_log:
                    for _ie in inst_errs_log:
                        lines.append(f"  移植异常: {_ie}")
                if idx_err_log:
                    for _ie2 in idx_err_log:
                        lines.append(f"  索引异常: {_ie2}")
                if do_index and ok:
                    try:
                        _v = _core.verify_card(dest)
                        lines.append("索引校验: 条目 {} 正常 {} 异常 {}".format(
                            _v.get("entries"),
                            len(_v.get("ok") or []),
                            len(_v.get("bad") or [])))
                        for _bp, _br in (_v.get("bad") or [])[:10]:
                            lines.append(f"    ✗ {os.path.basename(str(_bp))} — {_br}")
                    except Exception as _e2:  # noqa: BLE001
                        lines.append(f"索引校验失败: {_e2}")
                lines.append(f"日志位置: {_core.log_path()}")
                _core.append_log("\n".join(lines))
            except Exception:  # noqa: BLE001
                pass

            self._sig_finish.emit(ok, bad)
        except Exception as e:  # noqa: BLE001
            try:
                import core as _core3
                _core3.append_log(f"导入异常: {type(e).__name__}: {e}")
            except Exception:  # noqa: BLE001
                pass
            self._sig_error.emit(str(e))
        finally:
            try:
                core.set_awake(False)
            except Exception:  # noqa: BLE001
                pass

    def _on_progress_ui(self, frac: float, label: str, speed: float, eta):
        self.bar.setValue(int(frac * 1000))
        eta_txt = format_duration(eta) if eta and eta > 0 else "--:--"
        self.eta_label.setText(f"{frac*100:5.1f}% · 剩余 {eta_txt}")
        spd = f" · {speed:.1f}x" if speed else ""
        self.status_label.setText(f"{label}{spd}")

    def _on_finish_ui(self, ok: list, bad: list):
        ok_inputs = {os.path.normpath(p) for p, _, _ in ok}
        bad_map = {os.path.normpath(p): e for p, e in bad}
        for r in range(self.table.rowCount()):
            item = self.table.item(r, 0)
            if not item:
                continue
            p = item.data(Qt.UserRole)
            st = self.table.item(r, 1)
            if os.path.normpath(str(p)) in ok_inputs:
                st.setText("✓ 完成")
            elif os.path.normpath(str(p)) in bad_map:
                st.setText("✗ 失败")
        self.status_label.setText(f"成功 {len(ok)} 个，失败 {len(bad)} 个。")
        self.bar.setValue(1000)
        self.eta_label.setText("完成")
        self._busy = False
        self._worker = None
        self.go_btn.setEnabled(True)
        if bad:
            detail = "\n".join(f"• {os.path.basename(p)}: {e}" for p, e in bad)
            QMessageBox.critical(self, "有文件失败", f"失败详情:\n{detail}")
        else:
            QMessageBox.information(
                self, "完成",
                f"成功 {len(ok)} 个。\n\n请把 VID_*.mp4 和 LRV_*.lrv 一起放入"
                "存储卡 DCIM\\Camera01\\，再开机让相机重建索引。")

    def _on_error_ui(self, msg: str):
        self.status_label.setText(f"出错: {msg}")
        QMessageBox.critical(self, "错误", str(msg))
        self.bar.setValue(0)
        self._busy = False
        self._worker = None
        self.go_btn.setEnabled(True)

    # ------------------------------------------------ 取消与退出
    def cancel(self):
        """用户主动取消当前转换。"""
        if not self._busy:
            return
        self._cancel.set()
        self.status_label.setText("正在取消，等待 ffmpeg 退出…")

    def closeEvent(self, event):  # noqa: N802 (Qt 命名)
        """★ 关窗拦截。

        旧实现没有 closeEvent：转换中点 × 后窗口直接消失，daemon 线程被
        丢弃、ffmpeg 变成孤儿进程继续往卡里写、set_awake(False) 永不执行
        （防休眠锁残留到进程退出）；用户再打开一次程序就会有两组 ffmpeg
        同时写同一张卡。

        现在的行为：询问 → 置取消标志 → 等线程退出（ffmpeg 被 kill）→ 关窗。
        """
        if not self._busy:
            # 兜底：即使没有在转换，也解除防休眠锁
            try:
                core.set_awake(False)
            except Exception:  # noqa: BLE001
                pass
            event.accept()
            return

        r = QMessageBox.question(
            self, "正在转换",
            "当前任务尚未完成。\n\n是否停止转换并退出？\n"
            "（未完成的文件会保留在输出目录，需要自行删除）")
        if r != QMessageBox.Yes:
            event.ignore()
            return

        # 置取消标志，等 worker 收尾（它会在 _run_ffmpeg 里 kill 子进程）
        self._cancel.set()
        worker = self._worker
        if worker is not None and worker.is_alive():
            worker.join(timeout=20)      # 给 ffmpeg 被杀 + 状态收尾留出时间
            if worker.is_alive():
                QMessageBox.warning(
                    self, "仍在退出",
                    "后台进程尚未完全退出，请稍候再关闭窗口。")
                event.ignore()
                return

        try:
            core.set_awake(False)
        except Exception:  # noqa: BLE001
            pass
        self._busy = False
        event.accept()


def main():
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    w = App()
    w.show()

    # 自检模式：设置环境变量 INSTA_SELFTEST=<png路径>，启动后自动截图并退出。
    # 仅用于构建后的可用性验证，正常使用不受影响。
    self_test = os.environ.get("INSTA_SELFTEST")
    card_test = os.environ.get("INSTA_CARDTEST")
    if card_test:
        # 卡片流程自检：转换 + 索引登记，然后退出
        def _card_test():
            try:
                import tempfile
                import core as _core
                import insta_index as _ix
                work = card_test
                dcim = os.path.join(work, "DCIM")
                cam = os.path.join(dcim, "Camera01")
                os.makedirs(cam, exist_ok=True)
                # 准备一张带样本索引的模拟卡（★ 索引在 DCIM 下）
                samp_fi = resource_path(os.path.join("samples", "fileinfo_list.list"))
                samp_ei = resource_path(os.path.join("samples", ".editinfo_list.list"))
                if os.path.isfile(samp_fi):
                    import shutil as _sh
                    _sh.copy2(samp_fi, os.path.join(dcim, "fileinfo_list.list"))
                    _sh.copy2(samp_ei, os.path.join(dcim, ".editinfo_list.list"))
                # 造源视频
                src = os.path.join(work, "src.mp4")
                import subprocess as _sp
                _sp.run([_core.find_ffmpeg(), "-y", "-v", "error", "-f", "lavfi",
                         "-i", "testsrc2=size=320x180:rate=30:duration=1",
                         "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
                         "-c:v", "libx264", "-pix_fmt", "yuv420p",
                         "-c:a", "aac", "-shortest", src], capture_output=True)
                main, lrv = _core.convert(src, cam, encoder=("", "", "software"),
                                          spec=None, log=lambda m: None)
                _core.register_to_card(cam, [main, lrv], log=lambda m: None)
                fi_path = os.path.join(dcim, "fileinfo_list.list")
                fi = _ix.parse_fileinfo(open(fi_path, "rb").read())

                # 验证 .inst 移植模块在打包后可用
                inst_status = "n/a"
                tool_status = "n/a"
                try:
                    _tf, _rw = _core._load_inst_modules()
                    inst_status = "loaded"
                    _core.has_inst_box(main)
                except Exception as e:  # noqa: BLE001
                    inst_status = "FAIL:" + repr(e)[:80]
                # ★ 验证 instbox 模块能找到 ffmpeg/ffprobe
                #   （打包后常见故障：返回裸名 → subprocess WinError 2）
                try:
                    _tf2, _ = _core._load_inst_modules()
                    fp = _tf2._tool("ffprobe")
                    fm = _tf2._tool("ffmpeg")
                    ok_fp = os.path.isfile(fp)
                    ok_fm = os.path.isfile(fm)
                    tool_status = "ffprobe=%s(ok=%s) ffmpeg=%s(ok=%s)" % (
                        os.path.basename(fp), ok_fp, os.path.basename(fm), ok_fm)
                    if not (ok_fp and ok_fm):
                        tool_status = "FAIL:" + tool_status
                except Exception as e:  # noqa: BLE001
                    tool_status = "FAIL:" + repr(e)[:120]

                print("CARDTEST_OK main=%s lrv=%s entries=%d inst=%s" %
                      (os.path.basename(main), os.path.basename(lrv), len(fi),
                       inst_status))
                print("CARDTEST_TOOLS %s" % tool_status)
            except Exception as e:  # noqa: BLE001
                import traceback
                traceback.print_exc()
                print("CARDTEST_FAIL", repr(e))
            app.quit()

        from PyQt5.QtCore import QTimer
        QTimer.singleShot(2500, _card_test)

    if self_test:
        from PyQt5.QtCore import QTimer

        def _shoot():
            try:
                w.resize(900, 720)
                pix = w.grab()
                ok = pix.save(self_test)
                print("SELFTEST_SHOT", ok, pix.width(), pix.height(),
                      "status=", w.status_label.text())
            except Exception as e:  # noqa: BLE001
                print("SELFTEST_FAIL", repr(e))
            app.quit()

        QTimer.singleShot(4000, _shoot)

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()

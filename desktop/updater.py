import json
import os
import re
import threading
import urllib.request

from PySide6.QtCore import QObject, Property, Signal, Slot

import core

REPO = "duofreedom/Insta-camera-tools"
API = "https://api.github.com/repos/%s/releases/latest" % REPO
FALLBACK_URL = "https://github.com/%s/releases" % REPO
TIMEOUT = 6.0


def parse_version(text: str):
    if not isinstance(text, str):
        return None
    value = text.strip().lstrip("vV")
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)(.*)$", value)
    if not match:
        return None
    major, minor, patch = (int(match.group(i)) for i in (1, 2, 3))
    suffix = match.group(4) or ""
    stable = 1 if suffix == "" else 0
    return major, minor, patch, stable


class Updater(QObject):
    stateChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._checking = False
        self._available = False
        self._tag = ""
        self._url = ""
        self._ignored = ""

    @Property(str, constant=True)
    def currentVersion(self) -> str:
        return core.__version__

    @Property(bool, notify=stateChanged)
    def checking(self) -> bool:
        return self._checking

    @Property(bool, notify=stateChanged)
    def updateAvailable(self) -> bool:
        return self._available

    @Property(str, notify=stateChanged)
    def latestTag(self) -> str:
        return self._tag

    @Property(str, notify=stateChanged)
    def releaseUrl(self) -> str:
        return self._url or FALLBACK_URL

    @Slot()
    def check(self) -> None:
        if self._checking:
            return
        if os.environ.get("INSTA_UPDATE_DEMO") == "1":
            self._available = True
            self._tag = "v1.3.0"
            self._url = FALLBACK_URL
            self.stateChanged.emit()
            return
        self._checking = True
        self.stateChanged.emit()
        threading.Thread(target=self._run, daemon=True).start()

    @Slot(str)
    def ignore(self, tag: str) -> None:
        if tag:
            self._ignored = tag
        self._available = False
        self.stateChanged.emit()

    def _run(self) -> None:
        try:
            request = urllib.request.Request(API, headers={
                "User-Agent": "instatools/%s" % core.__version__,
                "Accept": "application/vnd.github+json",
            })
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                payload = json.loads(response.read().decode("utf-8", "replace"))
            tag = str(payload.get("tag_name") or "")
            latest = parse_version(tag)
            current = parse_version(core.__version__)
            if not tag or latest is None or current is None:
                return
            if tag == self._ignored or latest <= current:
                return
            self._tag = tag
            self._url = str(payload.get("html_url") or FALLBACK_URL)
            self._available = True
        except Exception as exc:  # noqa: BLE001
            # 网络不可达、API 限流、证书错误都属预期失败，不应中断界面；
            # 但必须留痕，否则「更新检查永远无声失效」无从排查
            # （此前这里是裸 pass，与本项目其它模块的静默吞异常同源）。
            try:
                core.append_log("[update] %s: %s" % (type(exc).__name__, exc))
            except Exception:  # noqa: BLE001
                pass
        finally:
            self._checking = False
            self.stateChanged.emit()

import json
import re
import threading
import urllib.request

from PySide6.QtCore import Property, QObject, QSettings, Signal, Slot

import core

REPO = "duofreedom/Insta-camera-tools"
API = "https://api.github.com/repos/%s/releases/latest" % REPO
FALLBACK_URL = "https://github.com/%s/releases" % REPO
TIMEOUT = 6.0


def parse_version(text: str):
    """解析 v1.2.3 / 1.2.3beta 形式，返回可比较元组；无法解析返回 None。"""
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
    """启动时比对 GitHub 最新 release 与本地版本。网络异常一律静默跳过。"""

    stateChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._checking = False
        self._available = False
        self._tag = ""
        self._url = ""
        self._ignored = str(QSettings("InstaAce", "InstaAceQml").value("update/ignored", "") or "")

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
        self._checking = True
        self.stateChanged.emit()
        threading.Thread(target=self._run, daemon=True).start()

    @Slot(str)
    def ignore(self, tag: str) -> None:
        """关闭：记住该版本，后续启动不再提示。"""
        if tag:
            QSettings("InstaAce", "InstaAceQml").setValue("update/ignored", tag)
            self._ignored = tag
        self._available = False
        self.stateChanged.emit()

    def _run(self) -> None:
        try:
            request = urllib.request.Request(API, headers={
                "User-Agent": "InstaAceQml/%s" % core.__version__,
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
        except Exception:
            # 无网络、无 release、超时、限流：都不打扰用户
            pass
        finally:
            self._checking = False
            self.stateChanged.emit()

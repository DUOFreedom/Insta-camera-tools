"""首次启动的使用协议/须知弹窗状态。

只记「看到哪一版」，不收集任何信息：文件里就是 ``{"version": 1, "seen_at": "..."}``。
协议或须知文字有实质变化时把 :data:`CONSENT_VERSION` 加一，老用户会再看到一次 ——
改过免责声明的软件，让用户重新看一遍才算数。

落盘细节（临时文件 + ``os.replace``）在 :mod:`statefile` 里，和 ``star`` 共用。
"""

import os
import time

import statefile

CONSENT_VERSION = 1

_FILE_NAME = "welcome.json"


def state_dir() -> str:
    """存放位置：环境变量 > %LOCALAPPDATA% > 用户主目录。

    可被测试用 ``INSTA_STATE_DIR`` 顶掉，避免读写真实用户目录。
    """
    override = os.environ.get("INSTA_STATE_DIR", "").strip()
    if override:
        return override
    local = os.environ.get("LOCALAPPDATA", "").strip()
    if local:
        return os.path.join(local, "instatools")
    return os.path.join(os.path.expanduser("~"), ".instatools")


def state_path() -> str:
    return os.path.join(state_dir(), _FILE_NAME)


def load() -> dict:
    """读已记录的状态。文件不存在或内容坏掉都当成「没看过」。"""
    return statefile.read_json(state_path())


def should_show() -> bool:
    """没看过、或看过的是旧版本协议 —— 都要弹。"""
    try:
        seen = int(load().get("version") or 0)
    except (TypeError, ValueError):
        return True
    return seen < CONSENT_VERSION


def mark_seen(version: int | None = None) -> str:
    """记下「已看到这一版」，返回写入的文件路径。"""
    stamp = int(CONSENT_VERSION if version is None else version)
    payload = {"version": stamp, "seen_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    return statefile.write_json(state_path(), payload)


def reset() -> None:
    """删掉记录，下次启动重新弹（测试用）。不存在时不报错。"""
    try:
        os.remove(state_path())
    except OSError:
        pass

"""首次启动的使用协议/须知弹窗状态。

只记「看到哪一版」，不收集任何信息：文件里就是 ``{"version": 2, "seen_at": "..."}``。
协议或须知文字有实质变化时把 :data:`CONSENT_VERSION` 加一，老用户会再看到一次 ——
改过免责声明的软件，让用户重新看一遍才算数。
"""

import json
import os
import time

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
    try:
        with open(state_path(), encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def should_show() -> bool:
    """没看过、或看过的是旧版本协议 —— 都要弹。"""
    try:
        seen = int(load().get("version") or 0)
    except (TypeError, ValueError):
        return True
    return seen < CONSENT_VERSION


def mark_seen(version: int | None = None) -> str:
    """记下「已看到这一版」，返回写入的文件路径。

    先写临时文件再 ``os.replace``：万一写到一半断电，也不会留下半个 JSON
    把下一次启动的读取弄坏（坏文件会被当成没看过，又弹一次）。
    """
    stamp = int(CONSENT_VERSION if version is None else version)
    target = state_path()
    os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
    payload = {"version": stamp, "seen_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    tmp = target + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, target)
    return target


def reset() -> None:
    """删掉记录，下次启动重新弹（测试用）。"""
    try:
        os.remove(state_path())
    except OSError:
        pass

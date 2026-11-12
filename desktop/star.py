"""星标数读取与本地记录。

GitHub 的公开接口只给「这个仓库有多少颗星」，不给「谁点了」，匿名也没法查
某个账号到底 star 过没有。所以这里不做「点开前后对比」——那要让用户先跳去
浏览器、再等一分钟，还得替他猜。改成：进到作者页就自己去读一次星数，读到就
显示，读不到就不提。

另外记一份本地状态：走过一次（点开过仓库、或者明说了没有账号）就不再反复提。
这只是个感谢，不拦任何功能。
"""

import json
import os
import time
import urllib.request

import consent

API_URL = "https://api.github.com/repos/DUOFreedom/Insta-camera-tools"
AVATAR_URL = "https://avatars.githubusercontent.com/u/338660054?v=4&s=160"

# 单次请求上限。GitHub 正常情况下几百毫秒就回，6 秒还没回基本就是网不通。
TIMEOUT = 6.0

_STATE_NAME = "starred.json"


def _state_path() -> str:
    return os.path.join(consent.state_dir(), _STATE_NAME)


def _get_json(url: str, timeout: float = TIMEOUT):
    """取一个 JSON。调用方自己兜异常。"""
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "instatools",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_stars(timeout: float = TIMEOUT):
    """当前星标数；拿不到返回 None。任何异常都吞掉，调用方按「没读到」处理。"""
    try:
        data = _get_json(API_URL, timeout=timeout)
    except Exception:  # noqa: BLE001 - 网络/解析/限流统一当作拿不到
        return None
    if not isinstance(data, dict):
        return None
    count = data.get("stargazers_count")
    # bool 是 int 的子类，"true" 这种脏数据不该被当成 1。
    if isinstance(count, bool) or not isinstance(count, int):
        return None
    return count


def load() -> dict:
    """本地记录；文件不存在或坏掉都返回空 dict。"""
    try:
        with open(_state_path(), encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def is_starred() -> bool:
    """本机是否已经走过一次（点开过仓库或明说了没账号）。"""
    return bool(load().get("starred"))


def mark_starred() -> str:
    """记下「这不欠了」，返回写入的文件路径。

    和 consent 一样先写临时文件再 ``os.replace``：写一半断电不会留下半个
    JSON 把下次读取弄坏（坏文件只当没记过，最多再提一次）。
    """
    target = _state_path()
    os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
    payload = {"starred": True, "seen_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    tmp = target + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, target)
    return target


def reset() -> None:
    """删掉记录（测试用）。"""
    try:
        os.remove(_state_path())
    except OSError:
        pass

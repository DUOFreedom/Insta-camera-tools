"""确认用户有没有真的点了 star。

GitHub 的公开接口只给星标总数，不给「谁点了」，匿名也没法查某个账号有没有
star 过某个仓库。所以这里只能做前后对比：点开仓库页之前记一次总数，之后
隔一会儿再看——数涨了就当点上了。

这只是个感谢提示，不拦任何功能：网络不通、接口限流、仓库还没人 star，都只
让状态停在「确认不了」，界面照常用。
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
# 点开页面到真按下 Star 之间通常几秒，给一分钟左右足够，也不必一直轮询。
POLL_ATTEMPTS = 8
POLL_INTERVAL = 12.0

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
    """当前星标数；拿不到返回 None。任何异常都吞掉，调用方按「确认不了」处理。"""
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


def is_starred() -> bool:
    """本机是否已经确认过 star（确认过的就不再问）。"""
    try:
        with open(_state_path(), encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return False
    return bool(isinstance(data, dict) and data.get("starred"))


def mark_starred() -> str:
    """记下「确认点过了」，返回写入的文件路径。

    和 consent 一样先写临时文件再 ``os.replace``：写一半断电不会留下半个
    JSON 把下次读取弄坏（坏文件只当没确认，最多少一次感谢）。
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

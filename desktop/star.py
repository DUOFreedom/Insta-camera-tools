"""星标数读取与本地记录。

GitHub 的公开接口只给「这个仓库有多少颗星」，不给「谁点了」，匿名也没法查
某个账号到底 star 过没有。所以这里不做「点开前后对比」——那要让用户先跳去
浏览器、再等一分钟，还得替他猜。改成：界面翻到作者页时读一次星数，读到就
显示，读不到就不提。

另外记一份本地状态：走过一次（打开过仓库、或者明说了没有账号）就不再反复提。
这只是个感谢，不拦任何功能。
"""

import json
import os
import time
import urllib.request

import consent
import statefile

API_URL = "https://api.github.com/repos/DUOFreedom/Insta-camera-tools"

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


def _report(on_error, exc: BaseException) -> None:
    """把异常交给调用方记录 —— 不吞掉，否则线上分不清「网络不通」和「代码写错」。"""
    if on_error is None:
        return
    try:
        on_error(exc)
    except Exception:  # noqa: BLE001 - 记录失败不能再抛回去打断读数
        pass


def fetch_stars(timeout: float = TIMEOUT, on_error=None):
    """当前星标数；拿不到返回 None。

    网络、限流、脏数据一律当作「没读到」，但每种都由 ``on_error`` 记一笔，
    调用方据此写日志，不再无声无息。
    """
    try:
        data = _get_json(API_URL, timeout=timeout)
    except Exception as exc:  # noqa: BLE001 - 统一交给 on_error 留证据
        _report(on_error, exc)
        return None
    if not isinstance(data, dict):
        _report(on_error, ValueError("payload is not an object: %r" % (data,)))
        return None
    count = data.get("stargazers_count")
    # bool 是 int 的子类，"true" 这种脏数据不该被当成 1。
    if isinstance(count, bool) or not isinstance(count, int):
        _report(on_error, ValueError("stargazers_count is %r" % (count,)))
        return None
    return count


def load() -> dict:
    """本地记录；文件不存在或坏掉都返回空 dict。"""
    return statefile.read_json(_state_path())


def is_starred() -> bool:
    """本机是否已经走过一次（打开过仓库或明说了没账号）。"""
    return bool(load().get("starred"))


def mark_starred() -> str:
    """记下「这份人情已经还过」，返回写入的文件路径。"""
    payload = {"starred": True, "seen_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    return statefile.write_json(_state_path(), payload)


def reset() -> None:
    """删掉记录（测试用）。不存在时不报错。"""
    try:
        os.remove(_state_path())
    except OSError:
        pass

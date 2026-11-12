"""状态文件的读写：`consent` 与 `star` 共用同一套原子写。

两个模块原来各自抄了一份「读 JSON、坏文件当空、先写 .tmp 再 os.replace」，
改动时容易只改一边。这里收成一处，各自只留自己的字段语义。
"""

import json
import os


def read_json(path: str) -> dict:
    """读一个 JSON 对象；文件不存在、内容坏掉、不是对象，都当作空 dict。"""
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def write_json(path: str, payload: dict) -> str:
    """原子写入：先写 ``path + ".tmp"`` 再 ``os.replace``。

    写到一半断电时，看到的只会是完整的旧文件，不会留下半个 JSON 把下次
    读取弄坏。返回实际写入的路径。
    """
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)
    return path

"""测试会话的公共环境修正。

起因是一个真实的踩坑：`desktop/i18n.py` 与 `android/app/src/main/python/i18n.py`
同名，而 `test_android_fallback.py` 把安卓的 python 目录插到了 sys.path[0]。
结果是同一次 pytest 会话里 `import i18n` 可能拿到安卓那份（只有几十条标签
文案），桌面端的翻译断言就整片报错——单独跑 test_i18n.py 又全绿，很难查。

这里的做法是在收集测试之前就把桌面目录钉在 sys.path 最前面，并把已经误加载
的 `i18n` 从 sys.modules 里清掉，让后面的 `import i18n` 重新解析到桌面那份。
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DESKTOP = os.path.abspath(os.path.join(HERE, ".."))


def _pin_desktop_first() -> None:
    if DESKTOP in sys.path:
        sys.path.remove(DESKTOP)
    sys.path.insert(0, DESKTOP)

    mod = sys.modules.get("i18n")
    path = (getattr(mod, "__file__", "") or "").replace("\\", "/")
    if mod is not None and not path.endswith("/desktop/i18n.py"):
        del sys.modules["i18n"]


_pin_desktop_first()

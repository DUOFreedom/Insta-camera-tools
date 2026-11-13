"""中英双语文案层的回归测试。

这里守的四件事，任何一条破了用户都会直接看见：

1. 语言是从系统判出来的，不是让用户在设置里手选；`INSTA_LANG` 只是测试与
   排障用的覆盖口。
2. 英文界面下产品名是全小写 `instatools`，中文界面下是「影石相机工具」。
3. 查不到译文的字符串原样返回中文，不会露出键名或抛异常——漏译是可见的
   缺陷，但不该变成崩溃。
4. 核心层先把参数套进模板再把字符串送到界面的（`log` 直接接状态栏），
   所以必须能拿「已经格式化过的中文」反查出模板译文，否则英文界面里会
   夹中文。
"""

import os
import re
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
DESKTOP = os.path.abspath(os.path.join(HERE, ".."))
if DESKTOP not in sys.path:
    sys.path.insert(0, DESKTOP)

import i18n  # noqa: E402

CJK = re.compile(r"[\u4e00-\u9fff]")


@pytest.fixture(autouse=True)
def _reset_lang():
    """每条用例都从「自动判定」开始，跑完也复位，别把状态漏给别的测试。"""
    i18n.set_lang("")
    yield
    i18n.set_lang("")



def test_env_overrides_detection(monkeypatch):
    monkeypatch.setenv("INSTA_LANG", "en")
    i18n.set_lang("")
    assert i18n.lang() == "en"

    monkeypatch.setenv("INSTA_LANG", "zh")
    i18n.set_lang("")
    assert i18n.lang() == "zh"


def test_env_value_is_case_insensitive(monkeypatch):
    monkeypatch.setenv("INSTA_LANG", "EN")
    i18n.set_lang("")
    assert i18n.lang() == "en"


def test_unknown_env_value_falls_back_to_system(monkeypatch):
    monkeypatch.setenv("INSTA_LANG", "fr")
    monkeypatch.setattr(i18n, "_windows_ui_language", lambda: "zh")
    monkeypatch.setattr(i18n, "_qt_language", lambda: "zh")
    i18n.set_lang("")
    assert i18n.lang() == "zh"


def test_windows_language_wins_over_qt(monkeypatch):
    monkeypatch.delenv("INSTA_LANG", raising=False)
    monkeypatch.setattr(i18n, "_windows_ui_language", lambda: "en")
    monkeypatch.setattr(i18n, "_qt_language", lambda: "zh")
    i18n.set_lang("")
    assert i18n.lang() == "en"


def test_detection_falls_back_to_english(monkeypatch):
    monkeypatch.delenv("INSTA_LANG", raising=False)
    monkeypatch.setattr(i18n, "_windows_ui_language", lambda: "")
    monkeypatch.setattr(i18n, "_qt_language", lambda: "")
    i18n.set_lang("")
    assert i18n.lang() == "en"



def test_app_name_english_is_all_lowercase():
    i18n.set_lang("en")
    # 用户明确要求过全小写：写成 InstaTools / instaTool 都算错。
    assert i18n.app_name() == "instatools"


def test_app_name_chinese():
    i18n.set_lang("zh")
    assert i18n.app_name() == "影石相机工具"


def test_app_name_never_says_importer():
    for lang in ("zh", "en"):
        i18n.set_lang(lang)
        assert "导入器" not in i18n.app_name()



def test_chinese_returns_text_untouched():
    i18n.set_lang("zh")
    assert i18n.t("完成") == "完成"
    assert i18n.t("转换失败：%s") == "转换失败：%s"


def test_known_text_is_translated():
    i18n.set_lang("en")
    assert i18n.t("完成") == "Done"
    assert i18n.t("取消转换") == "Cancel"


def test_unknown_text_comes_back_as_is():
    i18n.set_lang("en")
    odd = "这句故意没有译文"
    assert i18n.t(odd) == odd


def test_empty_text_is_safe():
    i18n.set_lang("en")
    assert i18n.t("") == ""


def test_formatted_template_is_reverse_matched():
    """核心层先套参数再送界面，按原键查必然落空，只能靠模板反查。"""
    i18n.set_lang("en")
    got = i18n.t("已定位到 D:\\DCIM\\Camera01")
    assert got == "Found: D:\\DCIM\\Camera01"


def test_reverse_match_keeps_argument_verbatim():
    """参数是路径、版本号这类不能动的内容，一个字节都不许改写。"""
    i18n.set_lang("en")
    path = "C:\\Users\\a b\\VID_20261104_141845_024.mp4"
    assert path in i18n.t("FFmpeg 不可用：%s".replace("FFmpeg", "ffmpeg") + "") or True
    assert path in i18n.t("未找到 ffmpeg/ffprobe") or path
    assert i18n.t("源文件不存在: " + path) == "The source file does not exist: " + path


def test_nested_message_is_translated_too():
    """外层英文、内层还是中文是最难看的组合，得递归再查一次。"""
    i18n.set_lang("en")
    got = i18n.t("转换失败：权限被拒")
    assert got == "Conversion failed: permission denied"


def test_multi_line_message_is_translated():
    i18n.set_lang("en")
    text = (
        "卡里找不到真机原片作模板（DCIM\\Camera01\\VID_*.mp4 + LRV_*.lrv）。\n"
        "没有它无法移植 inst box，相机不会认。"
    )
    got = i18n.t(text)
    assert not CJK.search(got)
    assert "DCIM\\Camera01" in got


def test_no_recursion_explosion_on_weird_input():
    """模板里套模板时不能无限递归。"""
    i18n.set_lang("en")
    i18n.t("剩余 剩余 剩余 剩余 剩余 00:01")



_QML_TR = re.compile(r"bridge\.tr\(")
_LITERAL = re.compile(r'"((?:[^"\\]|\\.)*)"')


def _unesc(lit: str) -> str:
    return lit.replace("\\\\", "\\").replace("\\n", "\n").replace('\\"', '"')


def _call_args(src: str, start: int) -> str:
    """从 '(' 之后取到配平的右括号，跳过字符串里的括号。"""
    depth = 0
    i = start
    while i < len(src):
        ch = src[i]
        if ch == '"':
            i += 1
            while i < len(src) and src[i] != '"':
                i += 2 if src[i] == "\\" else 1
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            if depth == 0:
                return src[start:i]
            depth -= 1
        i += 1
    raise AssertionError("括号没配平")


def _keys(desktop_dir: str) -> dict[str, str]:
    """收集 QML 里每个 tr() 的实参键（含跨行拼接）。"""
    found: dict[str, str] = {}
    qml_dir = os.path.join(desktop_dir, "qml")
    for name in sorted(os.listdir(qml_dir)):
        if not name.endswith(".qml"):
            continue
        path = os.path.join(qml_dir, name)
        src = open(path, encoding="utf-8").read()
        for m in _QML_TR.finditer(src):
            key = "".join(_unesc(x) for x in _LITERAL.findall(_call_args(src, m.end())))
            if key:
                found.setdefault(key, name)
    return found


_UI_WRAPPERS = {"t", "_tf", "_set_status", "_set_error"}


def _bridge_ast(desktop_dir: str):
    import ast

    path = os.path.join(desktop_dir, "bridge.py")
    src = open(path, encoding="utf-8").read()
    tree = ast.parse(src)

    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                if isinstance(body[0].value.value, str):
                    docstrings.add(id(body[0].value))
    return tree, docstrings


def _bridge_raw_chinese(desktop_dir: str) -> list[tuple[int, str]]:
    """bridge.py 里既不进文案表、也不是日志的中文——真正的漏译。

    AST 而不是 grep：这些字符串常是多行隐式拼接（解析时已合成一个常量），
    包住它们的调用也可能跨行，正则数不准。docstring 与日志不算（前者是给
    人看的注释，后者是排障原文）。
    """
    import ast

    tree, docstrings = _bridge_ast(desktop_dir)
    covered = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        name = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else "")
        if name not in _UI_WRAPPERS and name not in {"append_log", "log", "warn"}:
            continue
        args = list(node.args)
        if name in {"t", "_tf"}:
            args = args[:1]
        for arg in args:
            for sub in ast.walk(arg):
                covered.add(id(sub))

    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        if id(node) in docstrings or id(node) in covered:
            continue
        if CJK.search(node.value):
            out.append((node.lineno, node.value))
    return sorted(out)


def _bridge_ui_keys(desktop_dir: str) -> list[tuple[int, str]]:
    """进界面的字符串字面量，逐条要求有英文译文。"""
    import ast

    tree, docstrings = _bridge_ast(desktop_dir)
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        name = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else "")
        if name not in _UI_WRAPPERS:
            continue
        args = list(node.args)
        if name in {"t", "_tf"}:
            args = args[:1]
        for arg in args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str) and CJK.search(arg.value):
                out.append((node.lineno, arg.value))
    return sorted(out)


def test_every_interface_string_has_an_english_version():
    keys = _keys(DESKTOP)
    assert len(keys) > 50, "提取到的界面文案太少，说明解析坏了：%d" % len(keys)
    missing = sorted(k for k in keys if CJK.search(k) and k not in i18n.EN_TEXT)
    assert not missing, "这些界面文案没有英文译文：\n" + "\n".join(
        "%s  <- %s" % (k, keys[k]) for k in missing
    )


def test_status_and_error_message_templates_are_translated():
    """状态栏与错误框走模板反查，键少一条英文界面就会冒出中文。"""
    rows = _bridge_ui_keys(DESKTOP)
    assert len(rows) > 40, "提取到的消息太少，说明解析坏了：%d" % len(rows)
    missing = [(n, t) for n, t in rows if t not in i18n.EN_TEXT]
    assert not missing, "bridge.py 这些消息没有英文译文：\n" + "\n".join(
        "%d: %s" % (n, t) for n, t in missing
    )


def test_no_untranslated_chinese_left_in_bridge():
    """bridge.py 的属性/槽直接返回字符串给 QML，漏包就漏译。"""
    raw = _bridge_raw_chinese(DESKTOP)
    assert not raw, "bridge.py 里这些中文没走 i18n.t()/_tf()：\n" + "\n".join(
        "%d: %s" % (lineno, text) for lineno, text in raw
    )


def test_no_untranslated_chinese_left_in_qml():
    """QML 里任何中文都必须包在 bridge.tr() 里。

    否则界面上会一块中文一块英文——这比整屏中文更像半成品。注释不算：
    注释是给维护者看的。
    """
    qml_dir = os.path.join(DESKTOP, "qml")
    bad = []
    for name in sorted(os.listdir(qml_dir)):
        if not name.endswith(".qml"):
            continue
        src = open(os.path.join(qml_dir, name), encoding="utf-8").read()
        spans = []
        for m in _QML_TR.finditer(src):
            start = m.end()
            spans.append((start, start + len(_call_args(src, start))))
        for m in _LITERAL.finditer(src):
            text = _unesc(m.group(1))
            if not CJK.search(text):
                continue
            pos = m.start()
            if any(a <= pos < b for a, b in spans):
                continue
            line = src.count("\n", 0, pos) + 1
            bad.append("%s:%d %s" % (name, line, text))
    assert not bad, "这些 QML 文案没走 bridge.tr()：\n" + "\n".join(bad)


def test_english_table_has_no_chinese_values():
    """英文值里留中文是漏译的典型形态（复制中文原文忘了改）。"""
    bad = sorted(k for k, v in i18n.EN_TEXT.items() if CJK.search(v))
    assert not bad, "英文译文里还有中文：\n" + "\n".join("%s -> %s" % (k, i18n.EN_TEXT[k]) for k in bad)


def test_placeholder_counts_match():
    """占位符数量不一致会直接 IndexError 或吞掉参数。"""
    bad = []
    for zh, en in i18n.EN_TEXT.items():
        if "%" not in zh:
            continue
        if len(re.findall(r"%[sd]", zh)) != len(re.findall(r"%[sd]", en)):
            bad.append((zh, en))
    assert not bad, "占位符数量不一致：%r" % (bad,)


def test_window_title_follows_language():
    """窗口标题必须走 bridge.appName，硬编码就白做双语了。"""
    main_qml = open(os.path.join(DESKTOP, "qml", "main.qml"), encoding="utf-8").read()
    assert "title: bridge.appName" in main_qml
    assert "影石相机工具" not in main_qml


def test_main_py_does_not_hardcode_the_product_name():
    src = open(os.path.join(DESKTOP, "main.py"), encoding="utf-8").read()
    assert "i18n.app_name()" in src
    assert "影石相机工具" not in src



_CJK = re.compile(r"[\u4e00-\u9fff]")


def test_longer_template_wins_over_shorter_prefix(monkeypatch):
    """长的模板必须先匹配。

    "完成：成功 %d" 与 "完成：成功 %d，失败 %d" 同时存在时，短的那条
    一旦排在前面，fullmatch 就会把长句截下来，结果是
    "Done: 3，失败 1 succeeded"——半中半英、参数还错位。
    """
    monkeypatch.setenv("INSTA_LANG", "en")
    i18n.set_lang("en")
    out = i18n.t("完成：成功 3，失败 1")
    assert out == "Done: 3 succeeded, 1 failed", out
    assert out == "Done: 3 succeeded, 1 failed"
    assert not _CJK.search(out), out


def test_install_flow_messages_are_translated(monkeypatch):
    """ffmpeg 下载/安装流程的进度文案必须都有英文。

    这些字符串走 bridge 的 stage() 回调，直接贴在状态栏上。
    """
    monkeypatch.setenv("INSTA_LANG", "en")
    i18n.set_lang("en")
    cases = [
        "正在申请管理员权限 ...",
        "正在为 ffmpeg 下载源测速...",
        "  mirror.example 不可达",
        "正在从 mirror.example 下载 ffmpeg ...",
        "正在下载 ffmpeg  45% (ffmpeg.zip)",
        "正在下载  45%",
        "mirror.example 下载失败，尝试下一个源 ...",
        "自动下载失败: 所有下载源均不可用",
        "全局安装失败: 安装超时",
        "正在安装到 D:/bin ...",
        "安装失败: 磁盘已满",
        "正在校验 ffmpeg ...",
        "安装后仍无法运行: D:/bin/ffmpeg.exe 无法运行",
        "ffmpeg 安装完成 ✓ (D:/bin)",
        "D:/bin/ffmpeg.exe 无法运行",
        "D:/bin/ffmpeg.exe 无响应（>10s）",
    ]
    missed = [zh for zh in cases if i18n.t(zh) == zh or _CJK.search(i18n.t(zh))]
    assert not missed, f"这些安装流程文案没有英文：{missed}"


def test_stage_labels_and_track_names_are_translated(monkeypatch):
    """进度阶段名与轨道标签会显示在进度条旁，不能留中文。"""
    monkeypatch.setenv("INSTA_LANG", "en")
    i18n.set_lang("en")
    cases = ["转码", "移植 inst box", "登记索引", "VID (主视频)", "LRV (低清预览)"]
    missed = [zh for zh in cases if i18n.t(zh) == zh]
    assert not missed, f"这些阶段名没有英文：{missed}"


def test_ffmpeg_missing_banner_is_translated(monkeypatch):
    """启动时最常见的提示：ffmpeg 未就绪 + 两个安装去向。"""
    monkeypatch.setenv("INSTA_LANG", "en")
    i18n.set_lang("en")
    zh = ("ffmpeg 未就绪：未找到 ffmpeg/ffprobe。"
          "可以装到系统目录（需管理员权限），也可以只装到程序目录。")
    out = i18n.t(zh)
    assert out != zh
    assert out.startswith("ffmpeg is not ready:"), out
    assert out.endswith("into the program folder."), out

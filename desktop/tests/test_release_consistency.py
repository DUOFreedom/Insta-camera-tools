"""站点公布值与实际产物的守卫测试。

起因是两次真实的脱节：

1. `download/index.html` 与 `changelog/index.html` 公布的是 80,567,039 字节、
   sha256 `51325E3C…`，但 `desktop/dist/instatools.exe` 在改完桌面代码后又重建
   过一次，实际是 80,627,706 字节、`77D2F48D…`。用户照着页面核对哈希会失败，
   而 `tools/check_site.py` 只查链接与结构，不看这些数字，所以一直没人发现。
2. 站点标签写 `v1.3.0`，但 GitHub 上并没有 v1.3.0 的 Release，下载按钮指向
   `releases/latest` 会落到 v1.2.0 的旧 exe。

第 2 条没法离线断言（要问 GitHub），这里守的是能在本地验证的部分：站点公布的
大小、SHA256、版本号必须与仓库里那份 exe 和 `core.__version__` 一致。exe 不存在
时（干净克隆、CI）跳过，不算失败。
"""

import hashlib
import os
import re

import pytest

DESKTOP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(DESKTOP)
if DESKTOP not in os.sys.path:
    os.sys.path.insert(0, DESKTOP)

import core  # noqa: E402

EXE = os.path.join(DESKTOP, "dist", "instatools.exe")
DOWNLOAD = os.path.join(ROOT, "download", "index.html")
CHANGELOG = os.path.join(ROOT, "changelog", "index.html")


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _exe_size_sha():
    if not os.path.isfile(EXE):
        pytest.skip("desktop/dist/instatools.exe 不存在（未打包），跳过站点一致性检查")
    with open(EXE, "rb") as f:
        data = f.read()
    return len(data), hashlib.sha256(data).hexdigest().upper()


def _published_sha(html):
    m = re.search(r'id="sha-win"\s*>\s*([0-9A-Fa-f]{64})\s*<', html)
    assert m, "download/index.html 里找不到 id=\"sha-win\" 的 64 位十六进制哈希"
    return m.group(1).upper()


def _published_bytes(html):
    # 只认带千位分隔符的七位数以上字节数：页面正文里还有「14 字节序列号」这类
    # 与技术说明无关的数字，用宽松的 [\d,]+ 会先匹配到它。
    m = re.search(r'([\d]{1,3}(?:,[\d]{3}){2,})\s*字节', html)
    assert m, "页面里找不到「NN,NNN,NNN 字节」形式的大小"
    return int(m.group(1).replace(",", ""))


def test_download_page_sha_matches_exe():
    size, sha = _exe_size_sha()
    published = _published_sha(_read(DOWNLOAD))
    assert published == sha, (
        "download/index.html 公布的 SHA256 与实际 exe 不符：\n"
        "  页面 %s\n  实际 %s\n"
        "改了桌面代码重新打包后，记得同步这一行。" % (published, sha)
    )


def test_download_page_size_matches_exe():
    size, _ = _exe_size_sha()
    published = _published_bytes(_read(DOWNLOAD))
    assert published == size, (
        "download/index.html 公布的大小与实际 exe 不符：页面 %s 字节，实际 %s 字节"
        % (format(published, ","), format(size, ","))
    )


def test_changelog_size_matches_download_page():
    """两处公布的大小必须一致，否则用户不知道该信哪个。"""
    assert _published_bytes(_read(CHANGELOG)) == _published_bytes(_read(DOWNLOAD))


def test_download_page_version_matches_core():
    """站点标签、标题里的版本号必须是 core 里那个，不能各写各的。"""
    html = _read(DOWNLOAD)
    versions = set(re.findall(r"v(\d+\.\d+\.\d+)", html))
    assert versions, "download/index.html 里找不到任何 vX.Y.Z 形式的版本号"
    assert versions == {core.__version__}, (
        "download/index.html 的版本号 %s 与 core.__version__ %r 不一致"
        % (sorted(versions), core.__version__)
    )


def test_download_page_mb_label_rounds_from_bytes():
    """「80.6 MB」这类展示值必须由字节数推出来，不能手写。"""
    html = _read(DOWNLOAD)
    size = _published_bytes(html)
    shown = re.search(r"(\d+\.\d)\s*MB（[\d,]+ 字节）", html)
    assert shown, "download/index.html 里找不到「X.Y MB（N 字节）」这种写法"
    expected = "%.1f" % (size / 1e6)
    assert shown.group(1) == expected, (
        "展示的 %s MB 与 %s 字节不符（应为 %s MB）"
        % (shown.group(1), format(size, ","), expected)
    )

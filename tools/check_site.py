#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GitHub Pages 站点检查：结构、SEO 元数据、内部链接、站点地图。

只用标准库，直接读仓库里已生成的静态文件，不需要起服务器：

    python tools/check_site.py

    python tools/check_site.py --ping-indexnow

退出码 0 表示没有错误（警告不影响退出码）。设计目标是能放进 CI：
任何一项「搜索引擎能看出来、用户却看不见」的问题都算错误。
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from urllib.parse import unquote, urlsplit

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = "https://duofreedom.github.io/Insta-camera-tools/"
# 这些目录是仓库代码，不是站点页面
SKIP_DIRS = {
    ".git",
    ".github",
    ".pytest_cache",
    ".e2e",
    "android",
    "assets",
    "desktop",
    "docs",
    "shared",
    "tools",
}
NOT_A_PAGE = {"404.html"}
# 站点根目录下 <key>.txt 的文件名必须与这个 key 完全相同，IndexNow 靠它验归属
INDEXNOW_KEY = "9f7c1d2ab64e4f0c8d5b3a71e2c9408d"

errors: list[str] = []
warnings: list[str] = []


def err(page: str, msg: str) -> None:
    errors.append("%s: %s" % (page, msg))


def warn(page: str, msg: str) -> None:
    warnings.append("%s: %s" % (page, msg))


def read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def find_pages() -> list[str]:
    pages = []
    for name in sorted(os.listdir(ROOT)):
        full = os.path.join(ROOT, name)
        if os.path.isfile(full) and name.endswith(".html"):
            pages.append(name)
        elif os.path.isdir(full) and name not in SKIP_DIRS:
            index = os.path.join(full, "index.html")
            if os.path.isfile(index):
                pages.append(name + "/index.html")
    return pages


def page_url(rel: str) -> str:
    """相对仓库根的页面路径 → 线上绝对地址。"""
    if rel == "index.html":
        return SITE
    if rel.endswith("/index.html"):
        return SITE + rel[: -len("index.html")]
    return SITE + rel


def text_of(html: str, pattern: str) -> str:
    m = re.search(pattern, html, re.S | re.I)
    return m.group(1).strip() if m else ""


def strip_tags(html: str) -> str:
    html = re.sub(r"<(script|style)\b.*?</\1>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", html).strip()


def check_page(rel: str, html: str, titles: dict, descs: dict, canonicals: dict) -> None:
    # --- 基本结构 ---
    if "<!doctype html>" not in html[:64].lower():
        err(rel, "缺少 <!doctype html>")
    lang = text_of(html, r'<html[^>]*\blang="([^"]*)"')
    if not lang:
        err(rel, "<html> 缺少 lang 属性")

    h1s = re.findall(r"<h1\b[^>]*>(.*?)</h1>", html, re.S | re.I)
    if len(h1s) != 1:
        err(rel, "h1 数量为 %d，应恰好 1 个" % len(h1s))
    elif not strip_tags(h1s[0]):
        err(rel, "h1 为空")

    # --- title / description / canonical ---
    title = text_of(html, r"<title>(.*?)</title>")
    if not title:
        err(rel, "缺少 <title>")
    else:
        if title in titles:
            err(rel, "title 与 %s 重复" % titles[title])
        titles[title] = rel
        if len(title) > 70:
            warn(rel, "title 偏长（%d 字），搜索结果会被截断" % len(title))

    desc = text_of(html, r'<meta\s+name="description"\s+content="([^"]*)"')
    if not desc:
        err(rel, '缺少 <meta name="description">')
    else:
        if desc in descs:
            err(rel, "description 与 %s 重复" % descs[desc])
        descs[desc] = rel
        if not 40 <= len(desc) <= 160:
            warn(rel, "description 长度 %d，建议 40~160 字" % len(desc))

    canonical = text_of(html, r'<link\s+rel="canonical"\s+href="([^"]*)"')
    if not canonical:
        err(rel, "缺少 rel=canonical")
    else:
        if canonical != page_url(rel):
            err(rel, "canonical 应为 %s，实际 %s" % (page_url(rel), canonical))
        if canonical in canonicals:
            err(rel, "canonical 与 %s 重复" % canonicals[canonical])
        canonicals[canonical] = rel

    # --- 社交分享 ---
    for prop in ("og:title", "og:description", "og:image", "og:type", "og:url"):
        if not text_of(html, r'<meta\s+property="%s"\s+content="([^"]*)"' % prop):
            err(rel, "缺少 %s" % prop)
    og_image = text_of(html, r'<meta\s+property="og:image"\s+content="([^"]*)"')
    if og_image:
        if not og_image.startswith("http"):
            err(rel, "og:image 必须是绝对地址：%s" % og_image)
        else:
            local = og_image[len(SITE):] if og_image.startswith(SITE) else ""
            if local and not os.path.isfile(os.path.join(ROOT, local)):
                err(rel, "og:image 指向的文件不存在：%s" % local)
    if not text_of(html, r'<meta\s+name="twitter:card"\s+content="([^"]*)"'):
        warn(rel, "缺少 twitter:card")

    # --- 结构化数据 ---
    for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S):
        try:
            json.loads(block)
        except json.JSONDecodeError as exc:
            err(rel, "JSON-LD 解析失败：%s" % exc)

    # --- 图片 alt ---
    for tag in re.findall(r"<img\b[^>]*>", html, re.I):
        if "alt=" not in tag:
            err(rel, "图片缺少 alt：%s" % tag[:80])

    # --- 页面内 id 唯一 ---
    ids = re.findall(r'\sid="([^"]+)"', html)
    dup = {i for i in ids if ids.count(i) > 1}
    for i in sorted(dup):
        err(rel, "id 重复：%s" % i)


def check_links(rel: str, html: str, anchors: dict[str, set[str]]) -> None:
    here = os.path.dirname(rel)
    for href in re.findall(r'<a\b[^>]*\bhref="([^"]*)"', html, re.I):
        if not href or href.startswith(("mailto:", "tel:", "#")):
            continue
        parts = urlsplit(href)
        if parts.scheme in ("http", "https"):
            if parts.netloc and parts.netloc not in ("duofreedom.github.io",):
                continue  # 外链不校验
            target = unquote(parts.path)
            base = ROOT
        else:
            target = unquote(parts.path)
            base = os.path.normpath(os.path.join(ROOT, here))
        if not target:
            continue
        if target.startswith("/Insta-camera-tools/"):
            target = target[len("/Insta-camera-tools/"):]
            base = ROOT
        elif target.startswith("/"):
            warn(rel, "站内链接使用了根路径，项目页部署在子路径下会 404：%s" % href)
            target = target.lstrip("/")
            base = ROOT

        full = os.path.normpath(os.path.join(base, target))
        if not full.startswith(ROOT):
            err(rel, "链接跑到仓库外：%s" % href)
            continue
        if os.path.isdir(full):
            full = os.path.join(full, "index.html")
        if not os.path.isfile(full):
            err(rel, "链接指向的文件不存在：%s" % href)
            continue

        frag = parts.fragment
        if frag and full.endswith(".html"):
            key = os.path.relpath(full, ROOT).replace(os.sep, "/")
            ids = anchors.get(key)
            if ids is not None and frag not in ids:
                err(rel, "锚点不存在：%s" % href)


def check_sitemap(pages: list[str]) -> None:
    path = os.path.join(ROOT, "sitemap.xml")
    if not os.path.isfile(path):
        err("sitemap.xml", "文件不存在")
        return
    xml = read(path)
    locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", xml)
    if not locs:
        err("sitemap.xml", "没有 <loc>")
        return
    listed = set(locs)
    for rel in pages:
        if rel in NOT_A_PAGE:
            continue
        if page_url(rel) not in listed:
            err("sitemap.xml", "缺少页面 %s" % page_url(rel))
    known = {page_url(p) for p in pages}
    for loc in locs:
        if loc not in known:
            err("sitemap.xml", "列了不存在的页面 %s" % loc)
    if len(locs) != len(listed):
        err("sitemap.xml", "存在重复 <loc>")


def check_robots() -> None:
    path = os.path.join(ROOT, "robots.txt")
    if not os.path.isfile(path):
        err("robots.txt", "文件不存在")
        return
    txt = read(path)
    if "Sitemap:" not in txt:
        err("robots.txt", "缺少 Sitemap: 行")
    if re.search(r"^Disallow:\s*/\s*$", txt, re.M):
        err("robots.txt", "Disallow: / 会屏蔽整站")


def ping_indexnow() -> int:
    """把 sitemap.xml 里的全部 URL 提交给 IndexNow（Bing、Yandex 等共用）。

    只有部署成功后才该跑：提交的 __Host__ 不存在时对方会直接回 422，
    而不是等到抓取阶段才发现。
    """
    locs = re.findall(r"<loc>([^<]+)</loc>", read(os.path.join(ROOT, "sitemap.xml")))
    if not locs:
        print("sitemap.xml 里没有 URL，先跑一遍站点生成")
        return 1
    payload = {
        "host": urlsplit(SITE).hostname,
        "key": INDEXNOW_KEY,
        "keyLocation": SITE + INDEXNOW_KEY + ".txt",
        "urlList": locs,
    }
    req = urllib.request.Request(
        "https://api.indexnow.org/indexnow",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "instatools-site-check/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            code = resp.status
            body = resp.read().decode("utf-8", "replace").strip()
    except Exception as exc:  # noqa: BLE001
        print("IndexNow 提交失败：%s: %s" % (type(exc).__name__, exc))
        return 1
    print(
        "IndexNow 提交 %d 条 URL，HTTP %d%s"
        % (len(locs), code, ("  " + body) if body else "")
    )
    return 0 if 200 <= code < 300 else 1


def main() -> int:
    pages = find_pages()
    if not pages:
        print("没有找到任何页面")
        return 2

    anchors: dict[str, set[str]] = {}
    for rel in pages:
        anchors[rel] = set(re.findall(r'\sid="([^"]+)"', read(os.path.join(ROOT, rel))))

    titles: dict[str, str] = {}
    descs: dict[str, str] = {}
    canonicals: dict[str, str] = {}
    for rel in pages:
        html = read(os.path.join(ROOT, rel))
        check_page(rel, html, titles, descs, canonicals)
        check_links(rel, html, anchors)

    check_sitemap(pages)
    check_robots()

    print("页面 %d 个：%s" % (len(pages), "、".join(pages)))
    for w in warnings:
        print("警告  %s" % w)
    for e in errors:
        print("错误  %s" % e)
    print("-" * 60)
    print("结果：%d 个错误，%d 个警告" % (len(errors), len(warnings)))
    if errors:
        return 1
    if "--ping-indexnow" in sys.argv:
        return ping_indexnow()
    return 0


if __name__ == "__main__":
    sys.exit(main())

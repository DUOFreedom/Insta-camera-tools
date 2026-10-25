[README_InstaAce.md](https://github.com/user-attachments/files/33917328/README_InstaAce.md)
<div align="center">

<img src="source/InstaAceImporter/assets/app.svg" width="120" alt="InstaAce">

# InstaAce 桌面端

**把普通视频变成影石 Ace Pro 2 的"原生"素材**

转码成相机原生结构（VID + LRV）· 移植 `inst` box · 登记相机索引
从此相册里能识别、能播放、封面正确

[![Version](https://img.shields.io/badge/version-1.2.0-blue?style=flat-square)](source/InstaAceImporter/CHANGELOG.md)
[![License](https://img.shields.io/badge/license-GPL--3.0-green?style=flat-square)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows%2010%20%7C%2011-lightgrey?style=flat-square)]()
[![Python](https://img.shields.io/badge/python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)]()
[![Tests](https://img.shields.io/badge/tests-31%20passed-brightgreen?style=flat-square)]()

[下载](#下载) · [怎么用](#使用) · [原理](#识别三要素改代码前必读) · [从源码构建](#从源码构建) · [常见问题](#常见问题)

</div>

---

## 下载

从 [**Releases**](../../releases) 下载 `InstaAceImporter.exe`，双击即可运行，无需安装。

```
InstaAceImporter.exe   37.78 MB
sha256  6599AD577194884DC3F3246CBEF60A27910AC2F96853A3806C920F2EC5D4102A
```

> ⚠️ **ffmpeg 需要自备**，放在 exe 同目录的 `bin\` 文件夹里
> （`bin\ffmpeg.exe` 和 `bin\ffprobe.exe`）。程序会按「exe 目录 → exe\bin → PATH」查找，找不到会明确报错。

## 使用

1. 把相机卡插到电脑，或选择一个输出文件夹
2. 拖入要导入的视频（支持多选、整个文件夹）
3. 点开始，等进度条走完
4. 拔卡插回相机，在相册里就能看到

<table>
<tr><td width="50%">

**特色**

- 🔍 **开工前体检** —— 开跑前 1 秒内检查 ffmpeg、磁盘空间、卡是否可写，问题当场拦下
- ⏸️ **可随时取消** —— 转码中途点取消，ffmpeg 进程干净退出，不留孤儿
- 🔁 **断点续跑** —— 中断后重开，问你要不要只跑没完成的那几条
- 🖼️ **同名封面** —— `a.mp4` 旁边有 `a.jpg` 就自动用它当封面

</td><td width="50%">

**还支持**

- 💤 **防休眠** —— 转长片时系统不会睡过去
- 📊 **三阶段进度** —— 转码 / 移植 / 登记分开显示，不糊成一条
- 📦 **批量处理** —— 几百条一起排队
- 🧪 **离线回归** —— 31 项测试，不依赖真机也能跑

</td></tr>
</table>

## 从源码构建

```powershell
git clone https://github.com/<你的用户名>/Insta-camara-tools.git
cd Insta-camara-tools\source\InstaAceImporter

pip install -r requirements.txt
python gui.py                    # 直接运行

python -m PyInstaller --noconfirm InstaAceImporter.spec   # 打包
```

## 常见问题

<details>
<summary><b>点开始没反应 / 报错找不到 ffmpeg</b></summary>

把 `ffmpeg.exe` 和 `ffprobe.exe` 放进 exe 同目录的 `bin\` 文件夹。
或者装到系统 PATH 里也行。
</details>

<details>
<summary><b>视频导进去了，但相机相册里看不到</b></summary>

检查三件事：① 编码结构是否达标（VID 需要 HEVC `hvc1` 1080p、`-g 16 -bf 0`）；
② `inst` box 是否移植成功；③ 索引是否登记。见下面「识别三要素」。
</details>

<details>
<summary><b>相册里能看到条目，但点了打不开</b></summary>

通常是 `f7` 时间戳写错（必须是 14 位 `YYYYMMDDHHMMSS`，写成 9 位就会这样），
或者 `f9` 偏移不是文件内的真实字节偏移。
</details>

<details>
<summary><b>超过 4GB 的长视频会失败吗</b></summary>

不会。moov 重封装对 `stco`/`co64` 和 32/64 位 box 长度都做了支持。
</details>

<details>
<summary><b>Windows 提示"未知发布者"或杀软报毒</b></summary>

PyInstaller 打包的程序没有代码签名，会触发 SmartScreen。
点「更多信息 → 仍要运行」。杀软误报可以加白名单。
</details>

---

## 目录结构

```
InstaAce_Desktop（仓库根）\
├─ source\InstaAceImporter\        源码工程（可直接 build）
│  ├─ core.py                     核心：转码 + inst 移植 + 索引登记（2100 行）
│  ├─ gui.py                      PyQt5 界面（MD 风格卡片、拖拽、三阶段进度）
│  ├─ insta_index.py              影石索引 protobuf 读写
│  ├─ cpvc_origin\                逆向参考实现（对照用，不参与授权）
│  ├─ tests\test_insta.py         离线回归（31 passed / 2 skipped）
│  ├─ assets\                     图标（app.svg / app-small.svg / app.ico）
│  ├─ tools\make_icon.py          SVG → 多尺寸 ICO 生成器
│  ├─ LICENSE / README.md / CHANGELOG.md / .gitignore
│  └─ build.bat / run.bat / InstaAceImporter.spec
└─ LICENSE / README.md / .gitignore
```

---

## 项目结构说明

`source\InstaAceImporter\cpvc_origin\` 是逆向分析的参考实现，用于对照理解
`inst` box 结构与索引格式，**不是**主程序运行依赖。

---

## 回归测试

```powershell
cd Insta-camara-tools\source\InstaAceImporter
pip install -r requirements-dev.txt
python -m pytest -q
```

当前结果 `31 passed, 2 skipped`（跳过项需真机索引样本，仓库不含样本）。
覆盖：`f7` 十四位时间戳、隐藏+只读文件写入与属性恢复、`inst` box 探测、
进度分段映射、编码族 level 换算、同名封面查找、体积估算、开工体检、续跑账本。

---

## 识别三要素（改代码前必读）

| 层 | 要求 | 缺失后果 |
|---|---|---|
| 编码结构 | VID: HEVC `hvc1` 1080p 30fps `-g 16 -bf 0`；LRV: H.264 `avc1` 480p | 打不开／不显示 |
| `inst` box | 用**卡内真机原片**（3 条 trak，含 `tmcd`）当模板重封装 | 相机视为外来文件 |
| 索引登记 | `DCIM\fileinfo_list.list` + `.editinfo_list.list` | 相册里不出现 |

关键字段：

- `f7` = 14 位 `YYYYMMDDHHMMSS`（不带序号），写成 9 位会「能列出但打不开」
- `f9` = inst box 在文件中的**字节偏移**，不是文件大小
- 索引 meta 必须与文件内 `inst` meta **逐字节一致**
- **只登记 VID，不登记 LRV**（多登记会出现 0KB 打不开的条目）
- `.editinfo_list.list` 是隐藏文件，必须 `r+b` 原地改写，`wb` 会 PermissionError
- 缩略图（896×512 NV12）必须在 `rebuild_media` **之前**写入，顺序错了会不能播

---

## 已知排除项

- `bin\`（ffmpeg 2×222 MB）未包含，请自备
- `build\` / `dist\`（PyInstaller 中间产物）未包含
- `__pycache__` / `.pytest_cache` 未包含

`samples\` 目录已从仓库与打包配置中彻底移除（它含真机设备序列号）。
如自行采集索引样本做回归测试，请勿提交——两份 `.gitignore` 均已覆盖该路径。

# 开源合规声明

本应用以 **GPL-3.0-or-later** 发布。以下列出运行时与构建期使用的全部第三方组件。

---

## 一、许可结论

| 项目 | 内容 |
|---|---|
| 本项目许可 | GNU General Public License v3.0 or later |
| 完整文本 | 仓库根目录 `LICENSE` / <https://www.gnu.org/licenses/gpl-3.0.html> |
| 源码地址 | <https://github.com/DUOFreedom/Insta-camera-tools> |
| 分发形式 | GPL 允许的自由软件分发，同时提供对应源码 |

**为什么是 GPL-3.0**：应用静态链接了 FFmpeg 7.1 并使用其中的
libx264 与 libx265，二者均为 GPL-2.0-or-later。GPL-2.0+ 与 GPL-3.0
兼容，因此整体以 GPL-3.0-or-later 发布。

---

## 二、运行时组件

| 组件 | 版本 | 许可证 | 用途 |
|---|---|---|---|
| [FFmpeg](https://ffmpeg.org/) | 7.1 | GPL-2.0-or-later | 转码与封装 |
| [libx264](https://www.videolan.org/developers/x264.html) | 静态链接 | GPL-2.0-or-later | H.264 编码（LRV 预览文件） |
| [libx265](https://www.videolan.org/developers/x265.html) | 静态链接 | GPL-2.0-or-later | HEVC 编码（主视频） |
| [Python](https://www.python.org/) | 3.11 | PSF License | 导入核心运行环境 |
| [Chaquopy](https://chaquo.com/chaquopy/) | 16.0.0 | MIT（运行时） | 在 Android 上内嵌 CPython |
| [Kotlin](https://kotlinlang.org/) | 1.9.24 | Apache-2.0 | 应用界面语言 |
| [Jetpack Compose](https://developer.android.com/jetpack/compose) | BOM 2024.06.00 | Apache-2.0 | 应用界面框架 |
| [AndroidX Core](https://developer.android.com/jetpack/androidx) | 1.13.1 | Apache-2.0 | 基础组件 |
| [AndroidX Activity](https://developer.android.com/jetpack/androidx/releases/activity) | 1.9.0 | Apache-2.0 | Activity 与结果回调 |
| [AndroidX Lifecycle](https://developer.android.com/jetpack/androidx/releases/lifecycle) | 2.8.2 | Apache-2.0 | 生命周期与状态 |
| [AndroidX DocumentFile](https://developer.android.com/jetpack/androidx/releases/documentfile) | 1.0.1 | Apache-2.0 | SAF 目录访问 |

### FFmpeg 与 GPL 的对应源码

应用内打包的 `libffmpeg.so` 与 `libffprobe.so` 是**静态链接**的
FFmpeg 7.1 可执行文件（含 libx264、libx265），本质为 PIE 可执行文件，
仅沿用 `lib*.so` 命名以便随 APK 打入 `nativeLibraryDir`。

GPL 要求提供「对应源码」与可重建方式，两者均公开：

- FFmpeg 源码：<https://ffmpeg.org/download.html>（7.1 分支）
- libx264 源码：<https://code.videolan.org/videolan/x264>
- libx265 源码：<https://bitbucket.org/multicoreware/x265_git>
- 本项目的交叉编译脚本与完整步骤：仓库内 `docs/BUILD.md`

你可以按该文档用 NDK r27 自行重建出功能等价的二进制并替换
`android/app/src/main/jniLibs/<abi>/` 下的文件后重新打包。

---

## 三、构建期组件

| 组件 | 许可证 | 用途 |
|---|---|---|
| [Android Gradle Plugin](https://developer.android.com/build) | Apache-2.0 | 安卓构建 |
| [Gradle](https://gradle.org/) | Apache-2.0 | 构建系统 |
| [Chaquopy Gradle Plugin](https://chaquo.com/chaquopy/) | 商业许可（免费用于开源项目） | 打包 Python 与生成代理 |
| [PyInstaller](https://pyinstaller.org/)（桌面端） | GPL-2.0+ with bootloader exception | 桌面端打包 |
| [pytest](https://pytest.org/) | MIT | 桌面端回归测试 |

---

## 四、自有实现部分

以下能力为本项目自行实现，**未引入第三方库**：

| 能力 | 说明 |
|---|---|
| 索引 protobuf 编解码 | `insta_index.py`：无长度前缀的 protobuf 流读写，自行实现字段编解码，未使用 `protobuf` 库 |
| `inst` box 移植 | `inst_transplant.py`：`camera_udta` 字段表驱动写入、AMBA 越界校验、`ftyp` 补丁 |
| moov 重封装 | `moov_rewrap.py`：moov 骨架重建、音视频样本重排、`avc1` 采样条目精简 |

除上述组件外，共享核心仅使用 Python 标准库
（`struct`、`zlib`、`subprocess`、`urllib`、`threading`、`ctypes`、
`pathlib`、`dataclasses` 等）。

---

## 五、致谢

- **FFmpeg 项目** —— 转码与封装的基础设施
- **YCTS-otree** —— 感谢其在影石相机文件格式逆向分析上的公开工作，
  为理解 `inst` box 布局与索引 protobuf 结构提供了重要参考
- **Insta360 官方社区** —— 设备使用与格式相关的公开讨论

---

## 六、合规提示

本声明仅描述本项目的第三方组件许可情况，不构成法律意见。

本项目通过改写未公开的文件格式与相机索引实现导入功能，
这属于对文件格式的独立逆向分析。**本项目不包含、不破解、不反编译任何
商业软件的授权代码**，与影石创新科技股份有限公司无任何关联。

若你是权利持有人并认为本项目侵犯了你的权益，请通过
<https://github.com/DUOFreedom/Insta-camera-tools/issues> 联系，
我们会及时处理。

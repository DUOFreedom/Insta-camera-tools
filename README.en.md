<p align="center">
  <img src="desktop/assets/app.svg" width="112" alt="instatools">
</p>

<h1 align="center">instatools</h1>

<p align="center">
Convert ordinary videos into native formats recognized by Insta360 camera albums: produce paired VID + LRV files, transplant the camera's proprietary <code>inst</code> box, and register DCIM index.
</p>

<p align="center">
  <a href="README.en.md">English</a> · <a href="README.md">中文</a>
</p>

<p align="center">
  Website · <a href="https://duofreedom.github.io/Insta-camera-tools/">Home</a> · <a href="https://duofreedom.github.io/Insta-camera-tools/guide/">Guide</a> · <a href="https://duofreedom.github.io/Insta-camera-tools/faq/">FAQ</a>
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-GPL--3.0--or--later-blue?style=flat-square" alt="License"></a>
  <a href="desktop/CHANGELOG.md"><img src="https://img.shields.io/badge/version-1.3.0-success?style=flat-square" alt="Version"></a>
  <a href="desktop/requirements.txt"><img src="https://img.shields.io/badge/python-3.10%2B-3776ab?style=flat-square" alt="Python"></a>
  <a href="desktop/tests"><img src="https://img.shields.io/badge/tests-215%20passed-brightgreen?style=flat-square" alt="Tests"></a>
  <img src="https://img.shields.io/badge/platform-Windows%20%7C%20Android-6f42c1?style=flat-square" alt="Platform">
</p>

---

## 📦 Installation

Both desktop and Android run the same conversion logic (two manually-synced copies). Choose the platform based on where you want to convert.

### Desktop (Windows)

```bash
git clone https://github.com/DUOFreedom/Insta-camera-tools.git
cd Insta-camera-tools/desktop
pip install -r requirements.txt
```

`requirements.txt` only installs `PySide6>=6.5`. Requires Python 3.10+.

Desktop entry: `desktop/run_qml.bat` (`pythonw main.py`), build script: `desktop/build_qml.bat` → `desktop/dist/instatools.exe` (single file, ~79 MB).

<details>
<summary>Desktop Feature Matrix</summary>

Originally two parallel UIs existed (PyQt5 classic + QML). The classic version has been deleted; only QML remains — both UIs shared the same logic, and bugs were always "fixed once, forgotten the second time." Merging eliminates this drift.

The nine missing features in QML have all been added back, each guarded by tests (`desktop/tests/test_qml_bridge.py`):

| Feature | Entry |
|---------|-------|
| Pre-flight check | `Bridge.start()` calls `core.preflight` |
| Auto sample detection | `Bridge.autoDetectSample` |
| Cover selection | `Bridge.pickCover` / `clearCovers` |
| Resume from interruption | `Bridge.checkResume` + `core.save_job` in `_run` |
| Card verify & repair | `Bridge.verifyCard` / `repairCard` |
| Locate SD card | `Bridge.locateCard` |
| Remove single file | `Bridge.removeFile` |
| Hardware encoder detection | `Bridge.detectHardware` |
| Drag & drop add | `DropArea` → `Bridge.addPaths` |

When closing during conversion, two options: **Stop & Exit** (`cancel()` + `waitWorker(20000)` waits for thread to finish before quitting), **Minimize to tray** (conversion continues, notification on completion). Direct exit would leave ffmpeg as an orphan writing partial VID/LRV to the camera card with unregistered index.

</details>

### Android

```bash
cd android
gradle --offline :app:assembleRelease
```

Output: `android/app/build/outputs/apk/release/app-release.apk` (~75 MB). Requires JDK 21, Gradle 8.11.1, Android SDK 35, Python 3.11. Ensure `JAVA_HOME`, `ANDROID_HOME`, `CHAQUOPY_PYTHON`, `GRADLE_USER_HOME` point to local installs. Full requirements in [`docs/BUILD.md`](docs/BUILD.md).

> **Cloning alone won't build Android.** No Gradle wrapper (`gradlew`), and `android/app/src/main/jniLibs/` (4 ffmpeg/ffprobe binaries ~91 MB, dual ABI `arm64-v8a` + `armeabi-v7a`) are `.gitignore`d. See [`docs/BUILD.md`](docs/BUILD.md) for how to obtain them.

### Installing ffmpeg

Desktop needs ffmpeg **with libx264 + libx265**. The program searches in this order — **system first, then program directory**:

| Order | Location |
|-------|----------|
| 1 | Env vars `FFMPEG_PATH` / `FFPROBE_PATH` |
| 2 | Registry `App Paths\ffmpeg.exe` (installer-registered, HKLM before HKCU) |
| 3 | `C:\Program Files\instatools\bin` (program's "install to system" target) |
| 4 | `C:\Program Files\ffmpeg\bin`, `C:\Program Files (x86)\ffmpeg\bin`, `C:\ffmpeg\bin`, `%ProgramData%\chocolatey\bin`, `~\scoop\shims`, `%LOCALAPPDATA%\Microsoft\WinGet\Links` |
| 5 | System `PATH` (`shutil.which`) |
| 6 | exe directory and its `bin\` subdirectory |
| 7 | `%LOCALAPPDATA%\instatoolsImporter\bin`, `~\instatoolsImporter\bin` |

Implementation: `desktop/core.py:161` `_system_tool_dirs()`, `desktop/core.py:146` `_portable_tool_dirs()`, `desktop/core.py:179` `_registry_ffmpeg()`. After finding, runs `ffmpeg -version` to verify.

If none found, UI shows an orange banner with two buttons:

| Button | Installs to | Requires |
|--------|-------------|----------|
| Install to system | `C:\Program Files\instatools\bin`, available to all apps, registers in Registry `App Paths` | Admin rights (UAC prompt) |
| Install to program dir | `bin\` next to exe, falls back to `%LOCALAPPDATA%\instatoolsImporter\bin` if unwritable | No permissions needed |

Both buttons **download to temp first, then install**: if user cancels UAC, only a few seconds lost, no re-download of 200 MB. After install, hardware encoder detection re-runs automatically, so the "no hardware encoder" banner disappears.

<details>
<summary>Manual ffmpeg path override</summary>

```bash
set FFMPEG_PATH=D:\tools\ffmpeg\bin\ffmpeg.exe
set FFPROBE_PATH=D:\tools\ffmpeg\bin\ffprobe.exe
```

Must be a build with libx264 + libx265; stripped builds fail at transcode with "encoder not found".
</details>

---

## 🚀 Quick Start

### Command Line

```bash
python desktop/core.py D:/clips/holiday.mp4 D:/card/DCIM/Camera01
```

Outputs two files (`stamp` from source video's capture time, `NNN` is sequence number):

```
VID_20261109_183000_000.mp4
LRV_20261109_183000_000.lrv
```

Timestamp prefers embedded `creation_time` in container, then filesystem time, falls back to current time (`desktop/core.py:1594` `_source_stamp()`). Imported videos sort by original capture date in the album, not all bunched on import day.

Main and proxy encoding format, resolution, framerate, GOP **all follow the native template on the card**: Ace Pro 2 uses `libx265`+`hvc1` / `libx264`+`avc1`, GOP 16; GO Ultra both tracks are `hvc1`, GOP 120 and 10. Template GOP measured from `stss` (`shared/instbox/inst_transplant.py:233` `video_gop()`), written into AMBA box offset 53 and simultaneously constrains ffmpeg `-g`. See `desktop/core.py:67-72` and `desktop/core.py:1194-1200`.

### Batch Convert

Pass a directory as first argument; program filters by extension (`.mp4` `.mov` `.mkv` `.avi` `.ts` `.flv` `.wmv` `.m4v`) and converts each:

```bash
python desktop/core.py D:/clips D:/card/DCIM/Camera01
```

Ends with `Succeeded N, failed M.`, failures listed with reasons.

### GUI

1. Double-click `desktop/dist/instatools.exe`, or run `run_qml.bat` in `desktop/`.
2. Set output directory to card's `DCIM\Camera01`.
3. Pick any camera-native `VID_*.mp4` on the card as sample, or click "Auto detect from SD card" to let it find one.
4. Add videos, click "Start Convert".
5. Eject card, reinsert into camera; album should show the video.

---

## 🔧 Configuration

### Command Line Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| Input path | Required | Video file, or directory containing videos |
| Output dir | Input file's directory | Recommend pointing to `DCIM\Camera01` |
| Start sequence | Auto-continue | Scans max existing sequence on card when omitted |

Running without args prints usage and exits with code 1. Three positional args parsed in `desktop/core.py:3104` `__main__` block.

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `FFMPEG_PATH` | Auto-find | Absolute path to ffmpeg executable |
| `FFPROBE_PATH` | Auto-find | Absolute path to ffprobe executable |
| `INSTA_LANG` | Follow system | `zh` or `en`, overrides the UI language |

The first two must be existing files to be used; otherwise falls back to search order.

### UI Language

Both the desktop app and the Android app follow the system UI language; there is no language switch. The product name is `instatools` in English and 影石相机工具 in Chinese.

Resolution order: `INSTA_LANG` > Windows user UI language > Qt `QLocale` > English. `INSTA_LANG` exists for troubleshooting and screenshots (`set INSTA_LANG=en` before launching), not for everyday use.

A missing translation falls back to the Chinese original — no crash, and no internal keys leaking into the UI. The table lives in `desktop/i18n.py` (210 entries, keyed by the Chinese text).

### Camera Model Preset

| Option | Default | Description |
|--------|---------|-------------|
| Model preset | `Auto` | `Auto` = measure the spec from the native clip on the card; `Ace Pro 2` / `GO Ultra` = use the built-in preset |

Only needed when the card has no native clip to use as a template: the spec then comes from `CAMERA_PRESETS` instead of the template. When a native clip is present it always wins, preset or not.

Desktop picks it under "Output & options", Android picks it on the settings screen; the two preset tables hold the same values. The preset only decides encoding parameters: the inst transplant still requires a native pair on the card as a template, so picking a model does not make transplant possible without one.

### Android Settings

| Option | Default | Description |
|--------|---------|-------------|
| Model preset | `Auto` | Same as desktop, uses the built-in preset when the card has no native clip |
| Encoder | `Auto` | `Auto` = software libx265 + libx264 |
| Register camera index | On | Writes fileinfo / editinfo under DCIM, required for album appearance |

<details>
<summary>Why "Hardware" encoding may make camera not recognize</summary>

MediaCodec keyframe interval limited by system `MediaFormat` to whole seconds only. Camera requires dense GOP (Ace Pro 2: 16 frames, GO Ultra VID: 120 frames). At 30fps, 16 frames ≈ 0.53s; hardware can only do 1s.

Result: files generate and play, but camera may show no thumbnail or not recognize at all. If missing from album after import, switch back to "Auto" and re-import. This limitation is also documented in Android settings screen.
</details>

<details>
<summary>Supported Cameras</summary>

Specs not hardcoded — measured from the **native source pair** on the card, so new cameras need no code changes:

| Item | Ace Pro 2 | GO Ultra | Source |
|------|-----------|----------|--------|
| VID | HEVC 1080p | HEVC 1080p @59.94 | ffprobe |
| VID keyframe interval | 16 | 120 | `stss` |
| LRV encoding | H.264 `avc1` | HEVC `hvc1` | `stsd` |
| LRV keyframe interval | 16 | 10 | `stss` |
| `AMBA[53]` | 16 | 120 / 10 | Above two |

Conversion picks encoder and `-g` from template; `inst` box transplant writes real interval into `AMBA[53]` (camera uses it for thumbnail frame positions). Switching cameras only requires leaving one native clip of that camera on the card — no code or config changes.

GO Ultra support came from user-provided real footage; both cameras' differences documented in [CHANGELOG](desktop/CHANGELOG.md) "Go Ultra Camera Support" section.
</details>

---

## ❓ FAQ

### `ValidationError: 未找到 ffmpeg，无法构建转码命令` / `ValidationError: ffmpeg not found, cannot build transcode command`

Program couldn't find ffmpeg (`desktop/core.py:1027`). Check search order above; quickest is explicit override:

```bash
set FFMPEG_PATH=D:\tools\ffmpeg\bin\ffmpeg.exe
set FFPROBE_PATH=D:\tools\ffmpeg\bin\ffprobe.exe
```

`ffmpeg -version` must run normally; stripped builds (no libx264/libx265) fail at transcode.

### `目标不是影石相机卡（缺少 DCIM\Camera01 结构）` / `Target is not an Insta360 camera card (missing DCIM\Camera01 structure)`

Pre-index validation ensures target is a real camera card to avoid polluting ordinary folders with `DCIM` (`desktop/core.py:2111`). Point output to card's `DCIM` or `DCIM\Camera01` and re-run.

### `卡里找不到真机原片作模板（DCIM\Camera01\VID_*.mp4 + LRV_*.lrv）` / `No native source pair found on card (DCIM\Camera01\VID_*.mp4 + LRV_*.lrv)`

Program needs a pair of **camera-native** VID/LRV as template — it copies the template's `inst` box structure and index entry format (`desktop/core.py:2279`).

Fix: Record a few seconds with the camera first, leave it on the card, then run conversion.

### `缓存空间不足：源 2.1 GB，可用 800 MB` / `Insufficient cache: source 2.1 GB, available 800 MB`

Android import copies source to app private dir first, reserving 3× source size (transcode intermediates + output; criterion in `AppState.kt:373`). Free up phone storage or remove large files from queue.

### Android build error `Plugin [id: 'com.android.application', version: '8.7.3'] was not found`

<details>
<summary>Expand for fix</summary>

Gradle looking in wrong cache directory. Project needs AGP 8.7.3, but default `~/.gradle` usually has older versions:

```bash
export GRADLE_USER_HOME=D:/android-build/.gradle
```

If error `Minimum supported Gradle version is 8.9. Current version is 8.7`, Gradle itself too old — must use 8.11.1. Both cached in same dir; only 8.11.1 builds. See [`docs/BUILD.md`](docs/BUILD.md).
</details>

---

## 🤝 Contributing

```bash
cd desktop
pip install -r requirements-dev.txt
python -m pytest tests/ -q
```

Expected `215 passed, 3 skipped`. Two of the three skips need real device index samples (`desktop/samples/`, `android/app/src/test/resources/samples/`; samples contain device IDs, not committed by convention), the third needs a working ffmpeg to construct a transcode that must fail.

Before changing code, read [`docs/BUILD.md`](docs/BUILD.md). Two common pitfalls:

- **Shared logic has multiple copies; fix one, must fix the other.** `shared/insta_index.py` and `android/app/src/main/python/insta_index.py` are two copies; `desktop/tests/test_insta.py:491` `test_insta_index_copies_do_not_drift` uses AST comparison (docstrings stripped) — drift fails immediately. `shared/instbox/` modules on Android have **different filenames**:

| Desktop | Android |
|---------|---------|
| `shared/instbox/inst_transplant.py` | `android/app/src/main/python/insta360_tf_import.py` |
| `shared/instbox/moov_rewrap.py` | `android/app/src/main/python/camera_moov_rewrap.py` |
| `shared/insta_index.py` | `android/app/src/main/python/insta_index.py` |

- **Update artifact records after changes:** `desktop/CHANGELOG.md` logs each rebuild's measured size and verification method; run both builds before commit.

---

## 📄 License

[GPL-3.0-or-later](LICENSE).

Project links libx264 / libx265 (GPL-2.0-or-later); actual FFmpeg 7.1 is therefore GPL-2.0-or-later, compatible with GPL-3.0. Third-party notices in [`android/app/src/main/assets/docs/open-source-notices.md`](android/app/src/main/assets/docs/open-source-notices.md).

---

## 🗂 Architecture

<details>
<summary>Repository Structure & Module Responsibilities</summary>

```
Insta-camera-tools/
├── shared/                       # Desktop's sole reference source
│   ├── insta_index.py            # Camera index protobuf parse / generate
│   └── instbox/
│       ├── inst_transplant.py    # inst box transplant, ftyp patch
│       └── moov_rewrap.py        # moov rebuild, sample reorder, avc1 strip
├── desktop/                      # Windows Desktop
│   ├── core.py                   # Transcode core (shared by UI / CLI)
│   ├── main.py                   # Entry (PySide6 + QApplication)
│   ├── bridge.py                 # Bridge between UI and core.py
│   ├── tray.py                   # System tray (minimize during conversion)
│   ├── updater.py                # Update check
│   ├── qml/                      # 23 .qml files (incl. main.qml)
│   └── build_qml.bat             # Build script
├── android/                      # Gradle + Chaquopy
│   ├── app/src/main/python/      # insta_core.py / android_bridge.py etc.
│   └── app/src/main/java/        # Kotlin (Compose UI + Python engine wrapper)
└── docs/BUILD.md                 # Dual-platform build guide
```

`desktop/qml/` has 23 `.qml` files (incl. `main.qml`). `Card.qml`, `Divider.qml`, `Sidebar.qml`, `TextArea.qml`, `Toast.qml`, `Tooltip.qml` — 6 files unreferenced by any QML (still registered in `qmldir`).

> On "shared": `shared/` is desktop's **only** reference (no copies under `desktop/`). Android Chaquopy only packages `android/app/src/main/python/`, so that directory keeps same-name copies. **Logically equivalent but not byte-identical** (Android copies drop GPL headers and some Chinese comments). When modifying shared logic, **both places must be updated**; `desktop/tests/` only covers desktop.

</details>

<details>
<summary>Why "Transcode + Transplant" Two Steps</summary>

Camera doesn't just check extension — it validates three things simultaneously:

1. **Filename & Index**: `VID_YYYYMMDD_HHMMSS_NNN.mp4` format, with matching entry in `DCIM\fileinfo_list.list`.
2. **`inst` box**: Insta360-private metadata inside MP4 `moov`, storing thumbnail, creation time, camera model, etc. Without it, file plays but album ignores it.
3. **AMBA fields**: Camera-specific field table in `udta`, framerate/audio params at fixed offsets; out-of-bounds or misaligned = rejected.

So the pipeline: ffmpeg transcodes to camera-spec VID/LRV pair (16-frame dense GOP, hvc1/avc1 tags, specified color range), then copies `inst` box structure from native template, patches timestamps/thumbnail inside, finally appends new entries to index. Index is append-only — existing videos on card unaffected.

Index files at card root: `DCIM\fileinfo_list.list` and `DCIM\.editinfo_list.list` (note leading dot). Field definitions in `shared/insta_index.py` top docstring.

</details>

<details>
<summary>Known Limitations</summary>

- **Real-device pipeline not end-to-end verified**: AMBA field fixes only verified at offset level with synthetic templates; MediaCodec hardware encode/decode path has auto-fallback but untested on device. First real import: compare output with native clip using `ffprobe` on `avg_frame_rate` / `nb_frames`.
- **Android APK not shipped with Release**: Real import pipeline and some camera compatibilities not fully verified.
- **Signing**: Defaults to `~/.android/debug.keystore` only for overwriting old versions. Production distribution **must** configure own certificate (`INSTA_KEYSTORE` / `INSTA_KEYSTORE_PASSWORD` / `INSTA_KEY_ALIAS` / `INSTA_KEY_PASSWORD`); otherwise anyone with debug.keystore can forge update packages.

</details>
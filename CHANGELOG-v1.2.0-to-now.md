# 影石相机工具 - v1.2.0 到当前版本的变更日志

> 统计：v1.2.0 (tag `1a4eff8`) 以来共 **78 个提交**，涵盖桌面端 QML 重构、安卓端同步、GO Ultra 机型适配、ffmpeg 安装重写、代码质量提升等。
>
> 注：本文写于改名前，文中 `InstaAceQml.exe`、`InstaAceImporter`、`C:\Program Files\InstaAce\bin`、`com.duofreedom.instaace` 现分别为 `instatools.exe`、`instatoolsImporter`、`C:\Program Files\instatools\bin`、`com.duofreedom.instatools`。逐条改名记录见 `desktop/CHANGELOG.md`。

---

## 🎉 重大新功能

### 1. GO Ultra 机型完整适配
- **核心差异自动识别**：不再写死 Ace Pro 2 参数，从卡里真机原片量出规格
- **VID/LRV 编码跟随模板**：GO Ultra 两轨均为 HEVC `hvc1`，Ace Pro 2 为 HEVC + H.264 混合
- **GOP 从 stss 实测**：VID=120、LRV=10（Ace Pro 2 为 16）
- **AMBA[53] 写真实 GOP**：相机按此声明抽帧位置
- **代理轨元数据不过度改写**：LRV 的 f19/f20/f44 与主视频保持一致

### 2. 机型预设选择（桌面端）
- 界面「输出与选项」最顶部新增机型下拉：**自动 / Ace Pro 2 / GO Ultra**
- 选机型后按预设参数生成（编码、GOP、分辨率、帧率、音轨数）
- 选「自动」时若有原片仍优先用原片实测规格
- 安卓端同步 `CAMERA_PRESETS` 常量表

### 3. ffmpeg 查找与安装逻辑重写
- **新查找优先级**：环境变量 → 注册表 App Paths → 系统目录 → PATH → 程序目录
- **下载/安装分离**：先下到临时目录，再按 scope 落盘
- **双模式安装**：
  - 装到系统目录（`C:\Program Files\InstaAce\bin`，需 UAC，登记 App Paths）
  - 装到程序目录（exe 同目录 `bin\`，无需权限）
- 界面横幅改为双按钮「装到系统目录 / 装到程序目录」

---

## 🔧 核心修复

### 1. 自动分析样本不再卡死 UI
- `autoDetectSample` 改为后台线程执行
- 找到样本后通过 `QMetaObject.invokeMethod` 切回主线程
- 未找到时同理切回主线程报错

### 2. 模板选择逻辑修正
- 桌面端补齐 `template_from_names`，按用户实际选的样本名取模板
- 先试 `template_from_names` 再回落 `find_native_template`
- 安卓端同步，两端行为一致

### 3. 安卓端四处硬化跟齐桌面端
- `save_job`：不再静默吞 OSError
- `has_inst_box`：删除无用代码
- `render_cover`：补齐参数校验、cancel、timeout、错误处理
- `convert` 并发驱动：兜底记录 first_error，不再吞异常报成功

### 4. 端到端 GO Ultra 验证发现的两处缺陷
- `video_gop` 接受 `str` 路径（原只接受 `Path`，AttributeError 被吞导致 GOP 退化为 16）
- QSV/AMF 分支补上显式 `-g/-keyint_min`（原只 nvenc 加了，导致关键帧间隔默认 3 秒）

### 5. MCRC 按产物自身 mdat 重算
- 真机 VID 有 MCRC box（三个小端 u32：crc32、长度、0）
- 移植时按产物自己的 mdat 重算，不再沿用模板值

### 5. 序列号定位强化
- 从「最后一个 0a 0e + 14B alnum」改为「0a 0e + 14B + 12 11 + Insta360」
- f1 紧接 f2 机型名，全 inst 唯一命中

### 6. 安卓副本补齐 co64 支持
- `rebuild_stbl` 识别 `stco` 和 `co64` 两种 chunk offset 表
- 写入时按偏移量自动选 32/64 位

---

## 🎨 界面与体验

### 桌面端 QML 版
- **机型选择移到最上方**（编码器、输出目录之前）
- 删除 PyQt5 经典界面，只保留 QML 版（维护成本↓）
- QML 版补齐经典版全部 9 项缺失功能：
  - 开工前体检、自动找样本、封面选择、断点续跑
  - 卡校验与清理、定位 SD 卡、单条移除
  - 硬件编码器探测、拖拽添加
- 转换中关窗给两个出路：停止并退出 / 最小化到托盘继续跑
- 封面预览修复（`QUrl.fromLocalFile` 代替裸路径）
- lastError 粘性问题修复

---

## 🧪 测试与质量

- **测试总数**：177 passed, 3 skipped（从 v1.2.0 的 ~55 增加到 180+）
- **回滚验证**：关键修复均做了「改回缺陷版本 → 测试变红 → 恢复 → 测试绿」
- **行为测试替代 grep 测试**：造真 box 喂进去、真调一次、断言实际参数
- **双端副本漂移守卫**：AST 比对桌面端/安卓端共享模块
- **零调用符号清理**：删 7 组死代码（`_num`、`_audio_map`、`add_file_entry` 等）

---

## 📦 产物

| 平台 | 产物 | 尺寸 | 验证 |
|------|------|------|------|
| Windows | `InstaAceQml.exe` | ~80.5 MB | `--self-test` → `QML_OK roots=1` |
| Android | `app-release.apk` | ~75 MB | 单元测试 18 通过 (IndexTest 7 跳过, ConsentLogicTest 5, ImportCardStateTest 6) |

---

## 🔖 提交列表（按时间倒序，前 20 条）

```
9201fd2 feat: 机型选择移到最上方 + 修复自动分析卡死问题
cb6099a feat: 增加机型预设选项（Ace Pro 2 / GO Ultra / 自动）
ebcdda9 docs: README 添加中英双语支持
6313e7a feat: ffmpeg 查找与安装逻辑重写（先系统后本地、全局/程序目录双模式、UAC 分离）
1c99ee8 docs: 同步 QML 版补全功能后的产物尺寸与核对项
8ee528a feat: QML 版补齐经典版全部功能（封面/续跑/校验/定位卡/单条移除/硬件探测/拖拽）
ac76814 refactor: 删除 PyQt5 经典界面，QML 版补齐 preflight/自动找样本/托盘
991753c fix: 修审查报告里的三处小缺陷 + batch_convert 静默推翻软件编码选择
eb6deeb docs: 同步 MCRC 修复后的产物尺寸与核对结论
5c747d0 fix: MCRC 按产物自己的 mdat 重算
c743f5f docs: 同步重建后的产物尺寸与核对结论
907cb0f fix: 安卓副本补齐 co64，两份 rebuild_stbl 都认 co64
65e6626 fix: 序列号定位改用「f1 紧接 f2 机型名」的强特征
c294b25 docs: 补记本轮端到端验证与产物核对
3e032b1 fix: 端到端跑通时发现的两处 GOP 缺陷
c7a4dd7 fix: CLI 路径的关键帧间隔也跟随模板
c549167 fix: 按逆向报告修四处机型硬编码（采样条目/代理编码/代理元数据）
389b8e2 fix: QML 版补关窗拦截与路径还原（两处数据风险）
16dcf73 fix: 桌面端补齐模板固定 + 安卓端跟齐四处硬化
d59862f feat: 增加 GO Ultra 机型适配（LRV 编码/GOP/AMBA 跟随模板）
```

---

## ⚠️ 已知限制（未变）

- **真机链路未端到端验证**：AMBA 字段修复只做了合成模板的偏移级验证，MediaCodec 硬件编解码路径带自动回退但未经真机确认
- **安卓 APK 不随 Release 分发**：真机导入链路与部分机型兼容性尚未验证完毕
- **签名**：默认回退到 `~/.android/debug.keystore`，正式分发必须配置自有证书

---

> 生成时间：2026-11-11  
> 基准版本：v1.2.0 (tag `1a4eff8`)  
> 当前 HEAD：`9201fd2`
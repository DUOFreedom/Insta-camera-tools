import QtQuick
import QtQuick.Window
import QtQuick.Controls.Basic
import QtQuick.Dialogs

Window {
    id: win

    width: 1024
    height: 720
    minimumWidth: 720
    minimumHeight: 480
    visible: !selfTest
    title: bridge.appName
    flags: Qt.Window | Qt.FramelessWindowHint
    color: "transparent"

    onVisibleChanged: {
        if (visible)
            tray.hide()
    }

    Component.onCompleted: {
        Theme.dark = systemDark
        if (selfTest)
            return
        updater.check()
        bridge.checkFfmpeg()
        bridge.detectHardware()
        bridge.refreshSequence(outputView.outputDir, outputView.autoSequence)
        if (updateDemo)
            updateModal.open = true
        //   首次进软件、或者协议改版之后，先看三页说明。selfTest 上面已经
        //   返回了，打包自检不会卡在一个等人点的窗口上。
        if (bridge.welcomeNeeded || welcomeDemo)
            welcome.open = true
    }

    Connections {
        target: updater
        function onStateChanged() {
            if (updater.updateAvailable && !updateModal.open)
                updateModal.open = true
        }
    }

    //   窗口藏在托盘里跑完时，用户看不到状态栏 —— 必须主动提示一次，
    //   否则「最小化到托盘」等于让人干等。
    //   列表或输出目录一变，续跑状态就得重算：用户先选目录再拖文件进来是
    //   常见顺序，只在「开始」时算会让提示一直不出现。
    Connections {
        target: bridge
        function onFilesChanged() {
            bridge.checkResume(outputView.outputDir)
        }
    }

    Connections {
        target: outputView
        function onOutputDirChanged() {
            bridge.checkResume(outputView.outputDir)
            bridge.refreshSequence(outputView.outputDir, outputView.autoSequence)
        }
        function onAutoSequenceChanged() {
            bridge.refreshSequence(outputView.outputDir, outputView.autoSequence)
        }
    }

    //   「定位 SD 卡」找到的目录由 bridge 反推回来，界面只负责填进去。
    Connections {
        target: bridge
        function onLocatedChanged() {
            if (bridge.locatedDir !== "")
                outputView.outputDir = bridge.locatedDir
        }
    }

    Connections {
        target: bridge
        function onBusyChanged() {
            if (bridge.busy)
                return
            if (win.visible)
                return
            tray.notify(bridge.appName, bridge.status)
        }
    }

    FileDialog {
        id: sampleDialog
        title: bridge.tr("选择原生录制视频")
        nameFilters: [bridge.tr("视频文件 (*.mp4 *.mov *.lrv *.insv *.ins)")]
        onAccepted: bridge.setSample(bridge.localPath(selectedFile))
    }

    FileDialog {
        id: videoDialog
        title: bridge.tr("选择视频")
        nameFilters: [bridge.tr("视频文件 (*.mp4 *.mov *.mkv *.avi *.ts *.flv *.wmv *.m4v)")]
        fileMode: FileDialog.OpenFiles
        onAccepted: {
            var paths = []
            for (var i = 0; i < selectedFiles.length; ++i)
                paths.push(bridge.localPath(selectedFiles[i]))
            bridge.addFiles(paths)
        }
    }

    FolderDialog {
        id: folderDialog
        title: bridge.tr("选择包含视频的文件夹")
        onAccepted: bridge.addFolder(bridge.localPath(selectedFolder))
    }

    FolderDialog {
        id: outputDialog
        title: bridge.tr("选择输出目录")
        onAccepted: {
            outputView.outputDir = bridge.localPath(selectedFolder)
            bridge.checkResume(outputView.outputDir)
        }
    }

    FileDialog {
        id: coverDialog
        title: bridge.tr("选择封面图片")
        nameFilters: [bridge.tr("图片 (*.png *.jpg *.jpeg *.bmp *.webp)")]
        onAccepted: bridge.pickCover(bridge.localPath(selectedFile))
    }

    Rectangle {
        id: surface
        anchors.fill: parent
        radius: 12
        color: Theme.bgWindow
        border.width: 1
        border.color: Theme.divider
        clip: true

        //   拖拽添加：把视频或整个 DCIM 文件夹拖进窗口即可。
        //   经典版有拖放，QML 版此前只能靠按钮一个个点。
        DropArea {
            id: dropZone
            anchors.fill: parent
            //   必须在内容之上：拖放事件只送给最顶层的 item，压在 Column
            //   下面的话窗口里怎么拖都没反应。
            z: 20
            onEntered: function (drag) {
                if (drag.hasUrls)
                    drag.acceptProposedAction()
            }
            onDropped: function (drop) {
                var paths = []
                for (var i = 0; i < drop.urls.length; ++i)
                    paths.push(bridge.localPath(drop.urls[i]))
                bridge.addPaths(paths)
                drop.acceptProposedAction()
            }
        }

        Rectangle {
            anchors.fill: parent
            visible: dropZone.containsDrag
            radius: 12
            color: "transparent"
            border.width: 2
            border.color: Theme.accent
            z: 21
        }

        Column {
            anchors.fill: parent

            TitleBar {
                width: parent.width
                targetWindow: win
                title: bridge.appName
            }

            //  内容区自己就是 Flickable：ScrollView 把滚动交给内部
            //  Flickable，外面拿不到 contentY，也就没法做阻尼。
            Flickable {
                id: scroll
                width: parent.width
                height: parent.height - 40
                clip: true
                contentWidth: width
                contentHeight: pageColumn.height + 48
                boundsBehavior: Flickable.DragOverBounds
                ScrollBar.vertical: ScrollBar {
                    policy: ScrollBar.AsNeeded
                }

                //  拖过边界时把超出量按阻尼压回来，越推越推不动。
                contentItem.transform: Translate {
                    x: pageDamping.shiftX
                    y: pageDamping.shiftY
                }

                DragDamping {
                    id: pageDamping
                    flick: scroll
                }

                Column {
                    id: pageColumn
                    x: 24
                    y: 24
                    width: scroll.width - 48
                    spacing: 12

                    Text {
                        width: parent.width
                        text: bridge.appName
                        color: Theme.textPrimary
                        font.family: Theme.fontDisplayFamily
                        font.pixelSize: Theme.fontDisplaySize
                        font.weight: Font.DemiBold
                        lineHeightMode: Text.FixedHeight
                        lineHeight: Theme.fontDisplayLine
                    }

                    //   ffmpeg 缺失是硬阻塞：没有它一条也转不了。经典版启动就
                    //   自动下载，QML 版此前只在点「开始」时报一句，用户没处修。
                    Rectangle {
                        width: parent.width
                        visible: bridge.ffmpegMissing
                        implicitHeight: ffCol.implicitHeight + 24
                        radius: 12
                        color: Theme.card
                        border.width: 1
                        border.color: Theme.warning

                        Column {
                            id: ffCol
                            anchors.fill: parent
                            anchors.margins: 12
                            spacing: 8

                            Text {
                                width: parent.width
                                text: bridge.ffmpegDownloading
                                    ? bridge.tr("正在下载 ffmpeg… ") + Math.round(bridge.ffmpegProgress * 100) + "%"
                                    : bridge.tr("未找到 ffmpeg。它是转码必需组件，先选一个安装位置。")
                                color: Theme.textSecondary
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.fontBodySize
                                font.weight: Font.Normal
                                wrapMode: Text.Wrap
                                lineHeightMode: Text.FixedHeight
                                lineHeight: Theme.fontBodyLine
                            }

                            Text {
                                width: parent.width
                                visible: !bridge.ffmpegDownloading
                                text: bridge.tr("装到系统目录：所有程序都能用，需要管理员权限；"
                                      + "装到程序目录：只给本程序用，不需要任何权限。")
                                color: Theme.textSecondary
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.fontAuxSize
                                font.weight: Font.Normal
                                wrapMode: Text.Wrap
                                lineHeightMode: Text.FixedHeight
                                lineHeight: Theme.fontAuxLine
                            }

                            Row {
                                spacing: 8

                                AppButton {
                                    btnHeight: 32
                                    text: bridge.ffmpegDownloading ? bridge.tr("下载中…") : bridge.tr("装到系统目录")
                                    enabled: !bridge.ffmpegDownloading
                                    onClicked: bridge.installFfmpeg("global")
                                }

                                AppButton {
                                    btnHeight: 32
                                    accent: false
                                    text: bridge.ffmpegDownloading ? bridge.tr("下载中…") : bridge.tr("装到程序目录")
                                    enabled: !bridge.ffmpegDownloading
                                    onClicked: bridge.installFfmpeg("portable")
                                }
                            }
                        }
                    }

                    CameraSampleView {
                        width: parent.width
                        status: bridge.sample !== ""
                                ? bridge.tr("样本：") + bridge.sample
                                : bridge.tr("未设置样本（回退到影石默认结构）")
                        summary: bridge.specSummary
                        onPickSample: sampleDialog.open()
                        //   输出目录常就是卡根或 DCIM，先按它找，找不到再扫盘符。
                        onAutoDetect: bridge.autoDetectSample(outputView.outputDir)
                    }

                    InputFileView {
                        width: parent.width
                        files: bridge.files
                        //   这里只反映「列表本身」的状态。错误提示统一由
                        //   ActionView 显示 —— 把 lastError 接到文件区会让
                        //   一条「请先添加要转换的视频」把文件区永久染红。
                        state: bridge.busy ? "loading" : "empty"
                        onAddVideo: videoDialog.open()
                        onAddFolder: folderDialog.open()
                        onClearAll: bridge.clearFiles()
                        onRemoveFile: function (path) { bridge.removeFile(path) }
                    }

                    OutputOptionView {
                        id: outputView
                        width: parent.width
                        hardwareHint: bridge.hardwareEncoder === ""
                            ? bridge.tr("正在检测硬件编码器…")
                            : (bridge.hardwareEncoder === bridge.tr("未检测到")
                                ? bridge.tr("未检测到可用硬件编码器，将使用软件编码")
                                : bridge.tr("已检测到 ") + bridge.hardwareEncoder
                                  + bridge.tr("，可选它加快约 1.5～2 倍（默认仍用软件，与相机已验证的路径一致）"))
                        sequenceHint: bridge.nextSequence
                        coverSummary: bridge.coverSummary
                        coverImage: bridge.coverImage
                        //   机型下拉是「选中即生效」：必须双向接线，否则只有 QML
                        //   本地 property 变了，bridge 里仍是 auto，预设等于没选。
                        modelOverride: bridge.modelOverride
                        onModelOverrideSelected: function (value) {
                            bridge.setModelOverride(value)
                        }
                        onBrowseOutput: outputDialog.open()
                        onLocateCard: bridge.locateCard()
                        onPickCover: coverDialog.open()
                        onClearCovers: bridge.clearCovers()
                        onVerifyCard: bridge.verifyCard(outputView.outputDir)
                    }

                    //   续跑提示：只有真的存在「上次未完成」时才出现，
                    //   平时不占版面。
                    Rectangle {
                        width: parent.width
                        visible: bridge.resumeSummary !== ""
                        implicitHeight: resumeRow.implicitHeight + 24
                        radius: 12
                        color: Theme.card
                        border.width: 1
                        border.color: Theme.divider

                        Row {
                            id: resumeRow
                            anchors.fill: parent
                            anchors.margins: 12
                            spacing: 12

                            Text {
                                anchors.verticalCenter: parent.verticalCenter
                                //   按按钮的实际宽度反算，不写死 120：
                                //   英文的 "Only unfinished" 比中文长，
                                //   固定的 120 会让按钮自己溢出边框。
                                width: parent.width - resumeToggle.width - resumeRow.spacing
                                text: bridge.resumeSummary
                                color: Theme.textSecondary
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.fontBodySize
                                font.weight: Font.Normal
                                wrapMode: Text.Wrap
                                lineHeightMode: Text.FixedHeight
                                lineHeight: Theme.fontBodyLine
                            }

                            AppButton {
                                id: resumeToggle
                                width: Math.max(120, implicitWidth)
                                btnHeight: 32
                                text: bridge.resumeOnly ? bridge.tr("只跑未完成") : bridge.tr("全部重跑")
                                onClicked: bridge.setResumeOnly(!bridge.resumeOnly)
                            }
                        }
                    }

                    //   卡校验结果：有异常时把清单摊开，并给一键清理。
                    Rectangle {
                        width: parent.width
                        visible: bridge.verifyResult !== ""
                        implicitHeight: verifyCol.implicitHeight + 24
                        radius: 12
                        color: Theme.card
                        border.width: 1
                        border.color: bridge.verifyHasBad ? Theme.error : Theme.divider

                        Column {
                            id: verifyCol
                            anchors.fill: parent
                            anchors.margins: 12
                            spacing: 8

                            Text {
                                width: parent.width
                                text: bridge.verifyResult
                                color: bridge.verifyHasBad ? Theme.error : Theme.textSecondary
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.fontBodySize
                                font.weight: Font.Normal
                                wrapMode: Text.Wrap
                                lineHeightMode: Text.FixedHeight
                                lineHeight: Theme.fontBodyLine
                            }

                            AppButton {
                                btnHeight: 32
                                text: bridge.tr("清理异常条目")
                                visible: bridge.verifyHasBad
                                onClicked: bridge.repairCard(outputView.outputDir)
                            }
                        }
                    }

                    ProgressView {
                        width: parent.width
                        value: bridge.progress
                        eta: bridge.eta
                        status: bridge.status
                    }

                    ActionView {
                        width: parent.width
                        running: bridge.busy
                        hasError: bridge.lastError !== ""
                        errorText: bridge.lastError
                        onStart: {
                            //   先按当前目录刷一次续跑状态，start() 里还会再算一次
                            //   （目录或列表可能在两者之间变过）。
                            bridge.checkResume(outputView.outputDir)
                            bridge.start(
                                outputView.outputDir,
                                outputView.registerIndex,
                                outputView.autoSequence,
                                outputView.encoder)
                        }
                        onCancel: bridge.cancel()
                        onDismissError: bridge.clearError()
                    }
                }
            }
        }
    }

    //   转换中点 × 直接关窗的后果：进程退出 → ffmpeg 变孤儿继续往卡里写，
    //   set_awake(False) 永不执行（防休眠锁残留），卡上留半截 VID/LRV 且索引
    //   没登记。
    onClosing: function (close) {
        if (!bridge.busy) {
            close.accepted = true
            //   main.py 设了 setQuitOnLastWindowClosed(false)（否则「最小化
            //   到托盘」刚藏起窗口进程就结束了），所以空闲时关窗必须显式退出。
            Qt.quit()
            return
        }
        close.accepted = false
        closeModal.open = true
    }

    Modal {
        id: closeModal
        anchors.fill: parent
        title: bridge.tr("正在转换")
        dismissOnBackdrop: false

        Column {
            width: parent.width
            spacing: 12

            Text {
                width: parent.width
                text: bridge.tr("当前任务尚未完成。\n\n"
                    + "停止并退出：立刻中止，未完成的文件会留在输出目录，需要自行删除。\n"
                    + "最小化到托盘：窗口隐藏，转换继续跑完，跑完会弹提示。")
                wrapMode: Text.Wrap
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontBodySize
                font.weight: Font.Normal
                lineHeightMode: Text.FixedHeight
                lineHeight: Theme.fontBodyLine
            }

            Row {
                width: parent.width
                spacing: 8
                layoutDirection: Qt.RightToLeft

                AppButton {
                    text: bridge.tr("停止并退出")
                    btnHeight: 36
                    onClicked: {
                        bridge.cancel()
                        // 等 worker 把 ffmpeg 收掉再关；20 秒还没退出就再等一轮。
                        if (bridge.waitWorker(20000)) {
                            closeModal.open = false
                            Qt.quit()
                        } else {
                            closeModal.open = false
                            bridge.setStatusHint(bridge.tr("后台进程尚未退出，请稍候再关闭"))
                        }
                    }
                }

                AppButton {
                    //   托盘不可用（无桌面环境 / 某些 Linux）时不能给这个选项：
                    //   窗口一藏，用户既看不到窗口也找不到托盘图标，等于把
                    //   程序弄丢了。禁用并说明原因。
                    text: tray.available ? bridge.tr("最小化到托盘") : bridge.tr("最小化到托盘（不可用）")
                    btnHeight: 36
                    accent: false
                    enabled: tray.available
                    onClicked: {
                        closeModal.open = false
                        win.visible = false
                        tray.show()
                        tray.notify(bridge.appName,
                                    bridge.tr("转换在后台继续，完成后会再提示一次。"))
                    }
                }

                AppButton {
                    text: bridge.tr("继续转换")
                    btnHeight: 36
                    accent: false
                    onClicked: closeModal.open = false
                }
            }
        }
    }

    Modal {
        id: updateModal
        anchors.fill: parent
        title: bridge.tr("发现新版本")
        dismissOnBackdrop: false

        Column {
            width: parent.width
            spacing: 12

            Text {
                width: parent.width
                text: bridge.tr("当前版本 %1，最新版本 %2。")
                    .arg(updater.currentVersion)
                    .arg(updater.latestTag !== "" ? updater.latestTag
                        : (updateDemo ? "v1.2.0" : bridge.tr("未知")))
                wrapMode: Text.Wrap
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontBodySize
                font.weight: Font.Normal
                lineHeightMode: Text.FixedHeight
                lineHeight: Theme.fontBodyLine
            }

            Row {
                width: parent.width
                spacing: 8
                layoutDirection: Qt.RightToLeft

                AppButton {
                    text: bridge.tr("前往下载")
                    btnHeight: 36
                    onClicked: {
                        Qt.openUrlExternally(updater.releaseUrl)
                        updateModal.open = false
                    }
                }

                AppButton {
                    text: bridge.tr("稍后")
                    btnHeight: 36
                    accent: false
                    onClicked: updateModal.open = false
                }

                AppButton {
                    text: bridge.tr("关闭")
                    btnHeight: 36
                    accent: false
                    onClicked: {
                        updater.ignore(updater.latestTag)
                        updateModal.open = false
                    }
                }
            }
        }
    }

    //   showWelcome() 可以在运行期间把欢迎页叫回来（留给「关于」用），
    //   所以 open 不能绑成 bridge.welcomeNeeded 的表达式 —— 关窗时一旦
    //   open = false 就会把绑定打断，之后 showWelcome 再也叫不出来。
    Connections {
        target: bridge
        function onWelcomeChanged() {
            welcome.open = bridge.welcomeNeeded
        }
        //   浏览器确实起来了，但窗口落在全屏的主界面后面，看着像没反应。
        //   把主界面收起来，用户一眼就能看到刚打开的页面。
        function onBrowserOpened() {
            win.showMinimized()
        }
    }

    WelcomeDialog {
        id: welcome
        anchors.fill: parent
        onClosed: {
            welcome.open = false
            bridge.markWelcomeSeen()
        }
    }
}

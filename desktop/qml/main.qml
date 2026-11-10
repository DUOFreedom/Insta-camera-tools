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
    title: "影石相机工具"
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
        if (updateDemo)
            updateModal.open = true
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
    Connections {
        target: bridge
        function onBusyChanged() {
            if (bridge.busy)
                return
            if (win.visible)
                return
            tray.notify("影石相机工具", bridge.status)
        }
    }

    FileDialog {
        id: sampleDialog
        title: "选择原生录制视频"
        nameFilters: ["视频文件 (*.mp4 *.mov *.lrv *.insv *.ins)"]
        onAccepted: bridge.setSample(bridge.localPath(selectedFile))
    }

    FileDialog {
        id: videoDialog
        title: "选择视频"
        nameFilters: ["视频文件 (*.mp4 *.mov *.mkv *.avi *.ts *.flv *.wmv *.m4v)"]
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
        title: "选择包含视频的文件夹"
        onAccepted: bridge.addFolder(bridge.localPath(selectedFolder))
    }

    FolderDialog {
        id: outputDialog
        title: "选择输出目录"
        onAccepted: outputView.outputDir = bridge.localPath(selectedFolder)
    }

    Rectangle {
        id: surface
        anchors.fill: parent
        radius: 12
        color: Theme.bgWindow
        border.width: 1
        border.color: Theme.divider
        clip: true

        Column {
            anchors.fill: parent

            TitleBar {
                width: parent.width
                targetWindow: win
                title: "影石相机工具"
            }

            ScrollView {
                id: scroll
                width: parent.width
                height: parent.height - 40
                clip: true
                ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                ScrollBar.vertical.policy: ScrollBar.AsNeeded

                Column {
                    x: 24
                    y: 24
                    width: scroll.availableWidth - 48
                    spacing: 12

                    Text {
                        width: parent.width
                        text: "影石相机工具"
                        color: Theme.textPrimary
                        font.family: Theme.fontDisplayFamily
                        font.pixelSize: Theme.fontDisplaySize
                        font.weight: Font.DemiBold
                        lineHeightMode: Text.FixedHeight
                        lineHeight: Theme.fontDisplayLine
                    }

                    CameraSampleView {
                        width: parent.width
                        status: bridge.sample !== ""
                                ? "样本：" + bridge.sample
                                : "未设置样本（回退到影石默认结构）"
                        onPickSample: sampleDialog.open()
                        //   输出目录常就是卡根或 DCIM，先按它找，找不到再扫盘符。
                        onAutoDetect: bridge.autoDetectSample(outputView.outputDir)
                    }

                    InputFileView {
                        width: parent.width
                        files: bridge.files
                        state: bridge.lastError !== "" ? "error" : (bridge.busy ? "loading" : "empty")
                        errorText: bridge.lastError
                        onAddVideo: videoDialog.open()
                        onAddFolder: folderDialog.open()
                        onClearAll: bridge.clearFiles()
                    }

                    OutputOptionView {
                        id: outputView
                        width: parent.width
                        onBrowseOutput: outputDialog.open()
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
                        onStart: bridge.start(
                            outputView.outputDir,
                            outputView.registerIndex,
                            outputView.autoSequence,
                            outputView.encoder)
                        onCancel: bridge.cancel()
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
        title: "正在转换"
        dismissOnBackdrop: false

        Column {
            width: parent.width
            spacing: 12

            Text {
                width: parent.width
                text: "当前任务尚未完成。

"
                    + "停止并退出：立刻中止，未完成的文件会留在输出目录，需要自行删除。
"
                    + "最小化到托盘：窗口隐藏，转换继续跑完，跑完会弹提示。"
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
                    text: "停止并退出"
                    btnHeight: 36
                    onClicked: {
                        bridge.cancel()
                        // 等 worker 把 ffmpeg 收掉再关；20 秒还没退出就再等一轮。
                        if (bridge.waitWorker(20000)) {
                            closeModal.open = false
                            Qt.quit()
                        } else {
                            closeModal.open = false
                            bridge.setStatusHint("后台进程尚未退出，请稍候再关闭")
                        }
                    }
                }

                AppButton {
                    //   托盘不可用（无桌面环境 / 某些 Linux）时不能给这个选项：
                    //   窗口一藏，用户既看不到窗口也找不到托盘图标，等于把
                    //   程序弄丢了。禁用并说明原因。
                    text: tray.available ? "最小化到托盘" : "最小化到托盘（不可用）"
                    btnHeight: 36
                    accent: false
                    enabled: tray.available
                    onClicked: {
                        closeModal.open = false
                        win.visible = false
                        tray.show()
                        tray.notify("影石相机工具",
                                    "转换在后台继续，完成后会再提示一次。")
                    }
                }

                AppButton {
                    text: "继续转换"
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
        title: "发现新版本"
        dismissOnBackdrop: false

        Column {
            width: parent.width
            spacing: 12

            Text {
                width: parent.width
                text: "当前版本 " + updater.currentVersion
                    + "，最新版本 " + (updater.latestTag !== "" ? updater.latestTag
                        : (updateDemo ? "v1.2.0" : "未知")) + "。"
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
                    text: "前往下载"
                    btnHeight: 36
                    onClicked: {
                        Qt.openUrlExternally(updater.releaseUrl)
                        updateModal.open = false
                    }
                }

                AppButton {
                    text: "稍后"
                    btnHeight: 36
                    accent: false
                    onClicked: updateModal.open = false
                }

                AppButton {
                    text: "关闭"
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
}

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
                        onAutoDetect: bridge.setStatusHint("请手动选择卡内的 VID_*.mp4 作为样本")
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
    //   没登记。经典版 gui.py 的 closeEvent 早就拦过这条路，QML 版此前没有。
    onClosing: function (close) {
        if (!bridge.busy) {
            close.accepted = true
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
                text: "当前任务尚未完成。停止转换并退出？
"
                    + "未完成的文件会留在输出目录，需要自行删除。"
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

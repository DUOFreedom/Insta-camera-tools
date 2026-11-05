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

    Component.onCompleted: Theme.dark = systemDark

    FileDialog {
        id: sampleDialog
        title: "选择原生录制视频"
        nameFilters: ["视频文件 (*.mp4 *.mov *.lrv *.insv *.ins)"]
        onAccepted: bridge.setSample(selectedFile.toString().replace("file:///", ""))
    }

    FileDialog {
        id: videoDialog
        title: "选择视频"
        nameFilters: ["视频文件 (*.mp4 *.mov *.mkv *.avi *.ts *.flv *.wmv *.m4v)"]
        fileMode: FileDialog.OpenFiles
        onAccepted: {
            var paths = []
            for (var i = 0; i < selectedFiles.length; ++i)
                paths.push(selectedFiles[i].toString().replace("file:///", ""))
            bridge.addFiles(paths)
        }
    }

    FolderDialog {
        id: folderDialog
        title: "选择包含视频的文件夹"
        onAccepted: bridge.addFolder(selectedFolder.toString().replace("file:///", ""))
    }

    FolderDialog {
        id: outputDialog
        title: "选择输出目录"
        onAccepted: outputView.outputDir = selectedFolder.toString().replace("file:///", "")
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
}

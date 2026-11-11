import QtQuick

Rectangle {
    id: root
    property string state: "empty"
    property string errorText: bridge.tr("无法访问所选文件，请检查路径是否存在。")
    property var files: []

    signal addVideo()
    signal addFolder()
    signal clearAll()
    signal removeFile(string path)

    radius: 12
    color: Theme.card
    border.width: 1
    border.color: Theme.divider
    implicitHeight: content.implicitHeight + 32

    Column {
        id: content
        anchors.fill: parent
        anchors.margins: 16
        spacing: 12

        Row {
            width: parent.width

            Text {
                text: bridge.tr("待转换视频")
                color: Theme.textPrimary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontTitleSize
                font.weight: Font.DemiBold
                lineHeightMode: Text.FixedHeight
                lineHeight: Theme.fontTitleLine
            }

            Item {
                width: Math.max(0, parent.width - 120)
                height: 1
            }

            Text {
                anchors.verticalCenter: parent.verticalCenter
                visible: root.files.length > 0
                text: root.files.length + bridge.tr(" 个")
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontAuxSize
                font.weight: Font.Normal
            }
        }

        ListView {
            id: fileList
            width: parent.width
            height: Math.min(contentHeight, 168)
            visible: root.files.length > 0
            clip: true
            model: root.files
            spacing: 4
            boundsBehavior: Flickable.StopAtBounds

            delegate: Rectangle {
                width: fileList.width
                height: 32
                radius: 8
                color: hover.containsMouse ? Theme.divider : "transparent"

                Text {
                    anchors.left: parent.left
                    anchors.leftMargin: 8
                    anchors.right: parent.right
                    anchors.rightMargin: 32
                    anchors.verticalCenter: parent.verticalCenter
                    text: modelData
                    elide: Text.ElideMiddle
                    color: Theme.textPrimary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontBodySize
                    font.weight: Font.Normal
                }

                MouseArea {
                    id: hover
                    anchors.fill: parent
                    hoverEnabled: true
                }

                //   单个移除：加错一个文件时不用整表清空重来。
                Rectangle {
                    id: removeBtn
                    anchors.right: parent.right
                    anchors.rightMargin: 4
                    anchors.verticalCenter: parent.verticalCenter
                    width: 24
                    height: 24
                    radius: 12
                    visible: hover.containsMouse
                    color: removeArea.containsMouse ? Theme.divider : "transparent"

                    AppIcon {
                        anchors.centerIn: parent
                        name: "close"
                        size: 12
                        color: Theme.textSecondary
                    }

                    MouseArea {
                        id: removeArea
                        anchors.fill: parent
                        hoverEnabled: true
                        onClicked: root.removeFile(modelData)
                    }
                }
            }
        }

        Item {
            width: parent.width
            height: root.files.length > 0 ? 0 : stateArea.implicitHeight + 32
            visible: root.files.length === 0

            Column {
                id: stateArea
                anchors.centerIn: parent
                spacing: 12

                AppIcon {
                    anchors.horizontalCenter: parent.horizontalCenter
                    visible: root.state !== "loading"
                    name: root.state === "error" ? "warning" : "info"
                    size: 24
                    color: root.state === "error" ? Theme.error : Theme.textSecondary
                }

                Rectangle {
                    anchors.horizontalCenter: parent.horizontalCenter
                    visible: root.state === "loading"
                    width: 24
                    height: 24
                    radius: 12
                    color: "transparent"
                    border.width: 2
                    border.color: Theme.accent
                    opacity: 0.6
                }

                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    horizontalAlignment: Text.AlignHCenter
                    text: root.state === "empty" ? bridge.tr("暂无待转换视频")
                        : root.state === "loading" ? bridge.tr("正在读取…")
                        : bridge.tr("出错了")
                    color: root.state === "error" ? Theme.error : Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontBodySize
                    font.weight: Font.Normal
                    lineHeightMode: Text.FixedHeight
                    lineHeight: Theme.fontBodyLine
                }

                Text {
                    anchors.horizontalCenter: parent.horizontalCenter
                    visible: root.state === "error"
                    width: 280
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.Wrap
                    text: root.errorText
                    color: Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontAuxSize
                    font.weight: Font.Normal
                    lineHeightMode: Text.FixedHeight
                    lineHeight: Theme.fontAuxLine
                }

                AppButton {
                    anchors.horizontalCenter: parent.horizontalCenter
                    visible: root.state !== "loading"
                    text: root.state === "error" ? bridge.tr("重试") : bridge.tr("添加视频")
                    btnHeight: 28
                    accent: root.state !== "error"
                    onClicked: root.addVideo()
                }
            }
        }

        Row {
            spacing: 8

            AppButton {
                text: bridge.tr("添加视频")
                btnHeight: 36
                accent: true
                onClicked: root.addVideo()
            }

            AppButton {
                text: bridge.tr("添加文件夹")
                btnHeight: 36
                accent: false
                onClicked: root.addFolder()
            }

            AppButton {
                text: bridge.tr("清空")
                btnHeight: 36
                accent: false
                visible: root.files.length > 0
                onClicked: root.clearAll()
            }
        }
    }
}

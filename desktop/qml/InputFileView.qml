import QtQuick

Rectangle {
    id: root
    property string state: "empty"
    property string errorText: "无法访问所选文件，请检查路径是否存在。"

    signal addVideo()
    signal addFolder()

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

        Text {
            width: parent.width
            text: "待转换视频"
            color: Theme.textPrimary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontTitleSize
            font.weight: Font.DemiBold
            lineHeightMode: Text.FixedHeight
            lineHeight: Theme.fontTitleLine
        }

        Item {
            width: parent.width
            height: stateArea.implicitHeight + 32

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
                    text: root.state === "empty" ? "暂无待转换视频"
                        : root.state === "loading" ? "正在读取…"
                        : "读取失败"
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
                    text: root.errorText
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.Wrap
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
                    text: root.state === "error" ? "重试" : "添加视频"
                    btnHeight: 28
                    accent: root.state !== "error"
                    onClicked: root.addVideo()
                }
            }
        }

        Row {
            spacing: 8

            AppButton {
                text: "添加视频"
                btnHeight: 36
                accent: true
                onClicked: root.addVideo()
            }

            AppButton {
                text: "添加文件夹"
                btnHeight: 36
                accent: false
                onClicked: root.addFolder()
            }
        }
    }
}

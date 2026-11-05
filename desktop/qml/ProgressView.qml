import QtQuick

Rectangle {
    id: root
    property real value: 0
    property string eta: "剩余 --:--"
    property string status: "就绪。添加视频后点击「开始转换」。"

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
            text: "进度"
            color: Theme.textPrimary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontTitleSize
            font.weight: Font.DemiBold
            lineHeightMode: Text.FixedHeight
            lineHeight: Theme.fontTitleLine
        }

        Row {
            width: parent.width
            spacing: 12

            Rectangle {
                width: parent.width - etaLabel.width - 12
                height: 8
                radius: 4
                color: Theme.divider
                anchors.verticalCenter: parent.verticalCenter

                Rectangle {
                    width: parent.width * Math.max(0, Math.min(1, root.value))
                    height: parent.height
                    radius: 4
                    color: Theme.accent
                }
            }

            Text {
                id: etaLabel
                anchors.verticalCenter: parent.verticalCenter
                text: root.eta
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontAuxSize
                font.weight: Font.Normal
                lineHeightMode: Text.FixedHeight
                lineHeight: Theme.fontAuxLine
            }
        }

        Text {
            width: parent.width
            text: root.status
            color: Theme.textSecondary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontAuxSize
            font.weight: Font.Normal
            lineHeightMode: Text.FixedHeight
            lineHeight: Theme.fontAuxLine
            wrapMode: Text.Wrap
        }
    }
}

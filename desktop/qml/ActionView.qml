import QtQuick

Rectangle {
    id: root
    property bool running: false
    property bool hasError: false
    property string errorText: bridge.tr("转换失败：无法访问输出目录，请检查路径权限。")

    signal start()
    signal cancel()
    signal dismissError()

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
            text: bridge.tr("操作")
            color: Theme.textPrimary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontTitleSize
            font.weight: Font.DemiBold
            lineHeightMode: Text.FixedHeight
            lineHeight: Theme.fontTitleLine
        }

        Row {
            width: parent.width
            layoutDirection: Qt.RightToLeft

            AppButton {
                text: root.running ? bridge.tr("取消转换") : bridge.tr("开始转换")
                btnHeight: 36
                accent: !root.running
                onClicked: root.running ? root.cancel() : root.start()
            }
        }

        Row {
            width: parent.width
            visible: root.hasError && !root.running
            spacing: 8

            Text {
                width: parent.width - 72
                anchors.verticalCenter: parent.verticalCenter
                text: root.errorText
                color: Theme.error
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontAuxSize
                font.weight: Font.Normal
                lineHeightMode: Text.FixedHeight
                lineHeight: Theme.fontAuxLine
                wrapMode: Text.Wrap
            }

            AppButton {
                text: bridge.tr("知道了")
                btnHeight: 28
                accent: false
                onClicked: root.dismissError()
            }
        }
    }
}

import QtQuick

Rectangle {
    id: root
    property bool running: false
    property bool hasError: false
    property string errorText: "转换失败：无法访问输出目录，请检查路径权限。"

    signal start()
    signal cancel()

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
            text: "操作"
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
                text: root.running ? "取消转换" : "开始转换"
                btnHeight: 36
                accent: !root.running
                onClicked: root.running ? root.cancel() : root.start()
            }
        }

        Text {
            width: parent.width
            visible: root.hasError && !root.running
            text: root.errorText
            color: Theme.error
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontAuxSize
            font.weight: Font.Normal
            lineHeightMode: Text.FixedHeight
            lineHeight: Theme.fontAuxLine
            wrapMode: Text.Wrap
        }
    }
}

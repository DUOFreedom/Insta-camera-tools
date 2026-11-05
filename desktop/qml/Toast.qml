import QtQuick

Item {
    id: root
    property string text: ""
    property string kind: "info"
    property bool open: false

    readonly property color tone: kind === "success" ? Theme.success
                                : kind === "warning" ? Theme.warning
                                : kind === "error" ? Theme.error
                                : Theme.info

    visible: bubble.opacity > 0
    z: 96
    implicitWidth: label.implicitWidth + 32
    implicitHeight: label.implicitHeight + 16

    Rectangle {
        id: bubble
        anchors.fill: parent
        radius: 12
        color: Theme.popover
        border.width: 1
        border.color: Theme.divider
        opacity: root.open ? 1 : 0

        Behavior on opacity {
            NumberAnimation {
                duration: root.open ? Theme.durMedium : Theme.durFast
                easing.type: Easing.Bezier
                easing.bezierCurve: Theme.easeBezier
            }
        }
    }

    Rectangle {
        id: bar
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        width: 3
        radius: 12
        color: root.tone
    }

    Text {
        id: label
        anchors.centerIn: parent
        text: root.text
        color: Theme.textPrimary
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontBodySize
        font.weight: Font.Normal
    }

    Timer {
        interval: 3000
        running: root.open
        onTriggered: root.open = false
    }
}

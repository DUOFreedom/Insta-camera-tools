import QtQuick

Item {
    id: root
    property string text: ""
    property bool open: false

    visible: bubble.opacity > 0
    z: 95
    implicitWidth: label.implicitWidth + 16
    implicitHeight: label.implicitHeight + 8

    Rectangle {
        id: bubble
        anchors.fill: parent
        radius: 12
        color: Theme.popover
        border.width: 1
        border.color: Theme.divider
        opacity: root.open ? 1 : 0
        y: root.open ? 0 : 4

        Behavior on opacity {
            NumberAnimation {
                duration: root.open ? Theme.durMedium : Theme.durFast
                easing.type: Easing.Bezier
                easing.bezierCurve: Theme.easeBezier
            }
        }

        Behavior on y {
            NumberAnimation {
                duration: root.open ? Theme.durMedium : Theme.durFast
                easing.type: Easing.Bezier
                easing.bezierCurve: Theme.easeBezier
            }
        }
    }

    Text {
        id: label
        anchors.centerIn: parent
        text: root.text
        color: Theme.textPrimary
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontAuxSize
        font.weight: Font.Normal
        lineHeightMode: Text.FixedHeight
        lineHeight: Theme.fontAuxLine
    }
}

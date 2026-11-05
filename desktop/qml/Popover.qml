import QtQuick

Item {
    id: root
    property bool open: false
    property int radius: 12
    default property alias content: body.data

    visible: panel.opacity > 0
    z: 90
    implicitWidth: 200
    implicitHeight: body.childrenRect.height + 16

    Rectangle {
        id: panel
        anchors.fill: parent
        radius: root.radius
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

    Column {
        id: body
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: 8
        spacing: 4
    }
}

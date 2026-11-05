import QtQuick

Item {
    id: root
    property bool open: false
    property string title: ""
    default property alias content: body.data

    visible: overlay.opacity > 0
    anchors.fill: parent
    z: 100

    Rectangle {
        id: overlay
        anchors.fill: parent
        color: "#000000"
        opacity: root.open ? 0.4 : 0

        Behavior on opacity {
            NumberAnimation {
                duration: root.open ? Theme.durMedium : Theme.durFast
                easing.type: Easing.Bezier
                easing.bezierCurve: Theme.easeBezier
            }
        }
    }

    Rectangle {
        id: panel
        anchors.centerIn: parent
        width: 320
        height: body.implicitHeight + 32
        radius: 16
        color: Theme.card
        border.width: 1
        border.color: Theme.divider
        opacity: root.open ? 1 : 0
        scale: root.open ? 1 : 0.96

        Behavior on opacity {
            NumberAnimation {
                duration: root.open ? Theme.durDialog : Theme.durFast
                easing.type: Easing.Bezier
                easing.bezierCurve: Theme.easeBezier
            }
        }

        Behavior on scale {
            NumberAnimation {
                duration: root.open ? Theme.durDialog : Theme.durFast
                easing.type: Easing.Bezier
                easing.bezierCurve: Theme.easeBezier
            }
        }

        Column {
            id: body
            anchors.fill: parent
            anchors.margins: 16
            spacing: 12

            Text {
                width: parent.width
                visible: root.title !== ""
                text: root.title
                color: Theme.textPrimary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontTitleSize
                font.weight: Font.DemiBold
                lineHeightMode: Text.FixedHeight
                lineHeight: Theme.fontTitleLine
                elide: Text.ElideRight
            }
        }
    }

    MouseArea {
        anchors.fill: parent
        enabled: root.open
        onClicked: root.open = false
    }
}

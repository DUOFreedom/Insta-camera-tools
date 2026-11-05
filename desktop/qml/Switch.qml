import QtQuick

Item {
    id: root
    property bool checked: false
    property string label: ""

    signal toggled()

    implicitWidth: track.width + (label !== "" ? 8 + labelText.implicitWidth : 0)
    implicitHeight: 20
    activeFocusOnTab: true

    Rectangle {
        id: track
        width: 32
        height: 20
        radius: 10
        color: root.checked ? Theme.accent
             : mouse.containsMouse ? Theme.divider
             : Theme.divider
        opacity: root.enabled ? 1 : 0.5

        Behavior on color {
            ColorAnimation {
                duration: Theme.durFast
                easing.type: Easing.Bezier
                easing.bezierCurve: Theme.easeBezier
            }
        }
    }

    Rectangle {
        id: thumb
        width: 16
        height: 16
        radius: 8
        color: "#FFFFFF"
        anchors.verticalCenter: track.verticalCenter
        x: 2
        transform: Translate {
            x: root.checked ? 12 : 0
            Behavior on x {
                NumberAnimation {
                    duration: Theme.durFast
                    easing.type: Easing.Bezier
                    easing.bezierCurve: Theme.easeBezier
                }
            }
        }
    }

    Rectangle {
        id: focusRing
        anchors.fill: track
        anchors.margins: -2
        radius: 12
        color: "transparent"
        border.width: 2
        border.color: Theme.accent
        visible: root.activeFocus
    }

    Text {
        id: labelText
        anchors.left: track.right
        anchors.leftMargin: 8
        anchors.verticalCenter: track.verticalCenter
        visible: root.label !== ""
        text: root.label
        color: Theme.textPrimary
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontBodySize
        font.weight: Font.Normal
    }

    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        enabled: root.enabled
        onClicked: {
            root.checked = !root.checked
            root.toggled()
        }
    }

    Keys.onSpacePressed: {
        root.checked = !root.checked
        root.toggled()
    }
}

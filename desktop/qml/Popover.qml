import QtQuick
import QtQuick.Controls.Basic

Popup {
    id: root
    property int radius: 12
    property bool open: false
    default property alias content: body.data

    width: Math.max(120, body.implicitWidth + padding * 2)
    height: body.implicitHeight + padding * 2
    padding: 8
    modal: false
    focus: false
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
    visible: open
    onClosed: root.open = false

    background: Rectangle {
        radius: root.radius
        color: Theme.popover
        border.width: 1
        border.color: Theme.divider
    }

    contentItem: Item {
        implicitWidth: body.implicitWidth
        implicitHeight: body.implicitHeight

        transform: Translate {
            y: root.opened ? 0 : 4
            Behavior on y {
                NumberAnimation {
                    duration: root.opened ? Theme.durMedium : Theme.durFast
                    easing.type: Easing.Bezier
                    easing.bezierCurve: Theme.easeBezier
                }
            }
        }

        Column {
            id: body
            width: parent.width
            spacing: 4
        }
    }

    enter: Transition {
        NumberAnimation {
            property: "opacity"
            from: 0
            to: 1
            duration: Theme.durMedium
            easing.type: Easing.Bezier
            easing.bezierCurve: Theme.easeBezier
        }
    }

    exit: Transition {
        NumberAnimation {
            property: "opacity"
            from: 1
            to: 0
            duration: Theme.durFast
            easing.type: Easing.Bezier
            easing.bezierCurve: Theme.easeBezier
        }
    }
}

import QtQuick

Item {
    id: root
    property string iconName: ""
    property int iconSize: 20

    signal clicked()

    readonly property int btnSize: 28

    implicitWidth: btnSize
    implicitHeight: btnSize
    activeFocusOnTab: true
    scale: mouse.pressed ? 0.97 : 1

    Behavior on scale {
        NumberAnimation {
            duration: Theme.durFast
            easing.type: Easing.Bezier
            easing.bezierCurve: Theme.easeBezier
        }
    }

    Rectangle {
        id: bg
        anchors.fill: parent
        radius: btnSize / 2
        color: mouse.pressed ? Theme.accentPress
             : mouse.containsMouse ? Theme.accentHover
             : "transparent"

        Behavior on color {
            ColorAnimation {
                duration: Theme.durFast
                easing.type: Easing.Bezier
                easing.bezierCurve: Theme.easeBezier
            }
        }
    }

    Rectangle {
        id: focusRing
        anchors.fill: parent
        anchors.margins: -2
        radius: (btnSize + 4) / 2
        color: "transparent"
        border.width: 2
        border.color: Theme.accent
        visible: root.activeFocus
    }

    AppIcon {
        anchors.centerIn: parent
        name: root.iconName
        size: root.iconSize
        color: root.enabled ? Theme.iconPrimary : Theme.textDisabled
    }

    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        enabled: root.enabled
        onClicked: root.clicked()
    }

    Keys.onReturnPressed: if (root.enabled) root.clicked()
    Keys.onEnterPressed: if (root.enabled) root.clicked()
}

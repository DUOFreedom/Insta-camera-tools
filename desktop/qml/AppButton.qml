import QtQuick

Item {
    id: root
    property string text: ""
    property bool loading: false
    property bool hasError: false
    property bool accent: true
    property int btnHeight: 36

    signal clicked()

    implicitWidth: Math.max(64, label.implicitWidth + 32)
    implicitHeight: btnHeight
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
        radius: root.btnHeight === 28 ? 8 : 10
        color: !root.enabled ? Theme.divider
             : mouse.pressed ? Theme.accentPress
             : mouse.containsMouse ? Theme.accentHover
             : root.accent ? Theme.accent : "transparent"
        border.width: root.accent ? 0 : 1
        border.color: root.hasError ? Theme.error : Theme.divider

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
        radius: bg.radius + 2
        color: "transparent"
        border.width: 2
        border.color: Theme.accent
        visible: root.activeFocus
    }

    Text {
        id: label
        anchors.centerIn: parent
        text: root.loading ? "..." : root.text
        color: !root.enabled ? Theme.textDisabled
             : root.accent ? "#FFFFFF"
             : Theme.textPrimary
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontBodySize
        font.weight: Font.Normal

        SequentialAnimation on opacity {
            running: root.loading && !Theme.reducedMotion
            loops: Animation.Infinite
            NumberAnimation { to: 0.3; duration: Theme.durFast }
            NumberAnimation { to: 1.0; duration: Theme.durFast }
        }
    }

    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        enabled: root.enabled && !root.loading
        onClicked: root.clicked()
    }

    Keys.onReturnPressed: if (root.enabled && !root.loading) root.clicked()
    Keys.onEnterPressed: if (root.enabled && !root.loading) root.clicked()
}

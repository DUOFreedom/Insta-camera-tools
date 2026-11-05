import QtQuick

Item {
    id: root
    property string iconName: ""
    property string label: ""
    property bool selected: false
    property bool collapsed: false

    signal clicked()

    readonly property int itemHeight: 36

    implicitWidth: 196
    implicitHeight: itemHeight

    Rectangle {
        id: bg
        anchors.fill: parent
        radius: 8
        color: root.selected ? Theme.accent
             : mouse.containsMouse ? Theme.divider
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
        radius: 10
        color: "transparent"
        border.width: 2
        border.color: Theme.accent
        visible: root.activeFocus
    }

    AppIcon {
        id: icon
        anchors.left: parent.left
        anchors.leftMargin: 8
        anchors.verticalCenter: parent.verticalCenter
        name: root.iconName
        size: 20
        color: root.selected ? "#FFFFFF" : Theme.iconSecondary
    }

    Text {
        id: text
        anchors.left: icon.right
        anchors.leftMargin: 8
        anchors.right: parent.right
        anchors.rightMargin: 8
        anchors.verticalCenter: parent.verticalCenter
        text: root.label
        visible: !root.collapsed
        opacity: root.collapsed ? 0 : 1
        color: root.selected ? "#FFFFFF" : Theme.textPrimary
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontBodySize
        font.weight: Font.Normal
        elide: Text.ElideRight
        clip: true

        Behavior on opacity {
            NumberAnimation {
                duration: Theme.durFast
                easing.type: Easing.Bezier
                easing.bezierCurve: Theme.easeBezier
            }
        }
    }

    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        enabled: root.enabled
        onClicked: root.clicked()
    }

    activeFocusOnTab: true
    Keys.onReturnPressed: if (root.enabled) root.clicked()
    Keys.onEnterPressed: if (root.enabled) root.clicked()
}

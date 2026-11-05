import QtQuick

Item {
    id: root
    property bool collapsed: false
    property int currentIndex: 0

    signal navigate(int index)

    readonly property int widthExpanded: 220
    readonly property int widthCollapsed: 64
    readonly property int radius: 12
    readonly property int padding: 12

    implicitWidth: collapsed ? widthCollapsed : widthExpanded
    implicitHeight: 480

    Behavior on implicitWidth {
        NumberAnimation {
            duration: Theme.durPanel
            easing.type: Easing.Bezier
            easing.bezierCurve: Theme.easeBezier
        }
    }

    Rectangle {
        id: bg
        anchors.fill: parent
        radius: root.radius
        color: Theme.sidebar
        border.width: 1
        border.color: Theme.sidebarBorder
    }

    Column {
        id: content
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: root.padding
        spacing: 8

        Repeater {
            model: [
                { icon: "sidebar-toggle", label: "相机样本" },
                { icon: "search", label: "导入文件" },
                { icon: "settings", label: "输出选项" },
                { icon: "info", label: "进度" }
            ]

            delegate: ListItem {
                width: parent.width
                collapsed: root.collapsed
                iconName: modelData.icon
                label: modelData.label
                selected: index === root.currentIndex
                onClicked: {
                    root.currentIndex = index
                    root.navigate(index)
                }
            }
        }
    }
}

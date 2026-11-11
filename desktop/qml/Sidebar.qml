import QtQuick

Item {
    id: root
    property bool collapsed: false
    property int currentIndex: 0

    //   保留但禁用：主界面暂无导航功能，这个组件也没被任何地方实例化
    //   （留着备用）。信号声明保留，发射点停掉。
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
                { icon: "sidebar-toggle", label: bridge.tr("相机样本") },
                { icon: "search", label: bridge.tr("导入文件") },
                { icon: "settings", label: bridge.tr("输出选项") },
                { icon: "info", label: bridge.tr("进度") }
            ]

            delegate: ListItem {
                width: parent.width
                collapsed: root.collapsed
                iconName: modelData.icon
                label: modelData.label
                selected: index === root.currentIndex
                onClicked: {
                    root.currentIndex = index
                    // root.navigate(index)  // 见上方「保留但禁用」
                }
            }
        }
    }
}

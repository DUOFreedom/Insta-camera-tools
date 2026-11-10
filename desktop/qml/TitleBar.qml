import QtQuick

Rectangle {
    id: root
    property var targetWindow: null
    property string title: ""
    property bool showThemeToggle: true

    //   保留但禁用：主题切换直接改 Theme.dark 就够了，主窗口不需要再被
    //   通知一次。信号声明保留备用，发射点停掉。
    signal themeToggleRequested()

    height: 40
    color: "transparent"

    MouseArea {
        anchors.fill: parent
        acceptedButtons: Qt.LeftButton
        onPressed: {
            if (root.targetWindow)
                root.targetWindow.startSystemMove()
        }
        onDoubleClicked: {
            if (!root.targetWindow)
                return
            if (root.targetWindow.visibility === Window.Maximized)
                root.targetWindow.showNormal()
            else
                root.targetWindow.showMaximized()
        }
    }

    Text {
        anchors.left: parent.left
        anchors.leftMargin: 16
        anchors.verticalCenter: parent.verticalCenter
        text: root.title
        color: Theme.textSecondary
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontAuxSize
        font.weight: Font.Normal
        lineHeightMode: Text.FixedHeight
        lineHeight: Theme.fontAuxLine
    }

    Row {
        anchors.right: parent.right
        anchors.rightMargin: 8
        anchors.verticalCenter: parent.verticalCenter
        spacing: 8

        IconButton {
            visible: root.showThemeToggle
            iconName: "theme-toggle"
            onClicked: {
                Theme.dark = !Theme.dark
                // root.themeToggleRequested()  // 见上方「保留但禁用」
            }
        }

        IconButton {
            iconName: "close"
            onClicked: if (root.targetWindow) root.targetWindow.close()
        }
    }
}

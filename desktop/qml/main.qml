import QtQuick
import QtQuick.Window
import QtQuick.Controls.Basic

Window {
    id: win

    width: 1024
    height: 720
    minimumWidth: 720
    minimumHeight: 480
    visible: !selfTest
    title: "影石相机工具"
    flags: Qt.Window | Qt.FramelessWindowHint
    color: "transparent"

    property bool sidebarCollapsed: width < 900
    property string statusText: "就绪。添加视频后点击「开始转换」。"
    property real progressValue: 0

    Component.onCompleted: Theme.dark = systemDark

    Rectangle {
        id: surface
        anchors.fill: parent
        radius: 12
        color: Theme.bgWindow
        border.width: 1
        border.color: Theme.divider
        clip: true

        Column {
            anchors.fill: parent

            TitleBar {
                width: parent.width
                targetWindow: win
                title: "影石相机工具"
            }

            Row {
                width: parent.width
                height: parent.height - 40
                spacing: 12

                Sidebar {
                    id: sidebar
                    height: parent.height
                    collapsed: win.sidebarCollapsed
                    currentIndex: 0
                }

                ScrollView {
                    id: scroll
                    width: parent.width - sidebar.width - 12
                    height: parent.height
                    clip: true
                    ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                    ScrollBar.vertical.policy: ScrollBar.AsNeeded

                    Column {
                        x: 24
                        y: 24
                        width: scroll.availableWidth - 48
                        spacing: 12

                        CameraSampleView {
                            width: parent.width
                            status: "未设置样本（回退到影石默认结构）"
                        }

                        InputFileView {
                            width: parent.width
                            state: "empty"
                        }

                        OutputOptionView {
                            width: parent.width
                        }

                        ProgressView {
                            width: parent.width
                            value: win.progressValue
                            status: win.statusText
                        }

                        ActionView {
                            width: parent.width
                            onStart: {
                                win.statusText = "正在转换…"
                                win.progressValue = 0.35
                            }
                        }
                    }
                }
            }
        }
    }
}

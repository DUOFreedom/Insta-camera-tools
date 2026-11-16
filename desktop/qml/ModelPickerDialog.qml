import QtQuick
import QtQuick.Layouts

// 机型二级界面：点「机型」按钮弹出的卡片式选择器。
// 与安卓首页那张机型区同构：左设备正面照、右机型名与规格，整卡可点，
// 选中卡用浅蓝底 + 强调色描边 + 右侧勾选区分。
// 不复用 Modal.qml —— 它的面板固定 360 宽，放不下横排的设备照与规格两行。
Item {
    id: root
    z: 210
    visible: open
    property bool open: false
    signal selected(string value)
    signal closed()

    readonly property var codes: ["ace_pro_2", "ace_pro", "go_ultra"]
    readonly property var labels: ["Ace Pro 2", "Ace Pro", "GO Ultra"]
    readonly property var details: [
        bridge.tr("1080p60 · 双音轨 · LRV 用 H.264"),
        bridge.tr("1080p60 · 双音轨 · LRV 用 H.264"),
        bridge.tr("1080p60 · 单音轨 · LRV 用 H.265")
    ]
    readonly property var images: [
        "../assets/models/ace_pro_2.png",
        "../assets/models/ace_pro.png",
        "../assets/models/go_ultra.png"
    ]

    function close() {
        if (!open) {
            return
        }
        open = false
        root.closed()
    }

    function choose(value) {
        if (!open) {
            return
        }
        open = false
        root.selected(value)
    }

    Rectangle {
        anchors.fill: parent
        color: "#000000"
        opacity: root.open ? 0.45 : 0

        Behavior on opacity {
            NumberAnimation {
                duration: root.open ? Theme.durMedium : Theme.durFast
                easing.type: Easing.Bezier
                easing.bezierCurve: Theme.easeBezier
            }
        }
    }

    // 吃掉点击：不然底下的输出选项、按钮还能被点到。
    MouseArea {
        anchors.fill: parent
        enabled: root.open
        cursorShape: Qt.PointingHandCursor
        onClicked: root.close()
    }

    Rectangle {
        id: panel
        anchors.centerIn: parent
        width: Math.min(420, parent.width - 48)
        height: body.implicitHeight + 48
        radius: 16
        color: Theme.card
        border.width: 1
        border.color: Theme.divider
        opacity: root.open ? 1 : 0
        scale: root.open ? 1 : 0.96
        focus: root.open

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

        Keys.onEscapePressed: root.close()

        ColumnLayout {
            id: body
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.leftMargin: 24
            anchors.rightMargin: 24
            anchors.topMargin: 22
            spacing: 0

            Text {
                Layout.fillWidth: true
                text: bridge.tr("机型")
                color: Theme.textPrimary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontTitleSize
                font.weight: Font.DemiBold
                lineHeightMode: Text.FixedHeight
                lineHeight: Theme.fontTitleLine
                elide: Text.ElideRight
            }

            Text {
                Layout.fillWidth: true
                Layout.topMargin: 4
                text: bridge.tr("选定机型后按该机型的预设参数生成。")
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontAuxSize
                font.weight: Font.Normal
                lineHeightMode: Text.FixedHeight
                lineHeight: Theme.fontAuxLine
                wrapMode: Text.WordWrap
            }

            Repeater {
                model: root.codes

                delegate: Rectangle {
                    id: card
                    Layout.fillWidth: true
                    Layout.topMargin: index === 0 ? 16 : 12
                    implicitHeight: 68
                    radius: 12
                    readonly property bool current: bridge.modelOverride === modelData
                    color: current
                        ? Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.10)
                        : "transparent"
                    border.width: current ? 2 : 1
                    border.color: current ? Theme.accent : Theme.divider

                    Behavior on color {
                        ColorAnimation {
                            duration: Theme.durFast
                            easing.type: Easing.Bezier
                            easing.bezierCurve: Theme.easeBezier
                        }
                    }

                    Behavior on border.color {
                        ColorAnimation {
                            duration: Theme.durFast
                            easing.type: Easing.Bezier
                            easing.bezierCurve: Theme.easeBezier
                        }
                    }

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 14
                        anchors.rightMargin: 14
                        anchors.topMargin: 12
                        anchors.bottomMargin: 12
                        spacing: 14

                        Item {
                            Layout.preferredWidth: 60
                            Layout.preferredHeight: 44

                            Image {
                                anchors.fill: parent
                                source: root.images[index]
                                fillMode: Image.PreserveAspectFit
                                smooth: true
                                mipmap: true
                            }
                        }

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 2

                            Text {
                                Layout.fillWidth: true
                                text: root.labels[index]
                                color: Theme.textPrimary
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.fontTitleSize
                                font.weight: Font.DemiBold
                                lineHeightMode: Text.FixedHeight
                                lineHeight: Theme.fontTitleLine
                                elide: Text.ElideRight
                            }

                            Text {
                                Layout.fillWidth: true
                                text: root.details[index]
                                color: Theme.textSecondary
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.fontAuxSize
                                font.weight: Font.Normal
                                lineHeightMode: Text.FixedHeight
                                lineHeight: Theme.fontAuxLine
                                elide: Text.ElideRight
                            }
                        }

                        // 固定占位：未选中时不画圈，但位置要留着，
                        // 不然选中／未选中切换时标题行会横向跳一下。
                        Item {
                            Layout.preferredWidth: 20
                            Layout.preferredHeight: 20

                            Rectangle {
                                anchors.fill: parent
                                radius: 10
                                color: Theme.accent
                                visible: card.current

                                Text {
                                    anchors.centerIn: parent
                                    text: "✓"
                                    color: "#FFFFFF"
                                    font.family: Theme.fontFamily
                                    font.pixelSize: 12
                                }
                            }
                        }
                    }

                    MouseArea {
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: root.choose(modelData)
                    }
                }
            }
        }
    }
}

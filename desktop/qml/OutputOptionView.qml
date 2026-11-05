import QtQuick

Rectangle {
    id: root
    property string outputDir: ""
    property bool registerIndex: true
    property bool autoSequence: true
    property string encoder: "自动"

    signal browseOutput()
    signal encoderSelected(string value)

    readonly property var encoders: ["自动", "AMD", "NVIDIA", "Intel", "软件 (CPU)"]

    radius: 12
    color: Theme.card
    border.width: 1
    border.color: Theme.divider
    implicitHeight: content.implicitHeight + 32

    Column {
        id: content
        anchors.fill: parent
        anchors.margins: 16
        spacing: 12

        Text {
            width: parent.width
            text: "输出与选项"
            color: Theme.textPrimary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontTitleSize
            font.weight: Font.DemiBold
            lineHeightMode: Text.FixedHeight
            lineHeight: Theme.fontTitleLine
        }

        Row {
            width: parent.width
            spacing: 8

            Text {
                anchors.verticalCenter: parent.verticalCenter
                width: 64
                text: "输出目录"
                color: Theme.textPrimary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontBodySize
                font.weight: Font.Normal
            }

            TextField {
                width: parent.width - 64 - 8 - 64 - 16
                text: root.outputDir
                placeholder: "建议存储卡 DCIM\\Camera01"
                onTextChanged: root.outputDir = text
            }

            AppButton {
                text: "浏览"
                btnHeight: 36
                accent: true
                onClicked: root.browseOutput()
            }
        }

        Row {
            width: parent.width
            spacing: 16

            Switch {
                label: "登记相机索引"
                checked: root.registerIndex
                onToggled: root.registerIndex = checked
            }

            Switch {
                label: "自动接续序号"
                checked: root.autoSequence
                onToggled: root.autoSequence = checked
            }
        }

        Row {
            width: parent.width
            spacing: 8

            Text {
                anchors.verticalCenter: parent.verticalCenter
                width: 64
                text: "编码器"
                color: Theme.textPrimary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontBodySize
                font.weight: Font.Normal
            }

            Item {
                width: 160
                height: 36

                AppButton {
                    id: encoderTrigger
                    width: parent.width
                    text: root.encoder
                    btnHeight: 36
                    accent: false
                    onClicked: encoderPopover.open = !encoderPopover.open
                }

                Popover {
                    id: encoderPopover
                    anchors.top: encoderTrigger.bottom
                    anchors.topMargin: 4
                    width: parent.width

                    Repeater {
                        model: root.encoders

                        delegate: Item {
                            width: parent.width
                            height: 32

                            Rectangle {
                                anchors.fill: parent
                                radius: 8
                                color: hover.containsMouse ? Theme.divider : "transparent"
                            }

                            Text {
                                anchors.left: parent.left
                                anchors.leftMargin: 8
                                anchors.verticalCenter: parent.verticalCenter
                                text: modelData
                                color: Theme.textPrimary
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.fontBodySize
                                font.weight: Font.Normal
                            }

                            MouseArea {
                                id: hover
                                anchors.fill: parent
                                hoverEnabled: true
                                onClicked: {
                                    root.encoder = modelData
                                    encoderPopover.open = false
                                    root.encoderSelected(modelData)
                                }
                            }
                        }
                    }
                }
            }
        }

        Row {
            width: parent.width
            spacing: 8

            Text {
                anchors.verticalCenter: parent.verticalCenter
                width: 64
                text: "视频封面"
                color: Theme.textPrimary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontBodySize
                font.weight: Font.Normal
            }

            AppButton {
                text: "选择封面图片"
                btnHeight: 36
                accent: false
                onClicked: {}
            }

            Avatar {
                size: 40
                fallback: "封"
            }
        }
    }
}

import QtQuick
import QtQuick.Window

Rectangle {
    id: root
    property string outputDir: ""
    property bool registerIndex: true
    property bool autoSequence: true
    property string encoder: "自动"
    property string hardwareHint: ""
    property string sequenceHint: ""
    property string coverSummary: ""
    property string coverImage: ""

    signal browseOutput()
    signal locateCard()
    signal pickCover()
    signal clearCovers()
    signal verifyCard()
    //   保留但禁用：编码器选择目前只改 root.encoder，由 start() 一并读走，
    //   没有谁需要单独被通知。信号留着是因为外部将来可能想监听；发射点
    //   已停，避免一个没人处理的信号每点一次都白跑一遍绑定。
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
                width: parent.width - 64 - 8 - 64 - 8 - 96 - 16
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

            AppButton {
                text: "定位 SD 卡"
                btnHeight: 36
                accent: false
                onClicked: root.locateCard()
            }
        }

        Row {
            width: parent.width
            spacing: 8

            AppButton {
                text: "校验索引"
                btnHeight: 32
                accent: false
                onClicked: root.verifyCard()
            }

            Text {
                anchors.verticalCenter: parent.verticalCenter
                width: parent.width - 88 - 8
                text: "检查卡内索引与文件是否一致。相册里有条目却打不开，通常是索引登记了坏条目。"
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontBodySize
                font.weight: Font.Normal
                elide: Text.ElideRight
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

            AppButton {
                id: encoderTrigger
                width: 160
                text: root.encoder
                btnHeight: 36
                accent: false
                onClicked: encoderPopover.open = !encoderPopover.open
            }

            Text {
                anchors.verticalCenter: parent.verticalCenter
                width: parent.width - 64 - 8 - 160 - 8
                text: root.hardwareHint
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontAuxSize
                font.weight: Font.Normal
                lineHeightMode: Text.FixedHeight
                lineHeight: Theme.fontAuxLine
                elide: Text.ElideRight
            }
        }

        Text {
            width: parent.width
            visible: root.sequenceHint !== ""
            text: root.sequenceHint
            color: Theme.textSecondary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontAuxSize
            font.weight: Font.Normal
            lineHeightMode: Text.FixedHeight
            lineHeight: Theme.fontAuxLine
            elide: Text.ElideRight
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
                onClicked: root.pickCover()
            }

            AppButton {
                text: "恢复自动"
                btnHeight: 36
                accent: false
                onClicked: root.clearCovers()
            }

            Avatar {
                size: 40
                source: root.coverImage
                fallback: "封"
            }

            Text {
                anchors.verticalCenter: parent.verticalCenter
                width: parent.width - 64 - 8 - 112 - 8 - 96 - 8 - 40 - 8
                text: root.coverSummary
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontBodySize
                font.weight: Font.Normal
                elide: Text.ElideRight
            }
        }
    }

    Popover {
        id: encoderPopover
        parent: encoderTrigger
        width: encoderTrigger.width

        readonly property real winY: encoderTrigger.mapToItem(null, 0, 0).y
        readonly property real winH: encoderTrigger.Window ? encoderTrigger.Window.height : 720
        readonly property bool flipUp: winY + encoderTrigger.height + 8 + height > winH

        x: 0
        y: flipUp ? -height - 4 : encoderTrigger.height + 4

        Repeater {
            model: root.encoders

            delegate: Item {
                width: encoderPopover.width - 16
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
                        // root.encoderSelected(modelData)  // 见上方「保留但禁用」
                    }
                }
            }
        }
    }
}

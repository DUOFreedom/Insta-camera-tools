import QtQuick

Rectangle {
    id: root
    property string status: "未设置样本（回退到影石默认结构）"

    signal pickSample()
    signal autoDetect()

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
            text: "相机样本 · 读取存储卡原生录制视频"
            color: Theme.textPrimary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontTitleSize
            font.weight: Font.DemiBold
            lineHeightMode: Text.FixedHeight
            lineHeight: Theme.fontTitleLine
            elide: Text.ElideRight
        }

        Text {
            width: parent.width
            text: "请插入存有原生录制视频的存储卡，程序将分析其编码、分辨率、帧率与音频轨结构，据此生成新文件。"
            color: Theme.textSecondary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontAuxSize
            font.weight: Font.Normal
            lineHeightMode: Text.FixedHeight
            lineHeight: Theme.fontAuxLine
            wrapMode: Text.Wrap
        }

        Row {
            spacing: 8

            AppButton {
                text: "选择原生录制视频"
                btnHeight: 36
                accent: true
                onClicked: root.pickSample()
            }

            AppButton {
                text: "自动从存储卡分析"
                btnHeight: 28
                accent: false
                onClicked: root.autoDetect()
            }
        }

        Text {
            width: parent.width
            text: root.status
            color: Theme.textSecondary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontAuxSize
            font.weight: Font.Normal
            lineHeightMode: Text.FixedHeight
            lineHeight: Theme.fontAuxLine
            elide: Text.ElideRight
        }
    }
}

import QtQuick

Item {
    id: root
    property string source: ""
    property string fallback: ""
    property int size: 40

    implicitWidth: size
    implicitHeight: size

    Rectangle {
        id: circle
        anchors.fill: parent
        radius: size / 2
        color: Theme.divider
        clip: true

        Image {
            anchors.fill: parent
            source: root.source
            fillMode: Image.PreserveAspectCrop
            visible: root.source !== ""
        }

        Text {
            anchors.centerIn: parent
            visible: root.source === ""
            text: root.fallback
            color: Theme.textSecondary
            font.family: Theme.fontFamily
            font.pixelSize: size / 2
            font.weight: Font.DemiBold
        }
    }
}

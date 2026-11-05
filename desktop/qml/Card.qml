import QtQuick

Item {
    id: root
    property int padding: 16
    default property alias content: body.data

    implicitWidth: 320
    implicitHeight: body.childrenRect.height + root.padding * 2

    Rectangle {
        anchors.fill: parent
        radius: 12
        color: Theme.card
        border.width: 1
        border.color: Theme.divider
    }

    Column {
        id: body
        anchors.fill: parent
        anchors.margins: root.padding
        spacing: 12
    }
}

import QtQuick

Item {
    id: root
    property alias text: area.text
    property string placeholder: ""
    property bool hasError: false
    property string errorText: ""

    readonly property bool showError: hasError && errorText !== ""

    implicitWidth: 320
    implicitHeight: 96 + (showError ? 8 + Theme.fontAuxLine : 0)
    activeFocusOnTab: true

    Rectangle {
        id: bg
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        height: 96
        radius: 8
        color: root.enabled ? Theme.card : Theme.divider
        border.width: root.activeFocus || root.hasError ? 2 : 1
        border.color: root.hasError ? Theme.error
                    : root.activeFocus ? Theme.accent
                    : Theme.divider

        Behavior on border.color {
            ColorAnimation {
                duration: Theme.durFast
                easing.type: Easing.Bezier
                easing.bezierCurve: Theme.easeBezier
            }
        }
    }

    TextEdit {
        id: area
        anchors.fill: bg
        anchors.margins: 12
        wrapMode: TextEdit.Wrap
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontBodySize
        font.weight: Font.Normal
        color: root.enabled ? Theme.textPrimary : Theme.textDisabled
        selectionColor: Theme.accent
        selectedTextColor: "#FFFFFF"

        Text {
            anchors.fill: parent
            visible: area.text === "" && !area.activeFocus
            text: root.placeholder
            color: Theme.textSecondary
            font: area.font
            wrapMode: Text.Wrap
        }
    }

    Text {
        id: errorLabel
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: bg.bottom
        anchors.topMargin: 8
        visible: root.showError
        text: root.errorText
        color: Theme.error
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontAuxSize
        font.weight: Font.Normal
        wrapMode: Text.Wrap
    }

    MouseArea {
        anchors.fill: bg
        enabled: root.enabled
        onClicked: area.forceActiveFocus()
    }
}

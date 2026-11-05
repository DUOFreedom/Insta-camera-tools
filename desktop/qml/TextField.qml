import QtQuick

Item {
    id: root
    property alias text: input.text
    property string placeholder: ""
    property alias readOnly: input.readOnly
    property bool hasError: false
    property string errorText: ""
    property alias echoMode: input.echoMode

    signal accepted()

    readonly property int fieldHeight: 36
    readonly property int radius: 8
    readonly property bool showError: hasError && errorText !== ""

    implicitWidth: 240
    implicitHeight: fieldHeight + (showError ? 8 + Theme.fontAuxLine : 0)
    activeFocusOnTab: true

    Rectangle {
        id: bg
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        height: root.fieldHeight
        radius: root.radius
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

    TextInput {
        id: input
        anchors.fill: bg
        anchors.leftMargin: 12
        anchors.rightMargin: 12
        verticalAlignment: TextInput.AlignVCenter
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontBodySize
        font.weight: Font.Normal
        color: root.enabled ? Theme.textPrimary : Theme.textDisabled
        selectionColor: Theme.accent
        selectedTextColor: "#FFFFFF"
        clip: true
        onAccepted: root.accepted()

        Text {
            anchors.fill: parent
            verticalAlignment: Text.AlignVCenter
            visible: input.text === "" && !input.activeFocus
            text: root.placeholder
            color: Theme.textSecondary
            font: input.font
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
        onClicked: input.forceActiveFocus()
    }
}

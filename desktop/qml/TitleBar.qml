import QtQuick
import QtQuick.Window

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

    //   窗口拖动自己接管，不走 startSystemMove：系统级移动期间位置由系统写，
    //   应用层插不进去，也就没法在贴边时加阻尼。
    //   代价是丢掉 Aero 贴边吸附，所以自己在松手时补一个「顶上边=最大化」。
    MouseArea {
        id: dragArea
        anchors.fill: parent
        acceptedButtons: Qt.LeftButton

        //   允许被推出屏幕的最大距离。阻尼让实际位移无限逼近但不超过它，
        //   所以松手时最多弹回这么多像素，不会有跳一下的感觉。
        readonly property int slack: 26

        property rect area: Qt.rect(0, 0, 0, 0)
        property real pressWinX: 0
        property real pressWinY: 0
        property real pressScreenX: 0
        property real pressScreenY: 0
        property bool dragging: false
        //   未加阻尼的原始位移。判「要不要最大化」必须看它：
        //   阻尼把贴边的位移压在 slack 以内，用窗口实际 y 判断的话，
        //   横着拖时手抖向上 20 px 就会被当成「要最大化」。
        property real rawMovedX: 0
        property real rawMovedY: 0
        //   光标的屏幕坐标（逻辑）。不靠位移累加，直接用
        //   「窗口坐标 + 窗内坐标」，不会随拖拽误差漂移。
        property real pointerY: 0

        //   位移越大，能推动的距离越接近 slack 而永不超过：
        //   damp(26) ≈ 13，damp(78) ≈ 19.5，damp(∞) → 26。
        function damp(over) {
            return over <= 0 ? 0 : (slack * over) / (over + slack)
        }

        function limitX(value, win) {
            var minX = area.x
            var maxX = area.x + area.width - win.width
            if (value < minX)
                return minX - damp(minX - value)
            if (value > maxX)
                return maxX + damp(value - maxX)
            return value
        }

        function limitY(value, win) {
            var minY = area.y
            var maxY = area.y + area.height - win.height
            if (value < minY)
                return minY - damp(minY - value)
            if (value > maxY)
                return maxY + damp(value - maxY)
            return value
        }

        //   不带阻尼的硬夹，松手回收时用。
        function clampX(value, win) {
            var minX = area.x
            var maxX = area.x + area.width - win.width
            return Math.max(minX, Math.min(maxX, value))
        }

        function clampY(value, win) {
            var minY = area.y
            var maxY = area.y + area.height - win.height
            return Math.max(minY, Math.min(maxY, value))
        }

        onPressed: function (mouse) {
            var win = root.targetWindow
            if (!win)
                return
            //   最大化时手拖标题栏，惯例是先还原再接着拖。
            //   还原后位置由 Qt 重算，这里不再自己算一遍，直接交给系统。
            if (win.visibility === Window.Maximized) {
                win.showNormal()
                Qt.callLater(function () {
                    if (root.targetWindow)
                        root.targetWindow.startSystemMove()
                })
                return
            }
            settle.stop()
            //   注意：QQuickScreenInfo 上没有 availableGeometry 这个属性
            //   （那是 ScreenInfo 的），直接读会拿到 undefined，赋给 rect
            //   会静默失败、area 停在 0×0，于是整窗口被夹死在 (0,0)，
            //   表现就是「拖不动」。只能用 desktopAvailable* 自己拼一个。
            var s = win.screen
            if (!s)
                return
            area = Qt.rect(s.virtualX, s.virtualY,
                           s.desktopAvailableWidth, s.desktopAvailableHeight)
            if (area.width <= 0 || area.height <= 0)
                return
            pressWinX = win.x
            pressWinY = win.y
            //   屏幕坐标 = 窗口坐标 + 窗内坐标。窗口一移动，这两项此消彼长，
            //   和保持不变，所以它才是「鼠标在屏幕上动了多少」。
            pressScreenX = win.x + mouse.x
            pressScreenY = win.y + mouse.y
            pointerY = pressScreenY
            dragging = true
        }

        onPositionChanged: function (mouse) {
            if (!dragging || !pressed)
                return
            var win = root.targetWindow
            if (!win)
                return
            var movedX = pressWinX + (win.x + mouse.x - pressScreenX)
            var movedY = pressWinY + (win.y + mouse.y - pressScreenY)
            rawMovedX = movedX
            rawMovedY = movedY
            pointerY = win.y + mouse.y
            win.x = Math.round(limitX(movedX, win))
            win.y = Math.round(limitY(movedY, win))
        }

        onReleased: {
            if (!dragging)
                return
            dragging = false
            var win = root.targetWindow
            if (!win)
                return
            //   光标顶到屏幕上沿 + 确实往上拖过，才最大化，替代系统原来的贴顶吸附。
            //   不用位移阈值判：窗口本身已经占满高度，能拖出的位移取决于
            //   按在标题栏哪个位置（按得越靠上，越拖不出多少），阈值要么永远
            //   够不到，要么横拖时手抖就触发。光标在不在屏幕最上沿没有这些歧义。
            if (pointerY <= area.y + 1 && rawMovedY < pressWinY - 2) {
                win.showMaximized()
                return
            }
            //   松手后要收回可用区域内。这里不能用 limitX/limitY：
            //   它们会给超出的部分再加一次阻尼（松手时窗口已经在阻尼位置上，
            //   等于二次衰减），结果停在离边缘 20 px 的地方、看着像没对上。
            root.settleTargetX = Math.round(clampX(win.x, win))
            root.settleTargetY = Math.round(clampY(win.y, win))
            if (root.settleTargetX !== win.x || root.settleTargetY !== win.y)
                settle.start()
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

    //   松手后把被推出屏幕的那点位移平滑收回，不是硬跳。
    //   Window 的 x/y 不能挂 Behavior，只能用定时器一步步逼近。
    property real settleTargetX: 0
    property real settleTargetY: 0

    Timer {
        id: settle
        interval: 16
        repeat: true
        onTriggered: {
            var win = root.targetWindow
            if (!win) {
                settle.stop()
                return
            }
            var dx = root.settleTargetX - win.x
            var dy = root.settleTargetY - win.y
            //   差 1 px 也得直接落到位：每帧只走 40% 再取整，
            //   剩 1 px 时 0.4 会舍回原值，定时器永远走不到头。
            if (Math.abs(dx) <= 1 && Math.abs(dy) <= 1) {
                win.x = root.settleTargetX
                win.y = root.settleTargetY
                settle.stop()
                return
            }
            win.x = Math.round(win.x + dx * 0.4)
            win.y = Math.round(win.y + dy * 0.4)
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
            iconName: "window-minimize"
            onClicked: if (root.targetWindow) root.targetWindow.showMinimized()
        }

        IconButton {
            iconName: "close"
            onClicked: if (root.targetWindow) root.targetWindow.close()
        }
    }
}

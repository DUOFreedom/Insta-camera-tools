import QtQuick 2.15

//  拖过边界时的阻尼：Flickable 用 DragOverBounds 时内容会按 1:1 跟手拖出去，
//  这里再把「超出量」按阻尼曲线压回来 —— 视觉上越推越推不动，最多让出 slack。
//  松手回弹时 contentX/contentY 自己往回收，超出量归零，偏移随之消失，
//  所以不需要另外写回弹动画。
Item {
    id: root

    //  被处理的目标：Flickable 或它的子类（ListView / GridView）。
    property Flickable flick: null
    //  最大让出量（逻辑像素）。
    property real slack: 26

    //  带符号的超出量：往下拖过底为正，往上拖过上为负。
    property real overX: 0
    property real overY: 0
    //  施加到内容上的反向偏移（只走阻尼后的部分）。
    property real shiftX: 0
    property real shiftY: 0

    function damp(over) {
        return over <= 0 ? 0 : (slack * over) / (over + slack)
    }

    function refresh() {
        if (!flick)
            return
        var minX = Math.min(0, flick.width - flick.contentWidth)
        var minY = Math.min(0, flick.height - flick.contentHeight)
        var cx = flick.contentX
        var cy = flick.contentY
        root.overX = cx > 0 ? cx : (cx < minX ? cx - minX : 0)
        root.overY = cy > 0 ? cy : (cy < minY ? cy - minY : 0)
        root.shiftX = shiftOf(root.overX)
        root.shiftY = shiftOf(root.overY)
    }

    function shiftOf(over) {
        if (over === 0)
            return 0
        var distance = Math.abs(over)
        return -Math.sign(over) * (distance - damp(distance))
    }

    onFlickChanged: refresh()
    Component.onCompleted: refresh()

    Connections {
        target: root.flick

        function onContentXChanged() { root.refresh() }
        function onContentYChanged() { root.refresh() }
        function onContentWidthChanged() { root.refresh() }
        function onContentHeightChanged() { root.refresh() }
        function onHeightChanged() { root.refresh() }
        function onWidthChanged() { root.refresh() }
    }
}

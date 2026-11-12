import QtQuick
import QtQuick.Shapes

Item {
    id: root
    property string name: ""
    property int size: 20
    property color color: Theme.iconPrimary

    readonly property string svgPath: {
        switch (name) {
        case "chevron-left": return "M15 5 L8 12 L15 19"
        case "search": return "M11 4 A7 7 0 1 0 11 18 A7 7 0 1 0 11 4 M16 16 L21 21"
        case "settings": return "M12 8 A4 4 0 1 0 12 16 A4 4 0 1 0 12 8 M12 2 L12 5 M12 19 L12 22 M2 12 L5 12 M19 12 L22 12 M5 5 L7 7 M17 17 L19 19 M19 5 L17 7 M7 17 L5 19"
        case "close": return "M6 6 L18 18 M18 6 L6 18"
        case "check": return "M4 12 L10 18 L20 6"
        case "warning": return "M12 3 L22 20 L2 20 Z M12 9 L12 14 M12 17 L12 18"
        case "info": return "M12 2 A10 10 0 1 0 12 22 A10 10 0 1 0 12 2 M12 11 L12 17 M12 7 L12 8"
        case "more-horizontal": return "M6 12 L6 13 M12 12 L12 13 M18 12 L18 13"
        case "sidebar-toggle": return "M4 6 L20 6 M4 12 L14 12 M4 18 L20 18"
        case "theme-toggle": return "M12 3 A9 9 0 1 0 12 21 A9 9 0 1 0 12 3 M12 8 A4 4 0 1 0 12 16 A4 4 0 1 0 12 8"
        case "window-minimize": return "M6 10 L18 10"
        default: return ""
        }
    }

    implicitWidth: size
    implicitHeight: size

    Shape {
        width: 24
        height: 24
        transform: Scale {
            origin.x: 0
            origin.y: 0
            xScale: root.size / 24
            yScale: root.size / 24
        }
        ShapePath {
            strokeColor: root.color
            strokeWidth: 1.5
            fillColor: "transparent"
            capStyle: ShapePath.RoundCap
            joinStyle: ShapePath.RoundJoin
            PathSvg { path: root.svgPath }
        }
    }
}

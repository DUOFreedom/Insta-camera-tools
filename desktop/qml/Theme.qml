pragma Singleton
import QtQuick

QtObject {
    property bool dark: false
    property bool reducedMotion: false

    readonly property color bgWindowLight: "#F5F5F7"
    readonly property color cardLight: "#FFFFFF"
    readonly property color sidebarLight: "#FFFFFF"
    readonly property color sidebarBorderLight: "#0F000000"
    readonly property color popoverLight: "#FFFFFF"
    readonly property color textPrimaryLight: "#1D1D1F"
    readonly property color textSecondaryLight: "#6E6E73"
    readonly property color textDisabledLight: "#AEAEB2"
    readonly property color dividerLight: "#14000000"
    readonly property color accentLight: "#007AFF"
    readonly property color accentHoverLight: "#0071E3"
    readonly property color accentPressLight: "#0062CC"

    readonly property color bgWindowDark: "#1C1C1E"
    readonly property color cardDark: "#2C2C2E"
    readonly property color sidebarDark: "#1C1C1E"
    readonly property color sidebarBorderDark: "#14FFFFFF"
    readonly property color popoverDark: "#2C2C2E"
    readonly property color textPrimaryDark: "#F5F5F7"
    readonly property color textSecondaryDark: "#98989D"
    readonly property color textDisabledDark: "#636366"
    readonly property color dividerDark: "#1AFFFFFF"
    readonly property color accentDark: "#0A84FF"
    readonly property color accentHoverDark: "#409CFF"
    readonly property color accentPressDark: "#0066CC"

    readonly property color success: "#34C759"
    readonly property color warning: "#FF9F0A"
    readonly property color error: "#FF453A"

    readonly property color bgWindow: dark ? bgWindowDark : bgWindowLight
    readonly property color card: dark ? cardDark : cardLight
    readonly property color sidebar: dark ? sidebarDark : sidebarLight
    readonly property color sidebarBorder: dark ? sidebarBorderDark : sidebarBorderLight
    readonly property color popover: dark ? popoverDark : popoverLight
    readonly property color textPrimary: dark ? textPrimaryDark : textPrimaryLight
    readonly property color textSecondary: dark ? textSecondaryDark : textSecondaryLight
    readonly property color textDisabled: dark ? textDisabledDark : textDisabledLight
    readonly property color divider: dark ? dividerDark : dividerLight
    readonly property color accent: dark ? accentDark : accentLight
    readonly property color accentHover: dark ? accentHoverDark : accentHoverLight
    readonly property color accentPress: dark ? accentPressDark : accentPressLight
    readonly property color info: accent

    readonly property color iconPrimary: textPrimary
    readonly property color iconSecondary: textSecondary

    readonly property string fontFamily: "Segoe UI Variable"

    readonly property int fontDisplaySize: 22
    readonly property int fontDisplayLine: 28
    readonly property int fontTitleSize: 17
    readonly property int fontTitleLine: 22
    readonly property int fontBodySize: 13
    readonly property int fontBodyLine: 18
    readonly property int fontAuxSize: 11
    readonly property int fontAuxLine: 16
    readonly property int fontMetricSize: 28
    readonly property int fontMetricLine: 34

    readonly property int durFast: reducedMotion ? 0 : 150
    readonly property int durMedium: reducedMotion ? 0 : 200
    readonly property int durDialog: reducedMotion ? 0 : 250
    readonly property int durPanel: reducedMotion ? 0 : 300
    readonly property var easeBezier: [0, 0, 0.25, 0.1, 0.25, 1, 1, 1]
}

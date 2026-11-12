import QtQuick
import QtQuick.Layouts

// 首次进软件时的欢迎窗：使用协议 / 使用须知 / 作者主页，三页。
// 刻意不复用 Modal.qml —— 那个面板高度按内容自适应，三页文字长短不一会让
// 面板每翻一页就跳一次；这里固定宽高，翻页只换内容。
Item {
    id: root
    z: 200
    visible: open
    property bool open: false
    property int page: 0
    readonly property int pageCount: 3
    signal closed()

    // 每次打开都从第一页开始：关掉再打开不该停在半路。
    onOpenChanged: {
        if (open) {
            page = 0
        }
    }

    readonly property string pageTitle: page === 0 ? bridge.tr("使用协议")
        : page === 1 ? bridge.tr("使用须知")
        : bridge.tr("作者主页")

    readonly property string pageHint: page === 0 ? bridge.tr("第 1 页 / 共 3 页 · 用之前请先看完")
        : page === 1 ? bridge.tr("第 2 页 / 共 3 页 · 几条容易踩的坑")
        : bridge.tr("第 3 页 / 共 3 页 · 关于这颗 star")

    function close() {
        if (!open) {
            return
        }
        // 先收起再发信号：closed 的接收方会把 open 置回 false，
        // 反过来写会绕成一次重入。
        open = false
        root.closed()
    }

    function next() {
        if (page < pageCount - 1) {
            page += 1
        }
    }

    function prev() {
        if (page > 0) {
            page -= 1
        }
    }

    //   翻到作者页就去读一次星数：不需要用户先点开仓库，一辈子只自动读一次。
    property bool starRequested: false
    onPageChanged: {
        if (open && page === pageCount - 1 && !starRequested) {
            starRequested = true
            bridge.refreshStars()
        }
    }

    Rectangle {
        id: overlay
        anchors.fill: parent
        color: "#000000"
        opacity: root.open ? 0.45 : 0

        Behavior on opacity {
            NumberAnimation {
                duration: root.open ? Theme.durMedium : Theme.durFast
                easing.type: Easing.Bezier
                easing.bezierCurve: Theme.easeBezier
            }
        }
    }

    // 吃掉点击：不然底下的队列、按钮还能被点到。
    MouseArea {
        anchors.fill: parent
        enabled: root.open
        // 点遮罩不关窗 —— 这是协议，要翻到最后一页或者按 × 才算看过。
    }

    Rectangle {
        id: panel
        anchors.centerIn: parent
        width: Math.min(460, parent.width - 48)
        height: Math.min(430, parent.height - 48)
        radius: 16
        color: Theme.card
        border.width: 1
        border.color: Theme.divider
        opacity: root.open ? 1 : 0
        scale: root.open ? 1 : 0.96
        focus: root.open

        Behavior on opacity {
            NumberAnimation {
                duration: root.open ? Theme.durDialog : Theme.durFast
                easing.type: Easing.Bezier
                easing.bezierCurve: Theme.easeBezier
            }
        }

        Behavior on scale {
            NumberAnimation {
                duration: root.open ? Theme.durDialog : Theme.durFast
                easing.type: Easing.Bezier
                easing.bezierCurve: Theme.easeBezier
            }
        }

        Keys.onLeftPressed: root.prev()
        Keys.onRightPressed: root.next()
        Keys.onEscapePressed: root.close()

        Text {
            id: title
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.leftMargin: 24
            anchors.rightMargin: 56
            anchors.topMargin: 22
            text: root.pageTitle
            color: Theme.textPrimary
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontTitleSize
            font.weight: Font.DemiBold
            lineHeightMode: Text.FixedHeight
            lineHeight: Theme.fontTitleLine
            elide: Text.ElideRight
        }

        Text {
            id: hint
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: title.bottom
            anchors.leftMargin: 24
            anchors.rightMargin: 56
            anchors.topMargin: 4
            text: root.pageHint
            color: Theme.textDisabled
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontAuxSize
            lineHeightMode: Text.FixedHeight
            lineHeight: Theme.fontAuxLine
            elide: Text.ElideRight
        }

        // × 在所有页都可用：不逼着人翻到最后一页才能走。
        Item {
            id: closeButton
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.rightMargin: 14
            anchors.topMargin: 14
            width: 28
            height: 28

            Text {
                anchors.centerIn: parent
                text: "✕"
                color: closeArea.containsMouse ? Theme.textPrimary : Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: 15
            }

            MouseArea {
                id: closeArea
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: root.close()
            }
        }

        // ---- 第 1 页：使用协议 ----
        Flickable {
            id: pageTerms
            anchors.top: hint.bottom
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: footer.top
            anchors.leftMargin: 24
            anchors.rightMargin: 24
            anchors.topMargin: 14
            anchors.bottomMargin: 12
            visible: root.page === 0
            clip: true
            contentWidth: width
            contentHeight: termsColumn.implicitHeight
            //  拖过边界时按阻尼压回，越推越推不动；松手回弹自动归位。
            boundsBehavior: Flickable.DragOverBounds
            contentItem.transform: Translate {
                x: damping.shiftX
                y: damping.shiftY
            }

            DragDamping {
                id: damping
                flick: pageTerms
            }

            Column {
                id: termsColumn
                width: pageTerms.width
                spacing: 10

                Text {
                    width: parent.width
                    text: bridge.tr("本程序按 GPL-3.0-or-later 发布：源码公开，可以自由使用、修改、再分发；再分发时要保留同一许可证，并说明源码从哪拿。")
                    wrapMode: Text.Wrap
                    color: Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontBodySize
                    lineHeightMode: Text.FixedHeight
                    lineHeight: Theme.fontBodyLine
                }

                Text {
                    width: parent.width
                    text: bridge.tr("只拿它处理你本人拍的、或者已经取得授权的素材。把别人的片子包装成自己相机拍的，不在授权范围内，后果自负。")
                    wrapMode: Text.Wrap
                    color: Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontBodySize
                    lineHeightMode: Text.FixedHeight
                    lineHeight: Theme.fontBodyLine
                }

                Text {
                    width: parent.width
                    text: bridge.tr("导入会改写视频容器的元数据，并在相机卡里写索引文件。写卡有风险，动手之前请自己备份原片。")
                    wrapMode: Text.Wrap
                    color: Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontBodySize
                    lineHeightMode: Text.FixedHeight
                    lineHeight: Theme.fontBodyLine
                }

                Text {
                    width: parent.width
                    text: bridge.tr("软件按「现状」提供，不附带任何担保。素材损坏、相机不识别、数据丢失这类后果，作者不承担责任。")
                    wrapMode: Text.Wrap
                    color: Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontBodySize
                    lineHeightMode: Text.FixedHeight
                    lineHeight: Theme.fontBodyLine
                }

                Text {
                    width: parent.width
                    text: bridge.tr("程序完全在本机跑，不上传视频、路径或任何个人信息。只有检查更新的时候会访问 GitHub 的公开接口。")
                    wrapMode: Text.Wrap
                    color: Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontBodySize
                    lineHeightMode: Text.FixedHeight
                    lineHeight: Theme.fontBodyLine
                }
            }
        }

        // ---- 第 2 页：使用须知 ----
        Flickable {
            id: pageNotes
            anchors.top: hint.bottom
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: footer.top
            anchors.leftMargin: 24
            anchors.rightMargin: 24
            anchors.topMargin: 14
            anchors.bottomMargin: 12
            visible: root.page === 1
            clip: true
            contentWidth: width
            contentHeight: notesColumn.implicitHeight
            //  拖过边界时按阻尼压回，越推越推不动；松手回弹自动归位。
            boundsBehavior: Flickable.DragOverBounds
            contentItem.transform: Translate {
                x: notesDamping.shiftX
                y: notesDamping.shiftY
            }

            DragDamping {
                id: notesDamping
                flick: pageNotes
            }

            Column {
                id: notesColumn
                width: pageNotes.width
                spacing: 10

                Text {
                    width: parent.width
                    text: bridge.tr("• 移植 inst box 要求卡里已经有一对真机原片（VID_*.mp4 和 LRV_*.lrv）当模板。没有模板只能纯转码，相机不会认。")
                    wrapMode: Text.Wrap
                    color: Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontBodySize
                    lineHeightMode: Text.FixedHeight
                    lineHeight: Theme.fontBodyLine
                }

                Text {
                    width: parent.width
                    text: bridge.tr("• 机型预设只决定编码参数（分辨率、帧率、编码器、关键帧间隔、音轨数），不会解除上面那条。")
                    wrapMode: Text.Wrap
                    color: Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontBodySize
                    lineHeightMode: Text.FixedHeight
                    lineHeight: Theme.fontBodyLine
                }

                Text {
                    width: parent.width
                    text: bridge.tr("• 第一次用，先拿一段短片走一遍：导入，插回相机，看相册能不能播、能不能下载到手机。")
                    wrapMode: Text.Wrap
                    color: Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontBodySize
                    lineHeightMode: Text.FixedHeight
                    lineHeight: Theme.fontBodyLine
                }

                Text {
                    width: parent.width
                    text: bridge.tr("• 转换期间不要拔卡、不要拔读卡器。中途关窗程序会先问你要不要中止。")
                    wrapMode: Text.Wrap
                    color: Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontBodySize
                    lineHeightMode: Text.FixedHeight
                    lineHeight: Theme.fontBodyLine
                }

                Text {
                    width: parent.width
                    text: bridge.tr("• 需要 ffmpeg。没装的话程序会在顶部提示，可以一键装到系统目录或程序目录。")
                    wrapMode: Text.Wrap
                    color: Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontBodySize
                    lineHeightMode: Text.FixedHeight
                    lineHeight: Theme.fontBodyLine
                }

                Text {
                    width: parent.width
                    text: bridge.tr("• 机型不在列表里就选「自动」，程序会从卡里的原片把参数量出来。")
                    wrapMode: Text.Wrap
                    color: Theme.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontBodySize
                    lineHeightMode: Text.FixedHeight
                    lineHeight: Theme.fontBodyLine
                }
            }
        }

        // ---- 第 3 页：作者主页 ----
        Column {
            id: pageAuthor
            anchors.top: hint.bottom
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: footer.top
            anchors.leftMargin: 24
            anchors.rightMargin: 24
            anchors.topMargin: 14
            anchors.bottomMargin: 12
            visible: root.page === 2
            spacing: 12

            Row {
                spacing: 12

                Item {
                    width: 44
                    height: 44

                    //   头像直接内嵌在 exe 里，不再依赖网络下载。
                    Image {
                        id: avatarImage
                        anchors.fill: parent
                        source: "assets/avatar.png"
                        fillMode: Image.PreserveAspectCrop
                        cache: true
                        visible: false
                        mipmap: true
                    }

                    //   用片段着色器按距离中心距离裁剪。
                    ShaderEffect {
                        anchors.fill: parent
                        visible: avatarImage.status === Image.Ready
                        property variant source: avatarImage
                        fragmentShader: `
                            uniform lowp sampler2D source;
                            varying highp vec2 qt_TexCoord0;
                            void main() {
                                vec2 center = vec2(0.5, 0.5);
                                float radius = 0.5;
                                float dist = distance(qt_TexCoord0, center);
                                if (dist > radius) discard;
                                gl_FragColor = texture2D(source, qt_TexCoord0);
                            }
                        `
                    }

                    // 首字母回退
                    Text {
                        visible: avatarImage.status !== Image.Ready
                        anchors.centerIn: parent
                        text: "D"
                        color: "#FFFFFF"
                        font.family: Theme.fontFamily
                        font.pixelSize: 20
                        font.weight: Font.DemiBold
                    }
                }

                Column {
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 2

                    Text {
                        text: "DUOFreedom"
                        color: Theme.textPrimary
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontBodySize
                        font.weight: Font.DemiBold
                    }

                    Text {
                        text: bridge.tr("一个普通高中生")
                        color: Theme.textSecondary
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontAuxSize
                    }
                }
            }

            Text {
                width: parent.width
                text: bridge.tr("这个工具最初只是不想每次手动折腾视频元数据。后来越补越多，桌面端、安卓端，还有现在这个欢迎页。")
                wrapMode: Text.Wrap
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontBodySize
                lineHeightMode: Text.FixedHeight
                lineHeight: Theme.fontBodyLine
            }

            Text {
                width: parent.width
                text: bridge.tr("有问题、有想法，去仓库开 issue。如果它帮你省了事，点个 star 就是最实在的支持 —— 不点也完全没关系，功能一样不少。")
                wrapMode: Text.Wrap
                color: Theme.textSecondary
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontBodySize
                lineHeightMode: Text.FixedHeight
                lineHeight: Theme.fontBodyLine
            }

            Text {
                width: parent.width
                text: bridge.authorUrl
                color: Theme.accent
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontAuxSize
                elide: Text.ElideMiddle
            }

            Text {
                //   星标数只在真读到过的时候出现：读不到就不提，免得像个坏掉的读数。
                width: parent.width
                visible: bridge.starState === "ok" && bridge.starCount > 0
                text: bridge.tr("仓库现在有 %1 颗星").arg(bridge.starCount)
                color: Theme.textDisabled
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontAuxSize
            }

            Text {
                //   读星数不需要用户先点开仓库，所以这里只说明读数本身的状态。
                //   读不到也不提要求，功能一样不少。
                width: parent.width
                visible: bridge.starState === "loading" || bridge.starState === "unknown"
                text: bridge.starState === "loading"
                      ? bridge.tr("正在读星标数…")
                      : bridge.tr("没读到星标数（大概网络不通）。不影响使用。")
                wrapMode: Text.Wrap
                color: Theme.textDisabled
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontAuxSize
                lineHeightMode: Text.FixedHeight
                lineHeight: Theme.fontAuxLine
            }
        }

        // 正文超出可视高度时会被下边界一刀切断，看着像是内容丢了。
        // 在正文与 footer 之间垫一层同底色的渐隐，切断处就留有还能往下滚的余地。
        Rectangle {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: footer.top
            anchors.bottomMargin: 12
            height: 18
            visible: root.open
            gradient: Gradient {
                GradientStop {
                    position: 0.0
                    color: "transparent"
                }
                GradientStop {
                    position: 1.0
                    color: Theme.card
                }
            }
        }

        // ---- 底部：翻页点 + 按钮 ----
        Item {
            id: footer
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            anchors.leftMargin: 24
            anchors.rightMargin: 24
            anchors.bottomMargin: 20
            height: 36

            Row {
                id: dots
                anchors.left: parent.left
                anchors.verticalCenter: parent.verticalCenter
                spacing: 6

                Repeater {
                    model: root.pageCount

                    delegate: Rectangle {
                        width: index === root.page ? 16 : 6
                        height: 6
                        radius: 3
                        color: index === root.page ? Theme.accent : Theme.divider

                        Behavior on width {
                            NumberAnimation {
                                duration: Theme.durFast
                                easing.type: Easing.Bezier
                                easing.bezierCurve: Theme.easeBezier
                            }
                        }

                        Behavior on color {
                            ColorAnimation {
                                duration: Theme.durFast
                                easing.type: Easing.Bezier
                                easing.bezierCurve: Theme.easeBezier
                            }
                        }
                    }
                }
            }

            RowLayout {
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                spacing: 8
                layoutDirection: Qt.RightToLeft

                // RowLayout 让按钮按内容自适应宽度，避免长文本重叠
                AppButton {
                    // 最后一页才出现，前面两页没有可 star 的东西可指。
                    visible: root.page === root.pageCount - 1
                    // 走过一次就不再催：按钮还在，只是换了句更轻的话。
                    text: bridge.starDone ? bridge.tr("已点亮 · 再去看看")
                                          : bridge.tr("去点个 star")
                    btnHeight: 36
                    Layout.preferredWidth: Math.max(btnHeight * 2.5, implicitWidth)
                    onClicked: {
                        bridge.openAuthorPage()
                    }
                }

                AppButton {
                    visible: root.page === root.pageCount - 1
                    text: bridge.tr("算了")
                    btnHeight: 36
                    accent: false
                    Layout.preferredWidth: Math.max(btnHeight * 2.5, implicitWidth)
                    onClicked: root.close()
                }

                AppButton {
                    visible: root.page < root.pageCount - 1
                    text: bridge.tr("下一步")
                    btnHeight: 36
                    Layout.preferredWidth: Math.max(btnHeight * 2.5, implicitWidth)
                    onClicked: root.next()
                }

                AppButton {
                    visible: root.page > 0
                    text: bridge.tr("上一步")
                    btnHeight: 36
                    accent: false
                    Layout.preferredWidth: Math.max(btnHeight * 2.5, implicitWidth)
                    onClicked: root.prev()
                }
            }
        }
    }
}

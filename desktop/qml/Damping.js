.pragma library

//  拖过边界时的同一条阻尼曲线：位移越大，能推动的距离越接近 slack 而永不超过。
//  窗口贴边（TitleBar.qml）和内容拖拽（DragDamping.qml）本来是各写了一份，
//  公式一模一样；抽到这里改一处就两边同时生效。
//
//  damp(26, 26) ≈ 13，damp(78, 26) ≈ 19.5，damp(∞, 26) → 26
function damp(over, slack) {
    return over <= 0 ? 0 : (slack * over) / (over + slack)
}

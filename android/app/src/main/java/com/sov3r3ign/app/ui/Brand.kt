package com.sov3r3ign.app.ui

import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.buildAnnotatedString
import com.sov3r3ign.app.ui.theme.Sov

/** «Sover**ei**gn», the «ei» in the accent, as on the site. */
fun wordmark(): AnnotatedString = buildAnnotatedString {
    append("Sover")
    pushStyle(SpanStyle(color = Sov.Accent))
    append("ei")
    pop()
    append("gn")
}

/**
 * The mark itself, from the site's SVG: viewBox 100 100 312 312. The launcher
 * icon (res/drawable/ic_launcher_foreground.xml) is the same drawing.
 */
fun DrawScope.drawMark() {
    val k = size.width / 312f
    fun p(x: Float, y: Float) = Offset((x - 100f) * k, (y - 100f) * k)
    val route = listOf(p(150f, 180f), p(360f, 150f), p(256f, 360f))
    for (i in route.indices) drawLine(Sov.AccentDim, route[i], route[(i + 1) % 3], 16f * k, StrokeCap.Round)
    listOf(p(150f, 180f), p(360f, 150f)).forEach {
        drawCircle(Sov.Bg, 32f * k, it)
        drawCircle(Sov.Accent, 32f * k, it, style = Stroke(16f * k))
    }
    drawCircle(Sov.Accent, 40f * k, p(256f, 360f))
}

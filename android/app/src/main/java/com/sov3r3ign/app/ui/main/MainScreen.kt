package com.sov3r3ign.app.ui.main

import android.provider.Settings
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.State
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.produceState
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.runtime.withFrameMillis
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.PathEffect
import androidx.compose.ui.graphics.Shadow
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.layout.layout
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.sov3r3ign.app.session.Session
import com.sov3r3ign.app.state.AccountModel
import com.sov3r3ign.app.ui.Link
import com.sov3r3ign.app.ui.PAYMENT_URL
import com.sov3r3ign.app.ui.expiryWarning
import com.sov3r3ign.app.ui.needsPayment
import com.sov3r3ign.app.ui.subscriptionLine
import com.sov3r3ign.app.ui.theme.Sov
import kotlinx.coroutines.launch
import kotlin.math.PI
import kotlin.math.hypot
import kotlin.math.min

/**
 * The main screen: the Sovereign mark as the interface (the design canvas
 * "Sovereign Android — главный экран", M2). The solid dot is the button, the
 * rings are the server and the internet; while connected a packet runs the
 * route and each node flashes as it arrives. Behind it, the site's network.
 *
 * Everything is laid out in the mockup's units of a 412 x 915 screen and
 * scaled to the phone, by width or height, whichever is tighter, so the
 * whole screen fits without scrolling on smaller phones too.
 */
@Composable
fun MainScreen(
    session: Session,
    model: AccountModel,
    onOpenDevices: () -> Unit,
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val uriHandler = LocalUriHandler.current
    val ui by model.ui.collectAsState()
    val connection = rememberConnection(session)
    val status = connection.status

    // Android's "Remove animations" setting: nothing moves, the states still read.
    val still = remember {
        runCatching {
            Settings.Global.getFloat(context.contentResolver, Settings.Global.ANIMATOR_DURATION_SCALE, 1f) == 0f
        }.getOrDefault(false)
    }
    val clock: State<Long> = produceState(0L, still) {
        if (still) return@produceState
        val start = withFrameMillis { it }
        while (true) withFrameMillis { value = it - start }
    }

    LaunchedEffect(Unit) { model.load() }

    BoxWithConstraints(Modifier.fillMaxSize()) {
        val unit: Dp = min(maxWidth.value / Mesh.WIDTH, maxHeight.value / Mesh.HEIGHT).dp
        val mesh = remember { Mesh.of(20260930) }
        NetworkBackground(mesh, clock, still)

        Column(Modifier.fillMaxSize()) {
            TopBar(
                onDevices = onOpenDevices,
                onPay = { runCatching { uriHandler.openUri(PAYMENT_URL) } },
                onSignOut = { scope.launch { model.signOut() } },
            )
            Hero(
                unit = unit,
                link = status.link,
                action = status.action,
                clock = clock,
                still = still,
                onPress = if (ui.selected == null) onOpenDevices else connection.press,
            )
            Column(
                Modifier.fillMaxWidth().padding(horizontal = 24.dp).padding(top = 16.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                Text(
                    status.title,
                    style = MaterialTheme.typography.headlineMedium,
                    color = when (status.link) {
                        Link.ON -> Sov.Green
                        Link.NO_ANSWER -> Sov.Red
                        else -> Sov.TextBright
                    },
                    textAlign = TextAlign.Center,
                )
                val detail = if (ui.selected == null) "Выберите устройство, чтобы подключиться." else status.detail
                if (detail.isNotEmpty()) {
                    Text(detail, style = MaterialTheme.typography.bodyMedium, color = Sov.TextDim, textAlign = TextAlign.Center)
                }
            }
            Spacer(Modifier.weight(1f))
            Column(
                Modifier.fillMaxWidth().padding(horizontal = 24.dp).padding(bottom = 16.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp),
            ) {
                listOfNotNull(connection.error, ui.error).forEach {
                    Text(it, style = MaterialTheme.typography.bodySmall, color = Sov.Red, textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth())
                }
                ui.notice?.let {
                    Text(it, style = MaterialTheme.typography.bodySmall, color = Sov.Yellow, textAlign = TextAlign.Center, modifier = Modifier.fillMaxWidth())
                }
                DeviceRow(ui.selected?.name, onOpenDevices)
                ui.profile?.let { p ->
                    val warning = expiryWarning(p)
                    val lapsed = warning == null && needsPayment(p)
                    Text(
                        warning ?: subscriptionLine(p),
                        style = MaterialTheme.typography.bodySmall,
                        color = when {
                            warning != null -> Sov.Yellow
                            lapsed -> Sov.Red
                            else -> Sov.TextDim
                        },
                        textAlign = TextAlign.Center,
                        modifier = Modifier.fillMaxWidth(),
                    )
                    if (needsPayment(p)) {
                        TextButton(
                            onClick = { runCatching { uriHandler.openUri(PAYMENT_URL) } },
                            modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp),
                        ) { Text("Оплатить на сайте", color = Sov.Accent) }
                    }
                }
            }
        }
    }
}

@Composable
private fun TopBar(onDevices: () -> Unit, onPay: () -> Unit, onSignOut: () -> Unit) {
    var open by remember { mutableStateOf(false) }
    Row(
        Modifier.fillMaxWidth().height(64.dp).padding(horizontal = 24.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Canvas(Modifier.size(28.dp)) { drawMark() }
            Text(
                buildWordmark(),
                style = MaterialTheme.typography.titleMedium,
                color = Sov.TextBright,
            )
        }
        Box {
            Box(
                Modifier
                    .size(48.dp)
                    .clip(RoundedCornerShape(8.dp))
                    .border(BorderStroke(1.dp, Sov.BorderBright), RoundedCornerShape(8.dp))
                    .clickable(role = Role.Button, onClickLabel = "Меню") { open = true },
                contentAlignment = Alignment.Center,
            ) {
                Canvas(Modifier.size(22.dp)) {
                    val w = 1.8.dp.toPx()
                    listOf(0.29f, 0.5f, 0.71f).forEach { y ->
                        drawLine(Sov.Text, Offset(size.width * 0.17f, size.height * y), Offset(size.width * 0.83f, size.height * y), w, StrokeCap.Round)
                    }
                }
            }
            DropdownMenu(expanded = open, onDismissRequest = { open = false }) {
                DropdownMenuItem(text = { Text("Устройства") }, onClick = { open = false; onDevices() })
                DropdownMenuItem(text = { Text("Оплатить на сайте") }, onClick = { open = false; onPay() })
                DropdownMenuItem(text = { Text("Выйти", color = Sov.Red) }, onClick = { open = false; onSignOut() })
            }
        }
    }
}

/** «Sover**ei**gn», the «ei» in the accent, as on the site. */
private fun buildWordmark() = androidx.compose.ui.text.buildAnnotatedString {
    append("Sover")
    pushStyle(androidx.compose.ui.text.SpanStyle(color = Sov.Accent))
    append("ei")
    pop()
    append("gn")
}

/** The mark itself, from the site's SVG: viewBox 100 100 312 312. */
private fun DrawScope.drawMark() {
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

@Composable
private fun Hero(
    unit: Dp,
    link: Link,
    action: String,
    clock: State<Long>,
    still: Boolean,
    onPress: () -> Unit,
) {
    val density = LocalDensity.current
    BoxWithConstraints(Modifier.fillMaxWidth().height(unit * Mark.HERO_HEIGHT)) {
        val u = with(density) { unit.toPx() }
        // the mockup's 412 units centred in whatever width there is
        val left = with(density) { (maxWidth.toPx() - Mesh.WIDTH * u) / 2f }
        fun at(x: Float, y: Float) = Offset(left + x * u, y * u)
        val on = link == Link.ON
        val broken = link == Link.NO_ANSWER

        Canvas(Modifier.fillMaxSize()) {
            val t = if (still || !on) 0f else (clock.value % Mark.CYCLE_MS) / Mark.CYCLE_MS.toFloat()
            val button = at(Mark.BUTTON_X, Mark.BUTTON_Y)
            val server = at(Mark.SERVER_X, Mark.SERVER_Y)
            val globe = at(Mark.GLOBE_X, Mark.GLOBE_Y)
            val w = 7f * u

            val first = if (on || broken || link == Link.CONNECTING) Sov.Accent else Sov.BorderBright
            val second = when {
                on -> Sov.Accent
                broken -> Sov.Red
                else -> Sov.BorderBright
            }
            // the closed side of the triangle stays a hairline, as in the mark
            drawLine(Sov.Border, globe, button, w, StrokeCap.Round)
            drawLine(first, button, server, w, StrokeCap.Round)
            drawLine(second, server, globe, w, StrokeCap.Round,
                pathEffect = if (broken) PathEffect.dashPathEffect(floatArrayOf(10f * u, 10f * u)) else null)

            if (on) {
                val fs = if (still) 0f else Mark.flash(t, Mark.serverArrival)
                val fg = if (still) 0f else Mark.flash(t, 1f)
                halo(server, Mark.SERVER_R * u * 2.4f, fs)
                halo(globe, Mark.GLOBE_R * u * 2.4f, maxOf(fg, 0.25f))
                // the button's own glow
                drawCircle(
                    Brush.radialGradient(listOf(Sov.Accent.copy(alpha = 0.35f), Color.Transparent), button, Mark.BUTTON_SIZE * u * 0.85f),
                    Mark.BUTTON_SIZE * u * 0.85f, button,
                )
            }

            // server ring
            drawCircle(Sov.Bg, Mark.SERVER_R * u, server)
            drawCircle(if (broken) Sov.Red else first, Mark.SERVER_R * u, server, style = Stroke(w))
            // the globe
            drawGlobe(globe, Mark.GLOBE_R * u, if (on) Sov.Accent else Sov.BorderBright, 6f * u)

            if (on && !still) {
                val (px, py) = Mark.packetAt(t)
                val p = at(px, py)
                drawCircle(Brush.radialGradient(listOf(Sov.Accent.copy(alpha = 0.9f), Color.Transparent), p, 12f * u), 12f * u, p)
                drawCircle(Sov.Accent, 4f * u, p)
            }
        }

        NodeLabel("Сервер", at(Mark.SERVER_X, Mark.SERVER_Y - 44f), when {
            broken -> Sov.Red
            on -> Sov.Accent
            else -> null
        }) { if (on && !still) Mark.flash((clock.value % Mark.CYCLE_MS) / Mark.CYCLE_MS.toFloat(), Mark.serverArrival) else 1f }
        NodeLabel("Интернет", at(Mark.GLOBE_X, Mark.GLOBE_Y - 48f), if (on) Sov.Accent else null) {
            if (on && !still) Mark.flash((clock.value % Mark.CYCLE_MS) / Mark.CYCLE_MS.toFloat(), 1f) else 1f
        }

        PowerButton(
            centre = at(Mark.BUTTON_X, Mark.BUTTON_Y),
            size = unit * Mark.BUTTON_SIZE,
            link = link,
            action = action,
            onPress = onPress,
        )
    }
}

private fun DrawScope.halo(centre: Offset, radius: Float, strength: Float) {
    if (strength <= 0f) return
    drawCircle(
        Brush.radialGradient(listOf(Sov.Accent.copy(alpha = 0.75f * strength), Color.Transparent), centre, radius),
        radius, centre,
    )
}

/** A circle with meridians and parallels: the internet, in the mark's line. */
private fun DrawScope.drawGlobe(c: Offset, r: Float, colour: Color, stroke: Float) {
    drawCircle(Sov.Bg, r, c)
    drawCircle(colour, r, c, style = Stroke(stroke))
    val thin = Stroke(stroke * 0.55f)
    drawOval(colour, Offset(c.x - r * 0.45f, c.y - r), Size(r * 0.9f, r * 2f), style = thin)
    drawLine(colour, Offset(c.x, c.y - r), Offset(c.x, c.y + r), stroke * 0.55f)
    drawLine(colour, Offset(c.x - r, c.y), Offset(c.x + r, c.y), stroke * 0.55f)
    val h = r * 0.866f
    drawLine(colour, Offset(c.x - h, c.y - r / 2), Offset(c.x + h, c.y - r / 2), stroke * 0.55f)
    drawLine(colour, Offset(c.x - h, c.y + r / 2), Offset(c.x + h, c.y + r / 2), stroke * 0.55f)
}

/**
 * A node's name, its baseline at [anchor], centred on it. With a [glow]
 * colour it is neon: bright letters over a blurred glow whose strength
 * [flash] gives — read here, so only these few letters recompose per frame.
 */
@Composable
private fun NodeLabel(text: String, anchor: Offset, glow: Color?, flash: () -> Float) {
    val strength = if (glow == null) 0f else 0.55f + 0.45f * flash()
    Text(
        text,
        style = TextStyle(
            fontSize = 17.sp,
            fontWeight = FontWeight(600),
            letterSpacing = 0.5.sp,
            color = if (glow == null) Sov.Text else Sov.TextBright,
            shadow = glow?.let { Shadow(it.copy(alpha = strength), Offset.Zero, 14f + 10f * strength) },
        ),
        modifier = Modifier.layout { m, c ->
            val p = m.measure(c.copy(minWidth = 0, minHeight = 0))
            layout(p.width, p.height) {
                p.place((anchor.x - p.width / 2f).toInt(), (anchor.y - p.height).toInt())
            }
        },
    )
}

@Composable
private fun PowerButton(centre: Offset, size: Dp, link: Link, action: String, onPress: () -> Unit) {
    val on = link == Link.ON
    val fill = if (on) Sov.Accent else Sov.Bg2
    val edge = when (link) {
        Link.NO_ANSWER -> Sov.Red
        else -> Sov.Accent
    }
    val ink = if (on) Sov.OnAccent else Sov.TextBright
    val iconInk = when {
        on -> Sov.OnAccent
        link == Link.NO_ANSWER -> Sov.Red
        else -> Sov.Accent
    }
    Box(
        Modifier
            .layout { m, c ->
                val p = m.measure(c.copy(minWidth = 0, minHeight = 0))
                layout(p.width, p.height) {
                    p.place((centre.x - p.width / 2f).toInt(), (centre.y - p.height / 2f).toInt())
                }
            }
            .size(size)
            .clip(CircleShape)
            .background(fill)
            .border(2.dp, edge, CircleShape)
            .clickable(role = Role.Button, onClickLabel = action, onClick = onPress),
        contentAlignment = Alignment.Center,
    ) {
        Column(horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Canvas(Modifier.size(40.dp)) {
                val s = size.width / 24f
                val stroke = Stroke(1.8f * s, cap = StrokeCap.Round)
                // the power sign: an arc open at the top, and a stroke into it
                drawArc(iconInk, startAngle = -45f, sweepAngle = 270f, useCenter = false,
                    topLeft = Offset(4f * s, 5f * s), size = Size(16f * s, 16f * s), style = stroke)
                drawLine(iconInk, Offset(12f * s, 3f * s), Offset(12f * s, 11f * s), 1.8f * s, StrokeCap.Round)
            }
            Text(action, style = MaterialTheme.typography.labelLarge, color = ink)
        }
    }
}

@Composable
private fun DeviceRow(name: String?, onOpen: () -> Unit) {
    Row(
        Modifier
            .fillMaxWidth()
            .heightIn(min = 56.dp)
            .clip(RoundedCornerShape(8.dp))
            .background(Sov.Bg2)
            .border(BorderStroke(1.dp, Sov.BorderBright), RoundedCornerShape(8.dp))
            .clickable(role = Role.Button, onClick = onOpen)
            .padding(horizontal = 16.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text("ВАШЕ УСТРОЙСТВО", style = MaterialTheme.typography.labelMedium, color = Sov.TextDim)
            Text(name ?: "Не выбрано", style = MaterialTheme.typography.bodyLarge.copy(fontWeight = FontWeight(600)), color = Sov.TextBright)
        }
        Text(if (name == null) "Выбрать ›" else "Сменить ›", style = MaterialTheme.typography.bodyMedium, color = Sov.Accent)
    }
}

/**
 * The landing's network behind everything, with its shade: darker where the
 * content sits, so the mesh never fights the text. Twinkles and the two
 * background packets run off [clock], read only while drawing.
 */
@Composable
private fun NetworkBackground(mesh: Mesh, clock: State<Long>, still: Boolean) {
    Canvas(Modifier.fillMaxSize()) {
        val sx = size.width / Mesh.WIDTH
        val sy = size.height / Mesh.HEIGHT
        fun at(i: Int) = Offset(mesh.points[i].x * sx, mesh.points[i].y * sy)
        val seconds = clock.value / 1000f

        mesh.links.forEach { (a, b) -> drawLine(Sov.BorderBright.copy(alpha = 0.55f), at(a), at(b), 1.dp.toPx()) }
        mesh.routes.forEachIndexed { k, r ->
            for (i in 0 until r.size - 1) drawLine(Sov.Accent.copy(alpha = 0.3f), at(r[i]), at(r[i + 1]), 1.4.dp.toPx())
            if (!still) {
                val (dur, delay) = mesh.routeTiming[k]
                val s = seconds - delay
                if (s >= 0f) {
                    val p = along(r.map { at(it) }, (s % dur) / dur)
                    drawCircle(Brush.radialGradient(listOf(Sov.Accent.copy(alpha = 0.8f), Color.Transparent), p, 8.dp.toPx()), 8.dp.toPx(), p)
                    drawCircle(Sov.Accent, 3.2f.dp.toPx() / 2f, p)
                }
            }
        }
        mesh.points.forEachIndexed { i, pt ->
            val alpha = if (pt.twinkles && !still) {
                0.35f + 0.65f * (0.5f - 0.5f * kotlin.math.cos(2f * PI.toFloat() * ((seconds + pt.twinkleDelay) / 5f)))
            } else 1f
            drawCircle(Sov.AccentDim.copy(alpha = alpha), pt.radius.dp.toPx() / 1.6f, at(i))
        }
        drawRect(
            Brush.radialGradient(
                0f to Sov.Bg.copy(alpha = 0.9f),
                0.6f to Sov.Bg.copy(alpha = 0.55f),
                1f to Sov.Bg.copy(alpha = 0.15f),
                center = Offset(size.width / 2f, size.height * 0.58f),
                radius = maxOf(size.width, size.height) * 0.62f,
            ),
        )
    }
}

/** A point [f] of the way along a polyline, by length: the packet runs at one speed. */
private fun along(pts: List<Offset>, f: Float): Offset {
    val lens = pts.zipWithNext { a, b -> hypot(b.x - a.x, b.y - a.y) }
    var d = f * lens.sum()
    for (i in lens.indices) {
        if (d <= lens[i]) {
            val k = if (lens[i] == 0f) 0f else d / lens[i]
            return Offset(pts[i].x + (pts[i + 1].x - pts[i].x) * k, pts[i].y + (pts[i + 1].y - pts[i].y) * k)
        }
        d -= lens[i]
    }
    return pts.last()
}

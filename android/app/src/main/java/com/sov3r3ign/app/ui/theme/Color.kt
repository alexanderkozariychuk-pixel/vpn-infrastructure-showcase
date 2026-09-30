package com.sov3r3ign.app.ui.theme

import androidx.compose.ui.graphics.Color

/*
 * The design system "Sovereign" (built from the site's own CSS, 2026-09-30),
 * token for token. Dark only, like the site. Contrast on Bg / Bg2 is noted
 * where a colour is text.
 */
object Sov {
    val Bg = Color(0xFF080C0F)
    val Bg2 = Color(0xFF0D1318)
    val Bg3 = Color(0xFF111920)
    /** Decorative hairlines only (1.4:1): never the outline of a control. */
    val Border = Color(0xFF1E2D38)
    /** Outlines people must find: secondary buttons, the device row. */
    val BorderBright = Color(0xFF2A4055)
    val Text = Color(0xFFD8EAF6)          // 15.9 / 15.2 : 1
    val TextDim = Color(0xFF7A9FB5)       // 7.0 / 6.6 : 1
    val TextBright = Color(0xFFE8F4FF)    // 17.6 / 16.8 : 1
    /** The one hue: the main action, links, the mark. */
    val Accent = Color(0xFF00D4FF)        // 11.1 : 1 as text
    val AccentHover = Color(0xFF3FE0FF)
    /** Text on an Accent fill (10.2 : 1). Never white. */
    val OnAccent = Color(0xFF04191F)
    /** Outlines of accent controls and the mark's route. Never text. */
    val AccentDim = Color(0xFF006A80)
    val Green = Color(0xFF00FF88)         // connected, active — always with its word
    val Yellow = Color(0xFFFFD04D)        // waiting, ending soon
    val Red = Color(0xFFFF4D6A)           // failed, destructive (6.1 : 1)
}

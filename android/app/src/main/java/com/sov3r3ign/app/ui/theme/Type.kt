package com.sov3r3ign.app.ui.theme

import androidx.compose.material3.Typography
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.Font
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontVariation
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.em
import androidx.compose.ui.unit.sp
import com.sov3r3ign.app.R

/*
 * Unbounded for the name, titles and big words; the phone's own sans for
 * everything read; JetBrains Mono for technical values. Both faces ship in
 * the APK (SIL OFL 1.1, licences in assets/licenses): the app asks Google
 * for nothing — the privacy policy promises no third-party services.
 * Each file is a variable font; the weights the site uses are set by axis.
 */
private fun unbounded(w: Int) = Font(
    R.font.unbounded, FontWeight(w),
    variationSettings = FontVariation.Settings(FontVariation.weight(w)),
)

private fun mono(w: Int) = Font(
    R.font.jetbrains_mono, FontWeight(w),
    variationSettings = FontVariation.Settings(FontVariation.weight(w)),
)

val Unbounded = FontFamily(unbounded(300), unbounded(400), unbounded(700))
val JetBrainsMono = FontFamily(mono(400), mono(500))
private val Body = FontFamily.Default

val Typography = Typography(
    // the status word on the main screen ("Подключено"): Unbounded 400, 26
    headlineMedium = TextStyle(fontFamily = Unbounded, fontWeight = FontWeight(400), fontSize = 26.sp, lineHeight = 32.sp, letterSpacing = (-0.02).em),
    // page titles, as the portal's .page-title
    titleLarge = TextStyle(fontFamily = Unbounded, fontWeight = FontWeight(400), fontSize = 23.sp, lineHeight = 28.sp, letterSpacing = (-0.5).sp),
    // the wordmark
    titleMedium = TextStyle(fontFamily = Unbounded, fontWeight = FontWeight(700), fontSize = 18.sp, lineHeight = 22.sp, letterSpacing = (-0.02).em),
    // text people read: larger than the site's 15 — the app is for phones held at arm's length
    bodyLarge = TextStyle(fontFamily = Body, fontSize = 17.sp, lineHeight = 26.sp),
    bodyMedium = TextStyle(fontFamily = Body, fontSize = 16.sp, lineHeight = 24.sp),
    bodySmall = TextStyle(fontFamily = Body, fontSize = 14.sp, lineHeight = 20.sp),
    // buttons
    labelLarge = TextStyle(fontFamily = Body, fontWeight = FontWeight(600), fontSize = 17.sp, lineHeight = 20.sp),
    // uppercase labels above groups ("ВАШЕ УСТРОЙСТВО"), as the portal's .card-title
    labelMedium = TextStyle(fontFamily = Body, fontSize = 12.sp, lineHeight = 16.sp, letterSpacing = 2.sp),
    // technical values: addresses, config text
    labelSmall = TextStyle(fontFamily = JetBrainsMono, fontWeight = FontWeight(400), fontSize = 13.sp, lineHeight = 20.sp),
)

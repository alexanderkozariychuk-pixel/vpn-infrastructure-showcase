package com.sov3r3ign.app.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable

/*
 * Material's roles filled from the design system. Dark only, and no dynamic
 * colour: the phone's wallpaper must not repaint the brand.
 */
private val Scheme = darkColorScheme(
    primary = Sov.Accent,
    onPrimary = Sov.OnAccent,
    primaryContainer = Sov.Bg2,
    onPrimaryContainer = Sov.Accent,
    secondary = Sov.AccentDim,
    onSecondary = Sov.TextBright,
    background = Sov.Bg,
    onBackground = Sov.Text,
    surface = Sov.Bg,
    onSurface = Sov.Text,
    surfaceVariant = Sov.Bg2,
    onSurfaceVariant = Sov.TextDim,
    surfaceContainer = Sov.Bg2,
    surfaceContainerHigh = Sov.Bg3,
    surfaceContainerHighest = Sov.Bg3,
    outline = Sov.BorderBright,
    outlineVariant = Sov.Border,
    error = Sov.Red,
    onError = Sov.Bg,
)

@Composable
fun SovereignTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = Scheme, typography = Typography, content = content)
}

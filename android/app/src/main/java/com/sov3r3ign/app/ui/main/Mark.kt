package com.sov3r3ign.app.ui.main

import kotlin.math.hypot

/**
 * The main screen is the Sovereign mark: the solid dot at its base is the
 * button (this phone), the left ring the server, the right ring the internet.
 * Positions are the mockup's, in design units of a 412-wide screen, measured
 * from the top of the hero area. Plain Kotlin, tested on the JVM.
 */
object Mark {
    const val BUTTON_X = 206f
    const val BUTTON_Y = 392f
    const val BUTTON_SIZE = 176f
    const val SERVER_X = 70f
    const val SERVER_Y = 110f
    const val SERVER_R = 26f
    const val GLOBE_X = 320f
    const val GLOBE_Y = 82f
    const val GLOBE_R = 32f
    const val HERO_HEIGHT = 500f

    /** One run of the packet, button → server → internet. */
    const val CYCLE_MS = 2800

    private val firstLeg = hypot(BUTTON_X - SERVER_X, (BUTTON_Y - BUTTON_SIZE / 2) - SERVER_Y)
    private val secondLeg = hypot(GLOBE_X - SERVER_X, GLOBE_Y - SERVER_Y)

    /** The share of a cycle at which the packet reaches the server: it runs at one speed. */
    val serverArrival: Float = firstLeg / (firstLeg + secondLeg)

    /** Where the packet is at [t] in 0..1 of a cycle, in design units. */
    fun packetAt(t: Float): Pair<Float, Float> {
        val startY = BUTTON_Y - BUTTON_SIZE / 2
        return if (t <= serverArrival) {
            val f = t / serverArrival
            (BUTTON_X + (SERVER_X - BUTTON_X) * f) to (startY + (SERVER_Y - startY) * f)
        } else {
            val f = (t - serverArrival) / (1f - serverArrival)
            (SERVER_X + (GLOBE_X - SERVER_X) * f) to (SERVER_Y + (GLOBE_Y - SERVER_Y) * f)
        }
    }

    /**
     * How bright a node flashes at [t], 0..1, for a packet arriving at
     * [arrival]: a quick rise over the 0.07 of a cycle before, a slower fall
     * over the 0.16 after — the mockup's keyTimes. An arrival at 1 is also an
     * arrival at 0: the cycle wraps.
     */
    fun flash(t: Float, arrival: Float): Float {
        var d = t - arrival
        if (d > 0.5f) d -= 1f
        if (d < -0.5f) d += 1f
        return when {
            d < -RISE || d > FALL -> 0f
            d <= 0f -> 1f + d / RISE
            else -> 1f - d / FALL
        }
    }

    private const val RISE = 0.07f
    private const val FALL = 0.16f
}

package com.sov3r3ign.app.ui.main

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class MarkTest {

    @Test
    fun `the packet reaches the server at the share of the path before it`() {
        // 237.1 px to the server, 251.6 px on to the internet: 1.36 s of 2.8.
        assertEquals(0.485f, Mark.serverArrival, 0.001f)
        val (x, y) = Mark.packetAt(Mark.serverArrival)
        assertEquals(Mark.SERVER_X, x, 0.01f)
        assertEquals(Mark.SERVER_Y, y, 0.01f)
    }

    @Test
    fun `the packet starts at the top of the button and ends at the globe`() {
        assertEquals(Mark.BUTTON_X to Mark.BUTTON_Y - Mark.BUTTON_SIZE / 2, Mark.packetAt(0f))
        val (x, y) = Mark.packetAt(1f)
        assertEquals(Mark.GLOBE_X, x, 0.01f)
        assertEquals(Mark.GLOBE_Y, y, 0.01f)
    }

    @Test
    fun `a node flashes as the packet arrives, and is dark between`() {
        val a = Mark.serverArrival
        assertEquals(1f, Mark.flash(a, a), 0.001f)
        assertEquals(0f, Mark.flash(a - 0.08f, a), 0.001f)
        assertEquals(0f, Mark.flash(a + 0.17f, a), 0.001f)
        assertTrue(Mark.flash(a - 0.03f, a) > 0f)
        assertTrue(Mark.flash(a + 0.1f, a) > 0f)
    }

    @Test
    fun `the globe's flash wraps over the end of the cycle`() {
        assertEquals(1f, Mark.flash(0f, 1f), 0.001f)
        assertTrue(Mark.flash(0.05f, 1f) > 0f)
        assertTrue(Mark.flash(0.97f, 1f) > 0f)
        assertEquals(0f, Mark.flash(0.5f, 1f), 0.001f)
    }

    @Test
    fun `an arrival at 0 is the same moment as an arrival at 1`() {
        for (t in listOf(0f, 0.03f, 0.1f, 0.5f, 0.95f, 0.99f)) {
            assertEquals(Mark.flash(t, 1f), Mark.flash(t, 0f), 0.001f)
        }
    }
}

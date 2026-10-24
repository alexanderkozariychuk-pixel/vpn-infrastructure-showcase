package com.sov3r3ign.app.ui.main

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class MeshTest {

    @Test
    fun `the generator is the landing's, bit for bit`() {
        // First values of mulberry32(20260929), computed with the landing's own JavaScript.
        val r = Mulberry32(20260929)
        assertEquals(FIRST_THREE.toList(), List(3) { r.next() })
    }

    @Test
    fun `the same seed draws the same network`() {
        val a = Mesh.of(20260930)
        val b = Mesh.of(20260930)
        assertEquals(a.points, b.points)
        assertEquals(a.links, b.links)
        assertEquals(a.routes, b.routes)
        assertNotEquals(a.points, Mesh.of(1).points)
    }

    @Test
    fun `every point is joined to at least two others, a mesh and not a hairball`() {
        val m = Mesh.of(20260930)
        val degree = IntArray(m.points.size)
        m.links.forEach { (i, j) -> degree[i]++; degree[j]++ }
        assertTrue(degree.all { it >= 2 })
        assertTrue(degree.max() <= 8)
    }

    @Test
    fun `routes are three hops along existing links, and stay on the screen`() {
        val m = Mesh.of(20260930)
        assertEquals(2, m.routes.size)
        val linked = m.links.toSet()
        m.routes.forEach { r ->
            assertEquals(4, r.size)
            assertEquals(4, r.toSet().size)
            r.zipWithNext().forEach { (a, b) -> assertTrue((minOf(a, b) to maxOf(a, b)) in linked) }
        }
        m.points.forEach {
            assertTrue(it.x in 0f..Mesh.WIDTH && it.y in 0f..Mesh.HEIGHT)
        }
    }

    private companion object {
        val FIRST_THREE = doubleArrayOf(0.33081650477834046, 0.7369657973758876, 0.29230662784539163)
    }
}

package com.sov3r3ign.app.ui.main

/**
 * The background network of the site's landing page (pwa/static/landing.html),
 * the same algorithm on a phone-sized field: points on a jittered grid, each
 * joined to its two or three nearest, a few three-hop routes with a packet
 * running each. Seeded with the landing's own generator (mulberry32), so
 * every phone draws the same composition. Plain Kotlin, no Android: tested
 * on the JVM.
 *
 * Coordinates are in the design's units, a 412 x 915 screen; the screen
 * scales them to its size.
 */
class Mesh(
    val points: List<Point>,
    val links: List<Pair<Int, Int>>,
    /** Each a path of four point indices: three hops. */
    val routes: List<List<Int>>,
    /** Per route: seconds for a packet to run it, and its start delay. */
    val routeTiming: List<Pair<Float, Float>>,
) {
    data class Point(val x: Float, val y: Float, val radius: Float, val twinkles: Boolean, val twinkleDelay: Float)

    companion object {
        const val WIDTH = 412f
        const val HEIGHT = 915f

        fun of(seed: Int, cols: Int = 4, rows: Int = 9, routeCount: Int = 2): Mesh {
            val rnd = Mulberry32(seed)
            val xy = ArrayList<FloatArray>()
            for (r in 0 until rows) for (c in 0 until cols) {
                xy += floatArrayOf(
                    ((c + 0.5) * WIDTH / cols + (rnd.next() - 0.5) * WIDTH / cols * 0.8).toFloat(),
                    ((r + 0.5) * HEIGHT / rows + (rnd.next() - 0.5) * HEIGHT / rows * 0.8).toFloat(),
                )
            }
            val near = List(xy.size) { mutableListOf<Int>() }
            val links = LinkedHashMap<Pair<Int, Int>, Unit>()
            for (i in xy.indices) {
                val order = xy.indices.filter { it != i }.sortedBy { j ->
                    val dx = xy[i][0] - xy[j][0]
                    val dy = xy[i][1] - xy[j][1]
                    dx * dx + dy * dy
                }
                val k = 2 + if (rnd.next() < 0.4) 1 else 0
                for (m in 0 until k) {
                    val j = order[m]
                    val key = minOf(i, j) to maxOf(i, j)
                    if (key !in links) {
                        links[key] = Unit
                        near[i] += j
                        near[j] += i
                    }
                }
            }
            val routes = mutableListOf<List<Int>>()
            val timing = mutableListOf<Pair<Float, Float>>()
            val used = HashSet<Int>()
            var tries = 0
            while (routes.size < routeCount && tries < 200) {
                tries++
                val start = (rnd.next() * xy.size).toInt()
                if (start in used) continue
                val path = mutableListOf(start)
                var cur = start
                for (h in 0 until 3) {
                    val opts = near[cur].filter { it !in path }
                    if (opts.isEmpty()) break
                    cur = opts[(rnd.next() * opts.size).toInt()]
                    path += cur
                }
                if (path.size < 4) continue
                used += start
                routes += path
                timing += (5 + rnd.next() * 3).toFloat() to (routes.size - 1) * 1.3f
            }
            val points = xy.map {
                val tw = rnd.next() < 0.35
                val radius = (1.6 + rnd.next() * 1.8).toFloat()
                Point(it[0], it[1], radius, tw, (rnd.next() * 5).toFloat())
            }
            return Mesh(points, links.keys.toList(), routes, timing)
        }
    }
}

/** The landing's generator, bit for bit: 32-bit wrapping arithmetic, as JavaScript's Math.imul. */
internal class Mulberry32(private var state: Int) {
    fun next(): Double {
        state += 0x6D2B79F5
        var t = state
        t = (t xor (t ushr 15)) * (1 or t)
        t = (t + ((t xor (t ushr 7)) * (61 or t))) xor t
        return ((t xor (t ushr 14)).toLong() and 0xFFFFFFFFL) / 4294967296.0
    }
}

package com.sov3r3ign.app

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * The words the payment provider's terms keep out of anything public; the
 * site is held to them by tests/test_public_wording.py, and this is the same
 * list for the app, whose texts a moderator may read too. The service is
 * described by what it does, never by what it gets around.
 *
 * Scans all of src/main — code and comments alike: a comment is one edit
 * away from becoming a string.
 */
class WordingTest {

    private val banned = mapOf(
        "DPI" to "\\bDPI\\b",
        // \b because "необходимо" contains the letters.
        "обход" to "\\bобход",
        "белые списки" to "бел\\w*\\s+спис",
        // The site's pattern is "блокировк", which misses the genitive plural
        // ("без блокировок") — the most likely way to write it. Verb forms
        // stay allowed: "заблокировать промокод" is in the site's terms.
        "блокировки" to "блокиров(к|ок)",
        "цензура" to "цензур",
        "РКН" to "роскомнадзор|\\bРКН\\b",
        "bypass" to "\\bbypass",
        "allowlist / whitelist" to "\\b(allow|white)[\\s-]?list",
        "censorship" to "censor",
        "circumvent" to "circumvent",
    ).mapValues { (_, p) -> Regex("(?U)$p", RegexOption.IGNORE_CASE) }

    // Gradle runs unit tests from the module directory.
    private val sources = File("src/main").walkTopDown()
        .filter { it.isFile && it.extension in setOf("kt", "xml") }
        .toList()

    @Test
    fun `the sources were found`() {
        // A path that matches nothing would make the check below pass vacuously.
        assertTrue(sources.any { it.path.endsWith("ui/Messages.kt") })
        assertTrue(sources.any { it.name == "AndroidManifest.xml" })
    }

    @Test
    fun `no banned word anywhere in the app`() {
        val found = sources.flatMap { f ->
            val text = f.readText()
            banned.filterValues { it.containsMatchIn(text) }.keys.map { "${f.path}: $it" }
        }
        assertEquals(emptyList<String>(), found)
    }

    @Test
    fun `the patterns catch what they are for`() {
        // Checked in both alphabets' cases: \b must see Cyrillic as letters.
        assertTrue(banned.getValue("обход").containsMatchIn("Обход ограничений"))
        assertTrue(banned.getValue("блокировки").containsMatchIn("без блокировок"))
        assertTrue(banned.getValue("allowlist / whitelist").containsMatchIn("white-list"))
        assertTrue(banned.values.none { it.containsMatchIn("необходимо подключение") })
        assertTrue(banned.values.none { it.containsMatchIn("заблокировать промокод") })
    }
}

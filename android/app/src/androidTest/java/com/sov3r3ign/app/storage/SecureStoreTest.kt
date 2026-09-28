package com.sov3r3ign.app.storage

import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
import java.security.KeyStore

/*
 * Runs on the phone: `./gradlew connectedDebugAndroidTest`. Android Keystore
 * does not exist on a laptop's JVM, and a store tested against a fake key
 * would prove nothing about the real one.
 *
 * Uses its own key alias and directory, so it never touches what the app
 * itself has stored on the same phone.
 */
@RunWith(AndroidJUnit4::class)
class SecureStoreTest {

    private val context = InstrumentationRegistry.getInstrumentation().targetContext
    private val store = SecureStore(context, alias = ALIAS, dirName = DIR)
    private val conf = "[Interface]\nPrivateKey = aGVsbG8gd29ybGQgdGhpcyBpcyBub3QgYSBrZXk=\n"

    @After
    fun cleanUp() = store.clear()

    @Test
    fun whatIsStoredComesBack() {
        store.put("conf", conf)
        assertEquals(conf, store.get("conf"))
    }

    @Test
    fun theFileOnDiskDoesNotContainTheKey() {
        store.put("conf", conf)
        val onDisk = String(store.file("conf").readBytes(), Charsets.ISO_8859_1)
        assertFalse(onDisk.contains("PrivateKey"))
        assertFalse(onDisk.contains("aGVsbG8"))
    }

    @Test
    fun theFilesLiveWhereBackupDoesNotReach() {
        store.put("conf", conf)
        val path = store.file("conf").canonicalPath
        assertTrue(path, path.startsWith(context.noBackupFilesDir.canonicalPath))
    }

    @Test
    fun somethingNeverStoredIsAbsent() {
        assertNull(store.get("token"))
    }

    @Test
    fun twoFilesSwappedOnDiskAreBothRejected() {
        store.put("token", "t")
        store.put("conf", conf)
        store.file("conf").copyTo(store.file("token"), overwrite = true)
        assertNull(store.get("token"))
    }

    @Test
    fun aLostKeyMeansAbsentNotACrash() {
        store.put("conf", conf)
        KeyStore.getInstance("AndroidKeyStore").apply { load(null) }.deleteEntry(ALIAS)
        assertNull(store.get("conf"))
        assertFalse("an unreadable file is removed", store.file("conf").exists())
    }

    @Test
    fun aTruncatedFileIsAbsentNotACrash() {
        store.put("conf", conf)
        store.file("conf").writeBytes(byteArrayOf(12, 1, 2))
        assertNull(store.get("conf"))
    }

    @Test
    fun signOutLeavesNothingReadable() {
        store.put("token", "t")
        store.put("conf", conf)
        store.clear()
        assertNull(store.get("token"))
        assertNull(store.get("conf"))
    }

    @Test
    fun aNameThatCouldEscapeTheDirectoryIsRefused() {
        try {
            store.put("../shared_prefs/x", "v")
            throw AssertionError("expected a refusal")
        } catch (e: IllegalArgumentException) {
            // expected
        }
    }

    private companion object {
        const val ALIAS = "sovrn-store-test"
        const val DIR = "secure-test"
    }
}

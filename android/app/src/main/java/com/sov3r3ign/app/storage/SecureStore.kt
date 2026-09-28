package com.sov3r3ign.app.storage

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import java.io.ByteArrayOutputStream
import java.io.File
import java.io.IOException
import java.security.GeneralSecurityException
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/**
 * Small encrypted storage for the token and the device's .conf.
 *
 * Three layers, each for a different leak:
 *  - files live in noBackupFilesDir, which Android leaves out of both cloud
 *    backup and device-to-device transfer (allowBackup="false" alone does not
 *    stop the latter on Android 12+);
 *  - contents are AES-256-GCM encrypted with a key held in Android Keystore,
 *    which never leaves the phone, so a copied file is useless elsewhere;
 *  - each value is bound to its name as associated data, so swapping two
 *    files on disk makes both unreadable instead of one passing for the other.
 *
 * Not a defence against root on the phone while the app runs, or against code
 * inside this process. Nothing at the app level is.
 *
 * Everything stored here can be fetched again from the server. So a value that
 * cannot be decrypted — the Keystore key was lost, which some phones do after
 * the screen lock is removed — is deleted and read as absent: the app asks the
 * customer to sign in again instead of crashing.
 *
 * Blocking file I/O. Call it off the main thread.
 */
class SecureStore(
    context: Context,
    private val alias: String = "sovrn-store",
    dirName: String = "secure",
) : Secrets {
    private val dir = File(context.noBackupFilesDir, dirName)

    override fun put(name: String, value: String) {
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.ENCRYPT_MODE, key())
        cipher.updateAAD(check(name).toByteArray(Charsets.UTF_8))
        val sealed = cipher.doFinal(value.toByteArray(Charsets.UTF_8))
        val iv = cipher.iv

        val bytes = ByteArrayOutputStream().apply {
            write(iv.size)
            write(iv)
            write(sealed)
        }.toByteArray()

        // Write beside, then rename: a crash mid-write leaves the old value,
        // never half of the new one.
        dir.mkdirs()
        val tmp = File(dir, "$name.tmp")
        tmp.writeBytes(bytes)
        if (!tmp.renameTo(file(name))) throw IOException("could not replace $name")
    }

    override fun get(name: String): String? {
        val f = file(check(name))
        if (!f.exists()) return null
        return try {
            val bytes = f.readBytes()
            val ivLen = bytes[0].toInt()
            val iv = bytes.copyOfRange(1, 1 + ivLen)
            val cipher = Cipher.getInstance(TRANSFORMATION)
            cipher.init(Cipher.DECRYPT_MODE, existingKey() ?: return drop(f), GCMParameterSpec(TAG_BITS, iv))
            cipher.updateAAD(name.toByteArray(Charsets.UTF_8))
            String(cipher.doFinal(bytes, 1 + ivLen, bytes.size - 1 - ivLen), Charsets.UTF_8)
        } catch (e: GeneralSecurityException) {
            drop(f)
        } catch (e: IndexOutOfBoundsException) {
            drop(f) // truncated file
        }
    }

    override fun remove(name: String) {
        file(check(name)).delete()
    }

    /** Sign-out: every value, and the key that could read them. */
    override fun clear() {
        dir.listFiles()?.forEach { it.delete() }
        keyStore().deleteEntry(alias)
    }

    internal fun file(name: String) = File(dir, "$name.bin")

    private fun drop(f: File): String? {
        f.delete()
        return null
    }

    private fun check(name: String): String {
        require(NAME.matches(name)) { "bad storage name: $name" }
        return name
    }

    private fun keyStore(): KeyStore = KeyStore.getInstance(PROVIDER).apply { load(null) }

    private fun existingKey(): SecretKey? =
        (keyStore().getEntry(alias, null) as? KeyStore.SecretKeyEntry)?.secretKey

    private fun key(): SecretKey = existingKey() ?: KeyGenerator
        .getInstance(KeyProperties.KEY_ALGORITHM_AES, PROVIDER)
        .apply {
            init(
                KeyGenParameterSpec.Builder(
                    alias,
                    KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
                )
                    .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                    .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                    .setKeySize(256)
                    // No user authentication: the tunnel has to start after a
                    // reboot and under always-on VPN, before anyone unlocks.
                    .build()
            )
        }
        .generateKey()

    private companion object {
        const val PROVIDER = "AndroidKeyStore"
        const val TRANSFORMATION = "AES/GCM/NoPadding"
        const val TAG_BITS = 128
        val NAME = Regex("[a-z][a-z0-9_]{0,31}")
    }
}

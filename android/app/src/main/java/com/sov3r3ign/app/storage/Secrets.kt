package com.sov3r3ign.app.storage

/**
 * What the rest of the app needs from storage. SecureStore is the real one;
 * tests use a map, so the session logic can be checked on a laptop without
 * Android Keystore.
 */
interface Secrets {
    fun put(name: String, value: String)
    fun get(name: String): String?
    fun remove(name: String)
    fun clear()
}

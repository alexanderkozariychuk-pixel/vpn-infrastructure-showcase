package com.sov3r3ign.app.api

import java.io.IOException
import java.net.HttpURLConnection
import java.net.URI

/**
 * The real transport, on the platform's own HttpURLConnection. No HTTP
 * library: five endpoints do not justify another dependency in an app whose
 * whole job is trust.
 *
 * Blocking. Call it off the main thread.
 */
class HttpTransport(private val baseUrl: String = "https://sov3r3ign.com") : Transport {

    @Throws(IOException::class)
    override fun send(method: String, path: String, token: String?, jsonBody: String?): HttpReply {
        val conn = URI.create(baseUrl + path).toURL().openConnection() as HttpURLConnection
        try {
            conn.requestMethod = method
            conn.connectTimeout = 10_000
            conn.readTimeout = 15_000
            conn.setRequestProperty("Accept", "application/json")
            if (token != null) conn.setRequestProperty("Authorization", "Bearer $token")
            if (jsonBody != null) {
                conn.doOutput = true
                conn.setRequestProperty("Content-Type", "application/json; charset=utf-8")
                conn.outputStream.use { it.write(jsonBody.toByteArray(Charsets.UTF_8)) }
            }
            val code = conn.responseCode
            // Error bodies come on a different stream, and carry the reason.
            val stream = if (code >= 400) conn.errorStream else conn.inputStream
            val body = stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() } ?: ""
            return HttpReply(code, body)
        } finally {
            conn.disconnect()
        }
    }
}

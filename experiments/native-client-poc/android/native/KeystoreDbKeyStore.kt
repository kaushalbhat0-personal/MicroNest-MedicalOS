/**
 * A1 reference implementation for Android Keystore–protected DB key material.
 *
 * STATUS: SOURCE SAMPLE ONLY — NOT RUNTIME-TESTED on this workstation unless
 * evidence/a1_keystore_runtime.json reports PASS after device/emulator run.
 *
 * Do not claim Keystore integration is proven from this file alone.
 */
package com.healthcareos.poc.security

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

object KeystoreDbKeyStore {
    private const val ANDROID_KEYSTORE = "AndroidKeyStore"
    private const val KEY_ALIAS = "hos_poc_db_master_v1"
    private const val PREFS = "hos_poc_sealed" // holds ciphertext only, never raw DB key
    private const val PREF_WRAPPED = "wrapped_db_key"
    private const val PREF_IV = "wrapped_db_key_iv"

    fun ensureKey(): SecretKey {
        val ks = KeyStore.getInstance(ANDROID_KEYSTORE).apply { load(null) }
        (ks.getKey(KEY_ALIAS, null) as? SecretKey)?.let { return it }
        val kg = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, ANDROID_KEYSTORE)
        kg.init(
            KeyGenParameterSpec.Builder(
                KEY_ALIAS,
                KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT
            )
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setUserAuthenticationRequired(false) // PoC; production: require biometric/lock
                .build()
        )
        return kg.generateKey()
    }

    /** Persist random DB key wrapped by Keystore AES-GCM. Never store plaintext key in prefs. */
    fun wrapAndStore(context: Context, rawDbKey: ByteArray) {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, ensureKey())
        val iv = cipher.iv
        val wrapped = cipher.doFinal(rawDbKey)
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
            .putString(PREF_WRAPPED, android.util.Base64.encodeToString(wrapped, android.util.Base64.NO_WRAP))
            .putString(PREF_IV, android.util.Base64.encodeToString(iv, android.util.Base64.NO_WRAP))
            .apply()
        rawDbKey.fill(0)
    }

    fun unwrap(context: Context): ByteArray? {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val wrappedB64 = prefs.getString(PREF_WRAPPED, null) ?: return null
        val ivB64 = prefs.getString(PREF_IV, null) ?: return null
        val wrapped = android.util.Base64.decode(wrappedB64, android.util.Base64.NO_WRAP)
        val iv = android.util.Base64.decode(ivB64, android.util.Base64.NO_WRAP)
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.DECRYPT_MODE, ensureKey(), GCMParameterSpec(128, iv))
        return cipher.doFinal(wrapped)
    }

    fun clear(context: Context) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit().clear().apply()
        val ks = KeyStore.getInstance(ANDROID_KEYSTORE).apply { load(null) }
        if (ks.containsAlias(KEY_ALIAS)) ks.deleteEntry(KEY_ALIAS)
    }
}

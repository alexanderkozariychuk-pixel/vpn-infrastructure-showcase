import java.util.Properties

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kotlin.serialization)
}

/*
 * Release signing. The repository is public, so the key and its passwords
 * never enter it: they are read from a properties file outside it —
 * ~/.config/sovrn/keystore.properties, or the path given as
 * -Psovrn.signing=<file>. Without that file the release build comes out
 * unsigned (app-release-unsigned.apk), which Android refuses to install;
 * nothing half-signed is produced. See docs/android-release.md.
 */
val releaseSigning: Properties? = run {
    val path = findProperty("sovrn.signing") as String?
        ?: "${System.getProperty("user.home")}/.config/sovrn/keystore.properties"
    val f = file(path)
    if (f.isFile) Properties().apply { f.inputStream().use { load(it) } } else null
}

android {
    namespace = "com.sov3r3ign.app"
    compileSdk {
        version = release(37)
    }

    defaultConfig {
        applicationId = "com.sov3r3ign.app"
        minSdk = 26
        targetSdk = 37
        versionCode = 1
        versionName = "1.0"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    signingConfigs {
        releaseSigning?.let { p ->
            create("release") {
                storeFile = file(p.getProperty("storeFile"))
                storePassword = p.getProperty("storePassword")
                keyAlias = p.getProperty("keyAlias")
                keyPassword = p.getProperty("keyPassword")
            }
        }
    }

    buildTypes {
        release {
            signingConfig = signingConfigs.findByName("release")
            // Off for the first release: the tunnel library reaches Java from
            // native code by name, and shrinking would need keep rules proven
            // on a device first.
            optimization {
                enable = false
            }
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_11
        targetCompatibility = JavaVersion.VERSION_11
    }
    buildFeatures {
        compose = true
        // VERSION_CODE, compared with the site's /api/public/android.
        buildConfig = true
    }
    packaging {
        jniLibs {
            // wg and wg-quick are GPL-2.0 executables used only by the root
            // backend (AwgQuickBackend). GoBackend needs libwg-go.so alone.
            excludes += setOf("**/libwg.so", "**/libwg-quick.so")
        }
    }
}

dependencies {
    implementation(files("libs/amneziawg-tunnel-fba8e09c.aar"))
    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.compose.material3)
    implementation(libs.androidx.compose.ui)
    implementation(libs.androidx.compose.ui.graphics)
    implementation(libs.androidx.compose.ui.tooling.preview)
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.lifecycle.runtime.ktx)
    implementation(libs.kotlinx.serialization.json)
    testImplementation(libs.junit)
    androidTestImplementation(platform(libs.androidx.compose.bom))
    androidTestImplementation(libs.androidx.compose.ui.test.junit4)
    androidTestImplementation(libs.androidx.espresso.core)
    androidTestImplementation(libs.androidx.junit)
    debugImplementation(libs.androidx.compose.ui.test.manifest)
    debugImplementation(libs.androidx.compose.ui.tooling)
}
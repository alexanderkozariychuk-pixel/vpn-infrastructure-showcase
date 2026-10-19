# Android client — releasing

How a release APK is signed, checked and published. The repository is
public: nothing secret below is ever committed — not the key, not its
password, not a file that holds either.

## The signing key

One key for the life of the app. Android updates an installed app only with
an APK signed by the same key: **a lost key means the app can never be
updated** — only replaced by a different app, installed by hand on every
phone. A leaked key lets anyone ship an "update" that phones accept.

### Create it — once

```bash
mkdir -p ~/.config/sovrn && chmod 700 ~/.config/sovrn
openssl rand -base64 24          # the password; put it in the password manager now
keytool -genkeypair -v \
  -keystore ~/.config/sovrn/sovrn-release.jks -storetype PKCS12 \
  -alias sovrn -keyalg RSA -keysize 4096 -validity 36500 \
  -dname "CN=Sovereign"
```

- PKCS12 has one password for the store and the key; keytool asks once.
- The certificate is readable by anyone who has the APK. `CN=Sovereign`
  and nothing else: no personal name, no city, no email.

### Tell the build where it is

`~/.config/sovrn/keystore.properties`, readable only by you:

```properties
storeFile=/home/<user>/.config/sovrn/sovrn-release.jks
storePassword=<password>
keyAlias=sovrn
keyPassword=<password>
```

```bash
chmod 600 ~/.config/sovrn/keystore.properties
```

`app/build.gradle.kts` reads that path, or the one given as
`-Psovrn.signing=<file>`. Without the file the release comes out as
`app-release-unsigned.apk`, which no phone installs.

### Back it up — before the first APK leaves the laptop

- The `.jks` file in **two places off this laptop** — e.g. a USB stick kept
  at home and an encrypted cloud folder. The file is already encrypted by its
  password.
- The password in the password manager (Bitwarden, folder "Sovereign") —
  **not** next to the file.
- Check the copy, not just that it exists:
  `keytool -list -keystore <copy>.jks -alias sovrn` with the password from
  the manager must print the same SHA-256 as below.

### Its fingerprint — public, safe to publish

```bash
keytool -list -v -keystore ~/.config/sovrn/sovrn-release.jks -alias sovrn | grep SHA256
```

Recorded once, in `android/release-cert.sha256` (one line, the hex digest
as keytool prints it). `tools/android-release.sh` refuses any APK whose
signer does not match it. It is public by nature: anyone with the APK can
read it.

## Building and checking a release

`versionCode` goes up by one for every APK that is published, even a
rebuild; Android will not install a lower or equal code over a higher one.
`versionName` is what people see.

```bash
cd ~/Projects/vpn-infrastructure-showcase/android
./gradlew clean test assembleRelease
APK=app/build/outputs/apk/release/app-release.apk
BT=$(ls -d ~/Android/Sdk/build-tools/* | sort -V | tail -1)
```

Every check below must pass before the APK is published:

```bash
# 1. Signed with our key: the SHA-256 must match the one recorded above.
$BT/apksigner verify --verbose --print-certs "$APK" | grep -E "Verified using|SHA-256"

# 2. Version, and not debuggable (a debuggable build prints application-debuggable).
$BT/aapt2 dump badging "$APK" | grep -E "^package:|application-debuggable"

# 3. No private key inside — by key format, not by the bare "PrivateKey = "
#    prefix, which the library's own template contains.
rm -rf /tmp/apkx && unzip -q "$APK" -d /tmp/apkx
grep -rlaE "PrivateKey = [A-Za-z0-9+/]{43}=" /tmp/apkx || echo "no key"

# 4. The GPL tools stayed out: libwg-go.so only, per architecture.
unzip -l "$APK" | grep "\.so$"

sha256sum "$APK"
```

## Phones that ran a debug build

A debug build is signed with the SDK's debug key, and Android will not
replace it with a release build. Uninstall first — the phone then needs its
account signed in and its device chosen again:

```bash
adb uninstall com.sov3r3ign.app
adb install app/build/outputs/apk/release/app-release.apk
```

## Publishing

The portal serves the APK itself: `/download/android` is the file and
`/api/public/android` describes it (version, size, SHA-256) for the
Connect page and for the app's «Доступна новая версия». Both read
`/opt/pwa/downloads` on the app server, mounted read-only into the
container (`pwa/api/android.py`, `pwa/docker-compose.yml`). A release is
two files copied there — no deploy:

```bash
~/Projects/vpn-infrastructure-showcase/tools/android-release.sh            # every check above, uploads nothing
~/Projects/vpn-infrastructure-showcase/tools/android-release.sh --publish  # the checks, then the upload
curl -s https://sov3r3ign.com/api/public/android
```

The script refuses an APK signed by another key, a debuggable one, one
with a private key or other native code inside, and a versionCode not
above the one the portal offers. It writes the APK first and its
description second, each renamed into place; the portal offers a release
only while the description matches the file beside it.

The way back: publish the previous APK again (with a higher versionCode —
phones will not go down), or `sudo rm /opt/pwa/downloads/android.json` on
the app server, and the portal offers nothing.

#!/bin/bash
#
# android-release.sh — check a release APK and put it on the portal.
# Run on the workstation, from anywhere:
#
#   tools/android-release.sh            checks only, uploads nothing
#   tools/android-release.sh --publish  checks, then uploads to sov-app
#
# What it checks (docs/android-release.md, "Building and checking a release"):
#   1. signed, and by our key: the certificate's SHA-256 equals the one in
#      android/release-cert.sha256 (public; written once, when the key was made);
#   2. the package is ours and not debuggable;
#   3. no WireGuard private key inside, by key format;
#   4. native code is the known list (NATIVE_OK): the tunnel's libwg-go.so and
#      Compose's own libandroidx.graphics.path.so (Apache-2.0) — and never the
#      GPL tools libwg.so / libwg-quick.so;
#   5. the versionCode is above the one the portal offers now.
#
# Publishing writes two files into /opt/pwa/downloads on the app server, which
# the portal container mounts read-only (pwa/api/android.py): the APK, then its
# description. Each is uploaded under a temporary name and renamed into place,
# so a reader sees the old pair or the new one, never half a file. No deploy,
# no container restart.
#
# The way back: run it again with the previous APK. Or remove the description
# (sudo rm /opt/pwa/downloads/android.json) and the portal offers nothing.
set -euo pipefail

REPO=$(cd "$(dirname "$0")/.." && pwd)
APK=${APK:-$REPO/android/app/build/outputs/apk/release/app-release.apk}
CERT_FILE=$REPO/android/release-cert.sha256
HOST=${HOST:-sov-app}
DEST=/opt/pwa/downloads
PACKAGE=com.sov3r3ign.app
# Native libraries an APK of ours may carry. A new one stops the release until
# someone has looked at where it comes from and under what licence.
NATIVE_OK='libwg-go.so libandroidx.graphics.path.so'

BT=${BT:-$(find "$HOME/Android/Sdk/build-tools" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | sort -V | tail -1)}
fail() { echo "FAIL: $*" >&2; exit 1; }
ok() { echo "ok   $*"; }

[[ -f $APK ]] || fail "no APK at $APK — build it: cd $REPO/android && ./gradlew clean test assembleRelease"
[[ -x $BT/apksigner && -x $BT/aapt2 ]] || fail "build-tools not found (set BT=<sdk>/build-tools/<version>)"
[[ -s $CERT_FILE ]] || fail "$CERT_FILE is empty — record the key's SHA-256 there first (docs/android-release.md)"

# 1. Our signature.
want=$(tr -d ' :\n' < "$CERT_FILE" | tr 'A-F' 'a-f')
got=$("$BT/apksigner" verify --print-certs "$APK" 2>/dev/null | sed -n 's/^Signer #1 certificate SHA-256 digest: //p' | tr -d ' :' | tr 'A-F' 'a-f')
[[ -n $got ]] || fail "apksigner does not verify this APK (unsigned?)"
[[ $got == "$want" ]] || fail "signed by another key: $got"
ok "signed by our key"

# 2. Package, version, not debuggable.
badging=$("$BT/aapt2" dump badging "$APK")
pkg=$(sed -n "s/^package: name='\([^']*\)'.*/\1/p" <<<"$badging")
code=$(sed -n "s/^package: .* versionCode='\([0-9]*\)'.*/\1/p" <<<"$badging")
name=$(sed -n "s/^package: .* versionName='\([^']*\)'.*/\1/p" <<<"$badging")
[[ $pkg == "$PACKAGE" ]] || fail "package is '$pkg'"
[[ $code =~ ^[1-9][0-9]*$ ]] || fail "versionCode '$code'"
[[ $name =~ ^[0-9][0-9A-Za-z.-]{0,31}$ ]] || fail "versionName '$name'"
grep -q "application-debuggable" <<<"$badging" && fail "debuggable build"
ok "$pkg $name (code $code), not debuggable"

# 3. No private key inside.
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
unzip -q "$APK" -d "$tmp/x"
if grep -rlaE "PrivateKey = [A-Za-z0-9+/]{43}=" "$tmp/x" >/dev/null; then fail "a private key is inside the APK"; fi
ok "no private key inside"

# 4. Native code.
files=$(unzip -Z1 "$APK")
other=$(grep '\.so$' <<<"$files" | while read -r so; do
    [[ " $NATIVE_OK " == *" ${so##*/} "* ]] || echo "$so"
done)
[[ -z $other ]] || fail "unexpected native libraries: ${other//$'\n'/ }"
grep -q '/libwg-go\.so$' <<<"$files" || fail "libwg-go.so missing"
ok "native code: $NATIVE_OK, nothing else"

size=$(stat -c %s "$APK")
sha=$(sha256sum "$APK" | cut -d' ' -f1)
printf '{"version_code": %d, "version_name": "%s", "sha256": "%s", "size": %d}\n' "$code" "$name" "$sha" "$size" > "$tmp/android.json"
echo "     size $size, sha256 $sha"

# 5. Above what the portal offers now.
# $DEST is ours and expands here, on purpose (SC2029).
# shellcheck disable=SC2029
current=$(ssh "$HOST" "cat $DEST/android.json 2>/dev/null" | sed -n 's/.*"version_code": *\([0-9]*\).*/\1/p' || true)
if [[ -n $current ]] && (( code <= current )); then
    fail "versionCode $code is not above the portal's $current — raise it in android/app/build.gradle.kts"
fi
ok "versionCode $code is above the portal's ${current:-(none)}"

if [[ ${1:-} != "--publish" ]]; then
    echo "Checks passed. Nothing uploaded; run with --publish to put it on the portal."
    exit 0
fi

scp -q "$APK" "$HOST:/tmp/sovereign.apk.upload"
scp -q "$tmp/android.json" "$HOST:/tmp/android.json.upload"
# $DEST expands here, on purpose.
# shellcheck disable=SC2029
ssh "$HOST" "set -e
  sudo install -d -m 755 $DEST
  sudo install -m 644 /tmp/sovereign.apk.upload $DEST/.sovereign.apk.new
  sudo install -m 644 /tmp/android.json.upload $DEST/.android.json.new
  sudo mv -f $DEST/.sovereign.apk.new $DEST/sovereign.apk
  sudo mv -f $DEST/.android.json.new $DEST/android.json
  rm -f /tmp/sovereign.apk.upload /tmp/android.json.upload"
ok "published to $HOST:$DEST"
echo "Check: curl -s https://sov3r3ign.com/api/public/android"

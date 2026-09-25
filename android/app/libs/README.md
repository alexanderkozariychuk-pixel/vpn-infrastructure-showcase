# app/libs

`amneziawg-tunnel-fba8e09c.aar` belongs here and is deliberately not committed.

Built from amnezia-vpn/amneziawg-android, branch `sovrn-build`, commit `fba8e09c`
(upstream master `ff15093b` + a Makefile fix so the Go runtime patch lands on the
toolchain that actually compiles), with `./gradlew :tunnel:assembleRelease`.

    sha256  6a0782f69dd3dbb80774e56dd79e2514e1d81370d08270e931aec4d814f74de2

Not committed because the AAR contains GPL-2.0 executables (libwg.so,
libwg-quick.so) that the app excludes from the APK, and because a binary built
on one machine cannot be verified by anyone else; the source and hash can.

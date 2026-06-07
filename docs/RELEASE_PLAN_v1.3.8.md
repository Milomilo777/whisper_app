# v1.3.8 RELEASE PLAN — owner-authorised 2026-06-07 (execute ONLY after macOS is green)

Owner instruction: FIRST wait until the macOS build is fully green (the macOS
session is greening ~2 remaining items in its harsher MANUAL workflows —
macos-harsh / macos-test-matrix / the `.app` build; the routine `macOS build
check` is already green). THEN release v1.3.8 to master and prune the old
release. **KEEP the `macos-ci` branch** (still needed for real-Mac testing —
do NOT delete it).

State: local `master` == `origin/macos-ci` (reconverged, tip ~`6e15098`+), which
carries EVERYTHING (this session's fixes + the macOS session's commits). pyright
`app core` 0/0/0; ~20-bug find-until-dry sweep converged; v1.3.8 artifacts built
with the bundled cloud key. `origin/master` is still `53fc8b2` (untouched).

When macOS is green, run (all pre-authorised in CLAUDE.md):

1. `git fetch origin` ; confirm local `master` == `origin/macos-ci` (rebase onto it if the macOS session pushed more).
2. MERGE TO MASTER = clean FAST-FORWARD (macos-ci descends from 53fc8b2):
   `git push origin master:master`
3. `git tag -a v1.3.8 -m "Whisper Project v1.3.8"` ; `git push origin v1.3.8`
4. `gh release create v1.3.8 "dist_installer/WhisperProject-v1.3.8-Setup-Standard.exe" "dist_installer/WhisperProject-v1.3.8-Portable.zip" --title "Whisper Project v1.3.8" --notes-file docs/RELEASE_NOTES_v1.3.8.md`
5. PRUNE (policy = keep only latest + basic): `gh release delete v1.3.7 --yes`
   — delete the GitHub RELEASE only; KEEP the `v1.3.7` git tag + local installers as backup.
   KEEP `basic-v0.1.0`. (Current releases: v1.3.7 [Latest] + basic-v0.1.0.)
6. Do NOT delete `macos-ci`.

Notes:
- The bundled Google Cloud service-account key IS inside the Windows Setup/Portable
  artifacts (intended trusted-distribution) but is NOT in git and NOT in the macOS CI `.app`.
- Artifacts at `dist_installer/WhisperProject-v1.3.8-{Setup-Standard.exe,Portable.zip}`;
  launch-smoke verified ("Whisper Project v1.3.8").

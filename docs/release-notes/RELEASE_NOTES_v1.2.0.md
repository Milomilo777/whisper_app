# Whisper Project v1.2.0

UX + accessibility release on top of v1.1.0. Install the **Setup-Standard**
EXE attached below; your settings and downloaded models are kept.

## New

- **Copy / paste works everywhere now.** A right-click menu (Copy / Cut
  / Paste / Select all) on every text field, plus a copyable log console
  (right-click → Copy / Copy all / Clear). It's mouse-driven, so it
  works no matter which keyboard layout is active.
- **Bulk queue actions.** Select several rows in the transcription or
  download queue (Ctrl / Shift-click) and Cancel / Re-run / Resume /
  Remove them all at once, instead of one by one.
- **Scrollable queues.** Both queue lists now show a vertical scrollbar
  when the list grows past the visible area (and hide it when it fits).
- **Model visibility + on-demand install.** The Advanced model picker
  marks each model "downloaded" / "needs download", and a "Download now"
  button installs the chosen model without starting a transcription.
- **Open file from the Download tab.** A finished download can be opened
  directly from its right-click menu (not just its folder).

## Fixed

- **Copy / paste under a non-English keyboard layout.** Ctrl+C / V / X /
  A were dead while a Persian (or other non-Latin) layout was active —
  they work now (and the right-click menus above don't depend on the
  layout at all).
- **Outputs no longer overwrite a previous run.** Re-transcribing a file
  writes `name (1).srt` / `name (1).json` instead of replacing the
  earlier files.
- **The About dialog** now shows the correct app version (it was stuck
  on an old number) and opens in a single click.

## Notes

- Only the **Setup-Standard** installer is published.
- The installer now registers a stable entry in Add/Remove Programs, so
  a newer version upgrades the previous one cleanly instead of stacking.
- Full technical detail: `docs/CHANGELOG.md`.

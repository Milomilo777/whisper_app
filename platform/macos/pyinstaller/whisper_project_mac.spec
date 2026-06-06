# whisper_project_mac.spec — macOS .app build for the PyInstaller pipeline.
#
# THIS IS THE THIRD SPEC COPY (see CLAUDE.md "Style & scope"): adding a new
# module means updating whisper_project_onefile.spec AND
# whisper_project_onedir.spec AND this file's hiddenimports / datas so none of
# the pipelines bit-rot. Its hiddenimports + datas are kept in lock-step with
# whisper_project_onedir.spec (the Windows onedir build); the ONLY differences
# are the macOS .app BUNDLE wrapper at the bottom and the icns icon.
#
# Run (ON A MAC — cannot be built on Windows/Linux):
#     pyinstaller --noconfirm --clean platform/macos/pyinstaller/whisper_project_mac.spec
#
# Output: dist/Whisper Project.app  (then wrap into a .dmg via builddmg.command).
#
# Packaging prerequisites on the Mac (see ../pyinstaller/README.md):
#   * put the MAC ffmpeg/ffprobe/ffplay (+ yt-dlp) in ./bin — NOT the .exe
#     ones. ffplay is what makes the Video Tiling tab work out of the box.
#   * optional: assets/whisper.icns for the Dock icon.
#
# The app's core.paths.resource_base() returns sys._MEIPASS inside the frozen
# .app bundle, which is where COLLECT lays out bin/ + the bundled data files —
# no source changes needed. bundled_binary() drops the .exe suffix off Windows,
# so it resolves bin/ffmpeg / bin/ffplay (no extension) on macOS.
# pyright: reportMissingImports=false

import os

from PyInstaller.utils.hooks import (
    collect_all,
    collect_data_files,
    collect_dynamic_libs,
)

# Same Silero VAD packaging note as the Windows specs: faster_whisper loads
# silero_vad_v6.onnx by file path at runtime, so PyInstaller's module
# collection alone is not enough.
faster_whisper_datas = collect_data_files('faster_whisper')

# pywhispercpp ships its native whisper.cpp extension as a TOP-LEVEL module
# `_pywhispercpp` at site-packages root. collect_dynamic_libs returns [] for
# that layout — use collect_all on both names to gather module + binary +
# datas. All wrapped in try/except so a slim build host without the opt-in
# deps doesn't break the spec.
whisper_cpp_datas = []
whisper_cpp_binaries = []
whisper_cpp_hidden = []
for _name in ('pywhispercpp', '_pywhispercpp'):
    try:
        d, b, h = collect_all(_name)
        whisper_cpp_datas.extend(d)
        whisper_cpp_binaries.extend(b)
        whisper_cpp_hidden.extend(h)
    except Exception:
        pass
try:
    whisper_cpp_binaries.extend(collect_dynamic_libs('pywhispercpp'))
except Exception:
    pass

# stable-ts (alignment) — bring its data files + transitive whisper +
# tiktoken so the bundled app can run alignment when the user enables it.
alignment_datas = []
alignment_binaries = []
alignment_hidden = []
for _name in ('stable_whisper', 'whisper', 'tiktoken'):
    try:
        d, b, h = collect_all(_name)
        alignment_datas.extend(d)
        alignment_binaries.extend(b)
        alignment_hidden.extend(h)
    except Exception:
        pass

# This spec lives in platform/macos/pyinstaller/. PyInstaller resolves a bare
# relative script path (e.g. 'gui.py') against the SPEC's own directory, not the
# CWD — which made the build fail with "gui.py not found". Resolve every
# repo-relative input against the repo root computed from SPECPATH so the build
# works regardless of the working directory.
_REPO_ROOT = os.path.abspath(os.path.join(SPECPATH, os.pardir, os.pardir, os.pardir))

# Dock icon — bundle assets/whisper.icns when present (see the README for how
# to generate it from whisper.png). None is fine; PyInstaller uses a default.
_icns = os.path.join(_REPO_ROOT, 'assets', 'whisper.icns')
_icon = _icns if os.path.isfile(_icns) else None

a = Analysis(
    [os.path.join(_REPO_ROOT, 'gui.py')],
    pathex=[_REPO_ROOT],
    binaries=[
        *whisper_cpp_binaries,
        *alignment_binaries,
    ],
    datas=[
        (os.path.join(_REPO_ROOT, 'bin'), 'bin'),
        (os.path.join(_REPO_ROOT, 'assets'), 'assets'),
        # Static page served by the optional LAN/web HTTP job server
        # (gui.py serve -> core.server). Ship it so the frozen build can
        # serve the browser UI.
        (os.path.join(_REPO_ROOT, 'core', 'server', 'static'), 'core/server/static'),
        # SMTV transcription writer's bundled Word template (the team's
        # exact table styling). Resolved at runtime via
        # core.paths.resource_base -> core/writers/templates/.
        (os.path.join(_REPO_ROOT, 'core', 'writers', 'templates'), 'core/writers/templates'),
        *faster_whisper_datas,
        *whisper_cpp_datas,
        *alignment_datas,
    ],
    hiddenimports=[
        *whisper_cpp_hidden,
        *alignment_hidden,
        'app',
        'app.app',
        'app.dialogs',
        'app.domain',
        'app.services',
        'app.widgets',
        'app.observability',
        'app.dialogs.advanced',
        'app.dialogs.hub_setup',
        'app.dialogs.model_download',
        'app.dialogs.statistics',
        'app.dialogs.transcript_viewer',
        'app.domain.languages',
        'app.domain.tasks',
        'app.services.download_service',
        'app.services.format_service',
        'app.services.integrations_service',
        'app.services.transcription_service',
        'app.widgets.console',
        'app.widgets.hardware_wizard',
        'app.widgets.platform',
        'app.widgets.tabs',
        'app.widgets.tray',
        'core',
        'core.alignment',
        'core.backends',
        'core.backends.base',
        'core.backends.faster_whisper_be',
        'core.backends.whisper_cpp',
        'core.backends.parakeet',
        'core.backends.cloud_stt',
        'core.backends.google_cloud_stt',
        'core.chapters',
        'core.llm',
        'core.recorder',
        'core.search',
        'core.separator',
        'core.tiling',
        'core.voiceprint',
        # Opt-in backends (see the Windows specs' comment).
        'pywhispercpp',
        'pywhispercpp.model',
        '_pywhispercpp',
        'stable_whisper',
        'whisper',
        'tiktoken',
        'core.burn_subs',
        'core.config',
        'core.convert',
        'core.diarization',
        'core.hallucination',
        'core.hardware',
        'core.history',
        'core.hub',
        'core.logging_setup',
        'core.model_manager',
        'core.monitors',
        'core.paths',
        'core.stats',
        'core.task',
        'core.transcriber',
        'core.updates',
        'core.watcher',
        'core.worker',
        'core.integrations.otranscribe',
        'core.integrations.smtv',
        # Optional LAN/web HTTP job server (stdlib only).
        'core.server',
        'core.server.httpd',
        'core.server.jobs',
        'core.writers',
        'core.writers.base',
        'core.writers.srt',
        'core.writers.vtt',
        'core.writers.tsv',
        'core.writers.txt',
        'core.writers.json_writer',
        'core.writers.lrc',
        'core.writers.md',
        'core.writers.docx_writer',
        'core.writers.pdf_writer',
        'core.writers.smtv_docx_writer',
        'docx',
        'reportlab',
        'sherpa_onnx',
        # Optional multi-monitor detection for Video Tiling. Lazy-imported in
        # core.monitors; on macOS this is the PREFERRED path (the ctypes Win32
        # fallback is a no-op off Windows), so list it so the frozen .app keeps
        # working multi-monitor detection. Its absence only degrades to a
        # single-monitor fallback.
        'screeninfo',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Whisper Project',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    # Build for the host arch by default. To ship one app for Intel + Apple
    # Silicon, build under a universal2 Python and set this to 'universal2'.
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=_icon,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='Whisper Project',
)
# macOS .app wrapper. Version is kept at 1.3.6 to match the Info.plist the
# install.command writes for the source/venv path — do NOT bump it here; the
# release version is governed by core.__version__ + the git tag, and the mac
# path is still unbuilt/untested on real hardware.
app = BUNDLE(
    coll,
    name='Whisper Project.app',
    icon=_icon,
    bundle_identifier='com.translation-robot.whisperproject',
    version='1.3.6',
    info_plist={
        'CFBundleName': 'Whisper Project',
        'CFBundleDisplayName': 'Whisper Project',
        'CFBundleIdentifier': 'com.translation-robot.whisperproject',
        'CFBundleVersion': '1.3.6',
        'CFBundleShortVersionString': '1.3.6',
        'CFBundlePackageType': 'APPL',
        'NSHighResolutionCapable': True,
        # The app reads media files the user drops / picks; declaring a
        # minimum system version keeps macOS from down-ranking the unsigned
        # bundle's file access.
        'LSMinimumSystemVersion': '11.0',
    },
)

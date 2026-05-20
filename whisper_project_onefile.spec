# whisper_project.spec — PyInstaller spec for the desktop app
#
# Run:
#     pyinstaller --noconfirm --clean whisper_project.spec
#
# Output: dist/WhisperProject.exe — a single self-contained file.
#
# At launch the runtime extracts every bundled binary/data file to a
# temporary directory exposed via sys._MEIPASS. The app reads bin/,
# ffmpeg/ffprobe/yt-dlp, and faster_whisper's Silero VAD ONNX through
# core/paths.py::resource_base() which prefers _MEIPASS in onefile mode.
#
# The same exe doubles as the worker subprocess via the --worker flag
# handled at the top of gui.py — each worker subprocess extracts its
# own _MEIPASS at start, which is the unavoidable cost of onefile.
# pyright: reportMissingImports=false

from PyInstaller.utils.hooks import collect_data_files

# faster_whisper ships a Silero VAD model under faster_whisper/assets/.
# It is loaded by file path at runtime (not via importlib.resources), so
# PyInstaller's default Python-module collection misses it. Without this,
# transcription crashes the worker with:
#   ONNXRuntimeError ... silero_vad_v6.onnx failed: File doesn't exist
# every time VAD is enabled (which is the default).
faster_whisper_datas = collect_data_files('faster_whisper')

a = Analysis(
    ['gui.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('bin', 'bin'),
        *faster_whisper_datas,
    ],
    hiddenimports=[
        'app',
        'app.app',
        'app.observability',
        'app.dialogs.advanced',
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
        'app.widgets.platform',
        'app.widgets.tabs',
        'core',
        'core.config',
        'core.diarization',
        'core.history',
        'core.logging_setup',
        'core.model_manager',
        'core.paths',
        'core.task',
        'core.transcriber',
        'core.worker',
        'core.integrations.otranscribe',
        'core.integrations.smtv',
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
        'docx',
        'sherpa_onnx',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

# Onefile layout: pass binaries + datas directly to EXE and omit COLLECT.
# Everything (DLLs, ffmpeg.exe, silero_vad_v6.onnx, the bin/ directory)
# is embedded in the exe and extracted to sys._MEIPASS on launch.
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='WhisperProject-v0.7.0-Portable',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

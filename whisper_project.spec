# whisper_project.spec — PyInstaller spec for the desktop app
#
# Run:
#     pyinstaller --noconfirm whisper_project.spec
#
# Output: dist/WhisperProject/WhisperProject.exe (one-dir layout).
# False-positive antivirus rate is dramatically lower on --onedir than on
# --onefile, so we deliberately stay one-dir.
#
# The same exe doubles as the worker subprocess via the --worker flag handled
# at the top of gui.py.
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
        'core.history',
        'core.logging_setup',
        'core.model_manager',
        'core.task',
        'core.transcriber',
        'core.worker',
        'core.integrations.otranscribe',
        'core.writers',
        'core.writers.base',
        'core.writers.srt',
        'core.writers.vtt',
        'core.writers.tsv',
        'core.writers.txt',
        'core.writers.json_writer',
        'core.writers.lrc',
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
    name='WhisperProject',
    console=False,
    icon=None,
    # Pre-6.x flat layout: place bundled data (bin/) and DLLs alongside the
    # exe, not inside _internal/. The app resolves bin/ via
    # dirname(sys.executable); without this, ffmpeg/ffprobe/yt-dlp end up at
    # dist/WhisperProject/_internal/bin/ and the exe silently can't find
    # them at runtime.
    contents_directory='.',
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name='WhisperProject',
)

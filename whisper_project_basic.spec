# whisper_project_basic.spec — PyInstaller spec, single-file portable.
#
# Run:
#     pyinstaller --noconfirm --clean whisper_project_basic.spec
#
# Output: dist/WhisperProjectBasic-Portable.exe
#
# The exe doubles as the worker subprocess via the --worker flag
# handled at the top of gui.py — each worker spawn re-extracts its
# own _MEIPASS, which is the unavoidable cost of onefile mode.
# pyright: reportMissingImports=false

from PyInstaller.utils.hooks import collect_data_files

# faster_whisper ships a Silero VAD model under faster_whisper/assets/.
# It's loaded by file path at runtime (not importlib.resources), so
# PyInstaller's default Python-module collection misses it. Without
# this, transcription crashes with:
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
        # Explicit submodule list so a one-line refactor doesn't
        # silently produce a broken exe. Mirror this list when
        # adding any new core/app module.
        'app',
        'app.app',
        'app.dialogs',
        'app.dialogs.about',
        'app.dialogs.crash',
        'app.dialogs.diagnose',
        'app.dialogs.hub_setup',
        'app.dialogs.model_download',
        'app.dialogs.model_loading',
        'app.dialogs.show_log',
        'app.widgets',
        'app.widgets.dropzone',
        'core',
        'core.config',
        'core.error_messages',
        'core.hardware',
        'core.health_check',
        'core.hub',
        'core.logging_setup',
        'core.model_manager',
        'core.paths',
        'core.task',
        'core.transcriber',
        'core.worker',
        'core.writers',
        'core.writers.json_writer',
        'core.writers.srt',
        'core.writers.txt',
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
    a.binaries,
    a.datas,
    [],
    name='WhisperProjectBasic-Portable',
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

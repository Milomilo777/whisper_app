# whisper_project_onedir.spec — onedir build for the installer pipeline.
#
# Run:
#     pyinstaller --noconfirm --clean --distpath dist_onedir whisper_project_onedir.spec
#
# Output: dist_onedir/WhisperProject/WhisperProject.exe + sibling files.
#
# This spec exists alongside whisper_project.spec (onefile) so the
# installer (Inno Setup) can package the directory layout without the
# bootloader extraction cost of onefile. Method A ships the onefile
# exe; Method B ships an installer built on top of this onedir tree.
#
# The app's core.paths.resource_base() falls through to
# dirname(sys.executable) when sys._MEIPASS is unset, which is exactly
# what onedir frozen layout requires — no source changes needed.
# pyright: reportMissingImports=false

from PyInstaller.utils.hooks import collect_data_files

# Same Silero VAD packaging note as whisper_project.spec: faster_whisper
# loads silero_vad_v6.onnx by file path at runtime, so PyInstaller's
# module collection alone is not enough.
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

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='WhisperProject',
    console=False,
    icon=None,
    # Flatten the bundle so bin/ and DLLs sit beside the exe rather than
    # under _internal/. core.paths.resource_base() resolves the bundled
    # bin/ from dirname(sys.executable) in onedir mode.
    contents_directory='.',
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name='WhisperProject',
)

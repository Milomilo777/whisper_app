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

from PyInstaller.utils.hooks import (
    collect_all,
    collect_data_files,
    collect_dynamic_libs,
)

# Same Silero VAD packaging note as whisper_project.spec: faster_whisper
# loads silero_vad_v6.onnx by file path at runtime, so PyInstaller's
# module collection alone is not enough.
faster_whisper_datas = collect_data_files('faster_whisper')

# pywhispercpp ships its native whisper.cpp .pyd as a TOP-LEVEL module
# `_pywhispercpp` at site-packages root. collect_dynamic_libs returns
# [] for that layout — use collect_all on both names to gather the
# module + binary + datas.
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
# tiktoken so the bundled exe can actually run alignment when the
# user enables it.
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

a = Analysis(
    ['gui.py'],
    pathex=[],
    binaries=[
        *whisper_cpp_binaries,
        *alignment_binaries,
    ],
    datas=[
        ('bin', 'bin'),
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
        'app.widgets.tray',
        'core',
        'core.alignment',
        'core.backends',
        'core.backends.base',
        'core.backends.faster_whisper_be',
        'core.backends.whisper_cpp',
        # Opt-in backends (see onefile spec comment).
        'pywhispercpp',
        'pywhispercpp.model',
        '_pywhispercpp',
        'stable_whisper',
        'whisper',
        'tiktoken',
        'core.burn_subs',
        'core.config',
        'core.diarization',
        'core.history',
        'core.logging_setup',
        'core.model_manager',
        'core.paths',
        'core.task',
        'core.transcriber',
        'core.watcher',
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
        'core.writers.pdf_writer',
        'docx',
        'reportlab',
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

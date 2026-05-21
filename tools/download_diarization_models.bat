@echo off
setlocal EnableDelayedExpansion
REM Download the two ONNX files the diarization pipeline needs.
REM Both come from k2-fsa/sherpa-onnx releases and are gitignored.
REM
REM   bin\diarization\segmentation.onnx — pyannote-segmentation-3.0
REM     (6.0 MB; sherpa-onnx ONNX export)
REM   bin\diarization\embedding.onnx   — 3D-Speaker CAMPlus EN
REM     (28 MB; trained on VoxCeleb, English-leaning)
REM
REM Run once before building any of the three deliverables. CI does
REM not run this — it's a build-time step like fetching ffmpeg.

set ROOT=%~dp0..
set OUT=%ROOT%\bin\diarization
set PS=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe

if not exist "%OUT%" mkdir "%OUT%"

if not exist "%OUT%\segmentation.onnx" (
    echo [diar] downloading pyannote-segmentation-3.0
    "%PS%" -NoProfile -Command "Invoke-WebRequest -UseBasicParsing -Uri 'https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2' -OutFile '%OUT%\segmentation.tar.bz2'"
    if errorlevel 1 (
        echo [diar] segmentation download failed
        exit /b 1
    )
    "%SystemRoot%\System32\tar.exe" -xjf "%OUT%\segmentation.tar.bz2" -C "%OUT%"
    move "%OUT%\sherpa-onnx-pyannote-segmentation-3-0\model.onnx" "%OUT%\segmentation.onnx" >nul
    move "%OUT%\sherpa-onnx-pyannote-segmentation-3-0\model.int8.onnx" "%OUT%\segmentation.int8.onnx" >nul
    rmdir /S /Q "%OUT%\sherpa-onnx-pyannote-segmentation-3-0"
    del "%OUT%\segmentation.tar.bz2"
)

if not exist "%OUT%\embedding.onnx" (
    echo [diar] downloading 3D-Speaker CAMPlus EN embedding
    "%PS%" -NoProfile -Command "Invoke-WebRequest -UseBasicParsing -Uri 'https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/3dspeaker_speech_campplus_sv_en_voxceleb_16k.onnx' -OutFile '%OUT%\embedding.onnx'"
    if errorlevel 1 (
        echo [diar] embedding download failed
        exit /b 2
    )
)

echo [diar] models ready in %OUT%
dir /b "%OUT%"
exit /b 0

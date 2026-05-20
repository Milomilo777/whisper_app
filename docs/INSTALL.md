# Installation Guide — Whisper Project

This guide is for someone who doesn't know Python or programming and just wants to install and use the application.

> Persian version below — برای راهنمای فارسی به انتهای فایل بروید.

---

## What you need

- **Windows 10 or 11** (64-bit)
- At least **8 GB RAM** (CPU); or an **NVIDIA GPU with CUDA** for 10× speedup
- About **5 GB free disk space** (1.5 GB app + 3 GB model + working space)
- Internet connection once for the model download (offline afterwards)

---

## Install — pick one of three methods

v0.7.0 ships three independent installers. Pick the one that fits.

| Method | File | Size | What it is |
|---|---|---|---|
| **Portable** | `WhisperProject-v0.7.0-Portable.exe` | 190 MB | A single file. Double-click and it runs. Nothing is installed; no shortcut, no Start Menu entry. Best for USB sticks or one-off use. |
| **Compact** | `WhisperProject-v0.7.0-Setup-Compact.exe` | 137 MB | An installer that unpacks the app to Program Files, adds a Start Menu shortcut and an Add/Remove Programs entry, and runs noticeably faster on startup. Best for everyday Windows users. |
| **Standard** | `WhisperProject-v0.7.0-Setup-Standard.exe` | 153 MB | Same shape as Compact but ships a full Python interpreter on disk so the entire source tree is browsable after install. Best for users who want transparency for debugging. |

All three transcribe a real video end-to-end on a clean Windows 10/11 x64 machine.

🔗 Download:
**https://github.com/Milomilo777/whisper_project_direct_download_v2/releases/latest**

### If you picked Portable

Move `WhisperProject-v0.7.0-Portable.exe` anywhere convenient
(`C:\Apps\`, your Desktop, a USB stick). Double-click to launch.
The first launch unpacks to a temporary folder under `%TEMP%`
(takes about 5–10 seconds). Subsequent launches feel about the
same — every launch re-unpacks.

### If you picked Compact or Standard

Double-click the `…-Setup-….exe` file. The installer:

1. Asks for admin rights (Yes).
2. Confirms an install location (`C:\Program Files\WhisperProject\`
   by default — change it if you like).
3. Optionally creates a desktop icon (checkbox on the wizard).
4. Installs. Compact takes ~20 s; Standard takes ~45 s.

After install: launch from the Start Menu under **Whisper Project**,
or from the desktop icon if you ticked the box. Uninstall from
**Settings → Apps → Whisper Project → Uninstall** or from the
folder's `unins000.exe`.

### First launch — common to all three methods

#### ⚠️ SmartScreen warning
Windows may show:
> "Windows protected your PC — Microsoft Defender SmartScreen prevented an unrecognized app from starting"

This is **normal** because the binary is not code-signed. To continue:
1. Click **More info**
2. The **Run anyway** button appears — click it

#### ⚠️ Model download dialog (one time, 3 GB)
On first launch, a "Whisper model required" dialog appears. Click **Download**.

The model is fetched from a CDN (≈3 GB). At average speeds this takes 10–30 minutes.

If the CDN download fails, you can install the model manually (see Troubleshooting below).

Once the download finishes, the app is ready to use.

---

## Usage

### Transcribe (audio/video → subtitles)

1. Open the **Transcribe** tab
2. **Browse** → pick an audio or video file (mp3, mp4, wav, m4a, mkv, …)
3. Click **Transcribe**
4. Watch the **Transcription Queue** tab for progress
5. When done, two files are written next to your input:
   - `<filename>.srt` — subtitle file
   - `<filename>.json` — segments with precise timestamps

### Download Videos (from YouTube and other sites)

1. **Download Videos** tab
2. Paste the video URL
3. **Browse** next to "Folder" → choose the destination
4. For audio only, change format to mp3/m4a
5. Click **Download**

If "Auto-transcribe after download" is enabled in Advanced, the downloaded file is transcribed automatically.

### oTranscribe round-trip (text editing)

1. After a successful transcription, go to **Transcription Queue**
2. **Right-click** the row → **Export → oTranscribe (.otr)**
3. Open the `.otr` file at https://otranscribe.com, edit, export
4. Back to the **Transcribe** tab → **Import .otr → SRT...**

---

## Troubleshooting

### "MSVCP140.dll is missing" or a similar DLL error

Install the Visual C++ Redistributable from Microsoft:
🔗 https://aka.ms/vs/17/release/vc_redist.x64.exe

This is free and usually already installed on Windows 10/11.

### The exe won't run — antivirus removes it

PyInstaller-built binaries are sometimes flagged as tampered by antivirus engines. Fix:
1. Open Windows Security → Virus & threat protection → Exclusions
2. Add the `WhisperProject\` folder as an exclusion
3. Re-extract the ZIP

### "Model folder missing" or "Existing model failed to load"

Re-trigger the model-download dialog from the app. If it still fails, install the model manually:

```powershell
pip install huggingface_hub
python -c "from huggingface_hub import snapshot_download; snapshot_download('Systran/faster-whisper-large-v3', local_dir=r'C:\Users\YOUR_USER\AppData\Local\WhisperProject\Cache\models\models--Systran--faster-whisper-large-v3')"
```

(Replace `YOUR_USER` with your Windows username.)

This needs **Python**, installable from https://python.org (tick "Add to PATH" during install).

### Transcription is very slow

- The default model is `large-v3` (large). On CPU with int8 it takes about 2–3× the audio length.
- If you have an NVIDIA GPU with CUDA: Advanced → device → cuda; compute_type → float16. Speedup is 10×–20×.
- Or use a smaller model (edit `config.json` at `%LOCALAPPDATA%\WhisperProject\config.json` by hand).

### The app crashes

Log path: `%LOCALAPPDATA%\WhisperProject\Logs\app.log`

Paste that file into a GitHub issue along with a short description of what you were doing.

---

## Build from source (for developers)

If you want to build it yourself from source:

```cmd
git clone https://github.com/Milomilo777/whisper_project_direct_download_v2
cd whisper_project_direct_download_v2

REM Prerequisites
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install pyinstaller

REM Download ffmpeg / ffprobe / yt-dlp into bin/
REM Files from:
REM   https://www.gyan.dev/ffmpeg/builds/  (release essentials)
REM   https://github.com/yt-dlp/yt-dlp/releases/latest

REM Build
build.bat clean
```

Output: `dist\WhisperProject\WhisperProject.exe`

More detail: [docs/BUILD.md](BUILD.md)

---
---

# راهنمای نصب — Whisper Project (فارسی)

این راهنما برای کسی است که Python یا برنامه‌نویسی بلد نیست و فقط می‌خواهد برنامه را نصب کند و استفاده کند.

---

## آنچه نیاز دارید

- **Windows 10 یا 11** (نسخه 64-bit)
- حداقل **8 GB RAM** (CPU)؛ یا یک **NVIDIA GPU با CUDA** برای سرعت ۱۰ برابر
- حدود **5 GB فضای خالی** روی دیسک (1.5 GB برنامه + 3 GB مدل + جای کاری)
- اتصال اینترنت یک بار برای دانلود مدل (بعد از آن آفلاین کار می‌کند)

---

## نصب — یکی از سه روش را انتخاب کنید

نسخه ۰.۷.۰ سه installer جداگانه دارد. یکی را که با نیاز شما هماهنگ است انتخاب کنید.

| روش | فایل | اندازه | چه چیزی است |
|---|---|---|---|
| **Portable** | `WhisperProject-v0.7.0-Portable.exe` | ۱۹۰ مگابایت | یک فایل تنها. دوبار کلیک کنید تا اجرا شود. هیچ نصبی ندارد، نه shortcut نه Start Menu. مناسب برای USB یا استفاده موقت. |
| **Compact** | `WhisperProject-v0.7.0-Setup-Compact.exe` | ۱۳۷ مگابایت | installer که اپ را در Program Files باز می‌کند، یک shortcut در Start Menu و یک ورودی در Add/Remove Programs می‌سازد و start-up سریع‌تری دارد. مناسب کاربر معمولی ویندوز. |
| **Standard** | `WhisperProject-v0.7.0-Setup-Standard.exe` | ۱۵۳ مگابایت | شبیه Compact است اما یک Python interpreter کامل روی disk می‌گذارد، پس کل source tree بعد از نصب قابل مرور است. مناسب کاربرانی که شفافیت برای debug می‌خواهند. |

هر سه روش یک ویدئوی واقعی را روی یک ماشین ویندوز ۱۰/۱۱ تمیز end-to-end transcribe می‌کنند.

🔗 دانلود:
**https://github.com/Milomilo777/whisper_project_direct_download_v2/releases/latest**

### اگر Portable را انتخاب کردید

فایل `WhisperProject-v0.7.0-Portable.exe` را هر جا که می‌خواهید بگذارید
(`C:\Apps\`، Desktop، یا USB). دوبار کلیک کنید. اولین اجرا حدود ۵ تا ۱۰
ثانیه طول می‌کشد چون فایل خودش را در یک پوشه‌ی موقت زیر `%TEMP%` باز
می‌کند. هر بار اجرا همین زمان را می‌گیرد.

### اگر Compact یا Standard را انتخاب کردید

روی فایل `…-Setup-….exe` دوبار کلیک کنید. Installer:

۱. اجازه‌ی admin می‌خواهد (Yes بزنید).
۲. محل نصب را تأیید می‌کند (پیش‌فرض: `C:\Program Files\WhisperProject\`).
۳. اختیاری: یک desktop icon می‌سازد.
۴. نصب می‌کند. Compact حدود ۲۰ ثانیه، Standard حدود ۴۵ ثانیه.

پس از نصب: از Start Menu زیر **Whisper Project** یا از دسکتاپ اجرا کنید.
حذف از **Settings → Apps → Whisper Project → Uninstall** یا از فایل
`unins000.exe` در پوشه‌ی نصب.

### اولین اجرا — برای هر سه روش یکسان

#### ⚠️ هشدار SmartScreen
ویندوز ممکن است پیامی به این شکل نمایش دهد:
> "Windows protected your PC — Microsoft Defender SmartScreen prevented an unrecognized app from starting"

این **عادی** است چون فایل امضای رسمی شرکت ندارد. برای ادامه:
1. روی **More info** کلیک کنید
2. دکمه‌ی **Run anyway** ظاهر می‌شود — کلیک کنید

#### ⚠️ دیالوگ دانلود مدل (یک بار، 3 GB)
در اولین اجرا، دیالوگ "Whisper model required" ظاهر می‌شود. روی **Download** کلیک کنید.

مدل از یک CDN دانلود می‌شود (تقریباً 3 GB). در سرعت متوسط ۱۰–۳۰ دقیقه طول می‌کشد.

اگر دانلود از CDN اصلی شکست خورد، می‌توانید مدل را دستی نصب کنید (راهنما در پایین این فایل).

پس از تکمیل دانلود، اپ آماده استفاده است.

---

## استفاده

### Transcribe (تبدیل صدا/ویدئو به زیرنویس)

1. تب **Transcribe** را باز کنید
2. **Browse** → فایل صوتی یا ویدئویی (mp3, mp4, wav, m4a, mkv, ...) را انتخاب کنید
3. **Transcribe** را بزنید
4. تب **Transcription Queue** را ببینید برای پیشرفت کار
5. وقتی تمام شد، دو فایل کنار فایل ورودی شما نوشته می‌شوند:
   - `<نام-فایل>.srt` — زیرنویس
   - `<نام-فایل>.json` — داده‌ها با timestamp دقیق

### Download Videos (دانلود از YouTube و سایت‌های دیگر)

1. تب **Download Videos**
2. URL ویدئو را paste کنید
3. **Browse** کنار "Folder" → پوشه‌ی مقصد را انتخاب کنید
4. اگر می‌خواهید فقط صدا، format را به mp3/m4a تغییر دهید
5. **Download** را بزنید

اگر گزینه‌ی "Auto-transcribe after download" در Advanced فعال باشد، بعد از دانلود خودکار transcribe می‌شود.

### oTranscribe round-trip (ویرایش متن)

1. بعد از یک transcribe موفق، تب **Transcription Queue**
2. روی ردیف **right-click** → **Export → oTranscribe (.otr)**
3. فایل `.otr` را در https://otranscribe.com باز کنید، ویرایش کنید، export کنید
4. به تب **Transcribe** برگردید → **Import .otr → SRT...**

---

## رفع اشکال

### "MSVCP140.dll is missing" یا خطای مشابه DLL

نصب پکیج Visual C++ Redistributable از مایکروسافت:
🔗 https://aka.ms/vs/17/release/vc_redist.x64.exe

این رایگان است و معمولاً روی Windows 10/11 از قبل نصب است.

### EXE اجرا نمی‌شود — Antivirus حذفش می‌کند

PyInstaller-built EXEها گاهی توسط آنتی‌ویروس به اشتباه به عنوان tampered شناسایی می‌شوند. راه‌حل:
1. در Windows Security → Virus & threat protection → Exclusions
2. پوشه‌ی `WhisperProject\` را به عنوان exclusion اضافه کنید
3. ZIP را دوباره Extract کنید

### "Model folder missing" یا "Existing model failed to load"

دیالوگ دانلود مدل را دوباره اجرا کند. اگر باز هم کار نکرد، روش دستی:

```powershell
pip install huggingface_hub
python -c "from huggingface_hub import snapshot_download; snapshot_download('Systran/faster-whisper-large-v3', local_dir=r'C:\Users\YOUR_USER\AppData\Local\WhisperProject\Cache\models\models--Systran--faster-whisper-large-v3')"
```

(جای `YOUR_USER` نام کاربری ویندوز خودتان را بگذارید.)

این نیاز به **Python** دارد که از https://python.org نصب می‌شود (هنگام نصب گزینه‌ی "Add to PATH" را تیک بزنید).

### Transcribe خیلی کند است

- مدل پیش‌فرض `large-v3` است (بزرگ). روی CPU با int8 حدود ۲–۳ برابر طول صدا طول می‌کشد.
- اگر کارت گرافیک NVIDIA با CUDA دارید: Advanced → device → cuda؛ compute_type → float16. سرعت ۱۰× تا ۲۰× می‌شود.
- یا از مدل کوچک‌تر استفاده کنید (نیاز به ویرایش دستی `config.json` در `%LOCALAPPDATA%\WhisperProject\config.json`).

### اپ بسته می‌شود (crash)

مسیر لاگ: `%LOCALAPPDATA%\WhisperProject\Logs\app.log`

این فایل را در یک issue روی GitHub paste کنید با یک توضیح کوتاه از کاری که می‌کردید.

---

## بیلد از سورس (برای توسعه‌دهندگان)

اگر می‌خواهید خودتان از سورس بیلد کنید:

```cmd
git clone https://github.com/Milomilo777/whisper_project_direct_download_v2
cd whisper_project_direct_download_v2

REM پیش‌نیازها
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install pyinstaller

REM دانلود ffmpeg / ffprobe / yt-dlp به پوشه bin/
REM فایل‌ها از:
REM   https://www.gyan.dev/ffmpeg/builds/  (release essentials)
REM   https://github.com/yt-dlp/yt-dlp/releases/latest

REM بیلد
build.bat clean
```

خروجی: `dist\WhisperProject\WhisperProject.exe`

برای جزئیات بیشتر: [docs/BUILD.md](BUILD.md)

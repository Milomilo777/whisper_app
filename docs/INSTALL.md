# راهنمای نصب — Whisper Project

این راهنما برای کسی است که Python یا برنامه‌نویسی بلد نیست و فقط می‌خواهد برنامه را نصب کند و استفاده کند.

---

## آنچه نیاز دارید

- **Windows 10 یا 11** (نسخه 64-bit)
- حداقل **8 GB RAM** (CPU)؛ یا یک **NVIDIA GPU با CUDA** برای سرعت ۱۰ برابر
- حدود **5 GB فضای خالی** روی دیسک (1.5 GB برنامه + 3 GB مدل + جای کاری)
- اتصال اینترنت یک بار برای دانلود مدل (بعد از آن آفلاین کار می‌کند)

---

## نصب در ۳ مرحله

### مرحله ۱ — دانلود نسخه آماده

از پیج Releases مخزن، آخرین نسخه را دانلود کنید:

🔗 **https://github.com/Milomilo777/whisper_project_direct_download_v2/releases/latest**

فایلی به نام `WhisperProject-v0.6.0-windows-x64.zip` (تقریباً 450 MB) دانلود کنید.

### مرحله ۲ — Extract و انتخاب محل

ZIP را Extract کنید در یک پوشه دلخواه، **ترجیحاً نه روی Desktop**. مثال‌های خوب:
- `C:\Apps\WhisperProject\`
- `D:\Programs\WhisperProject\`

پس از Extract، باید این ساختار را داشته باشید:
```
WhisperProject\
├── WhisperProject.exe       ← این را اجرا می‌کنید
├── bin\                     ← ffmpeg / ffprobe / yt-dlp
├── faster_whisper\          ← مدل VAD
├── ctranslate2\             ← engine اصلی
├── (تعداد زیادی DLL)
└── _internal\               ← (اختیاری بسته به نسخه)
```

⚠️ **خود `WhisperProject.exe` را تنها کپی نکنید** — بدون DLLها و پوشه‌ها کار نمی‌کند.

### مرحله ۳ — اولین اجرا

روی `WhisperProject.exe` دوبار کلیک کنید.

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
دیالوگ دانلود مدل را دوباره اجرا می‌کند. اگر باز هم کار نکرد، روش دستی:

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

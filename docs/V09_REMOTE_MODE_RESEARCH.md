# v0.9 Remote-Mode Research — Burst compute روی سرور GPU

این فایل تحقیقات دو شارد موازی است: یکی برای cloud GPU providers +
pricing + APIs، دیگری برای remote architecture + non-tech UX patterns.
هدف: یک طراحی برای حالت "دکمه بزن، سرور بگیر، transcribe کن، tear
down" که برای کاربر غیرفنی به سادگی paste کردن یک API key است.

## TL;DR — تصمیم پیشنهادی

**Stack**: RunPod Community Cloud (RTX 4090 $0.34/hr، per-ms billing،
Python SDK، SOC 2 Type II) به‌عنوان provider اصلی.

**معماری**: SSH + SFTP + همان `core/worker.py` فعلی روی remote، با
**JSON-stdio روی کانال SSH** — کد worker دست نمی‌خورد، فقط transport
عوض می‌شود (الگوی VS Code Remote-SSH).

**UX**: ویزارد ۵ مرحله‌ای، password یک‌بار، اپ خودش SSH key تولید و
push می‌کند، بعد از آن کاربر هرگز password نمی‌دهد.

**کوچک‌ترین MVP**: فقط BYO mode + password + SSH key auto-push — **۲
هفته کار، ۸۰٪ ارزش با ۲۰٪ تلاش**.

**پیام marketing**: «۱۰۰ ساعت صوت = ~$۳ GPU، فقط در زمان مصرف».

---

## ۱. مقایسه‌ی ارائه‌دهندگان (۲۰۲۶)

| Provider | RTX 4090 | RTX 3090 | A100 80GB | L40S | H100 | Billing | API Quality |
|---|---|---|---|---|---|---|---|
| **RunPod (Community)** | $0.34/hr | ~$0.22 | $1.19/hr | $1.90/hr | ~$2.49 | per-ms | Excellent: Python SDK + GraphQL + runpodctl CLI + SSH |
| RunPod (Secure) | $0.59/hr | n/a | ~$2.49 | ~$2.49 | ~$2.99 | per-ms | same |
| **Vast.ai** | $0.31/hr | $0.13/hr | ~$0.75 | ~$1.20 | ~$1.65 | per-sec | Excellent: `pip install vastai` (SDK+CLI in one) |
| Lambda Labs | n/a | n/a | $1.29/hr | n/a | $2.49-2.99 | per-min | REST API، no spot، 4090/3090 ندارد |
| Modal | n/a | n/a | $3.73/hr | n/a | $3.95/hr | per-sec | Container-only، SSH ندارد |
| **Replicate** | n/a | n/a | n/a | n/a | n/a | per-run | Highest-level: HTTP POST audio in, JSON out |
| Hyperbolic | $0.50/hr | n/a | $1.80/hr | n/a | $3.00-3.20 | per-hr | OpenAI-compatible API |
| TensorDock | $0.35/hr | n/a | $0.75-1.20 | n/a | $1.91-2.25 | per-hr | REST، KVM (Windows OK)، spot |
| Hetzner GEX44 | RTX-4000 Ada 20GB | — | — | — | — | monthly | SSH/bare-metal، API for ad-hoc ندارد |
| Hetzner GEX131 | RTX PRO 6000 Blackwell | — | — | — | — | monthly | same |

**برنده‌ها**: RunPod Community + Vast.ai مارکت‌پلیس‌ها هستند و با
اختلاف زیاد ارزان‌ترین.

---

## ۲. واقعیت هزینه (۱۰۰ ساعت صوت)

```
Hardware          Wall-clock    GPU $/hr    Total cost (audio-only)
---------------   -----------   ---------   -----------------------
i7 CPU (local)    200-300 hr    $0          free but slow
RTX 3090 cloud    8-12 hr       $0.22       $2-3
RTX 4090 cloud    5-8 hr        $0.34       $2-3
A100 80GB         2-4 hr        $1.19       $3-5
L40S              2-4 hr        $1.90       $4-8
H100              1-2 hr        $2.49       $3-5
```

**پیام marketing**: «۱۰۰ ساعت صوت ≈ $۳ GPU روی RTX 4090. ۱۰۰۰ ساعت
زیر $۳۰. فقط در زمان مصرف.»

**SaladCloud benchmark** (مرجع جانبی): گزارش رسمی ادعا می‌کند ۱
میلیون ساعت صوت با large-v3 معادل $۵۱۱۰ روی شبکه‌ی RTX 3060 های
خانگی است — ~۰.۵ سنت در هر ساعت صوت. این نشان می‌دهد لایه‌ی پایین‌رده
هم برای backlog های بزرگ منطقی است.

---

## ۳. سه طعم برای کاربر در یک ویزارد

```
Settings → Remote processing →
  ┌───────────────────────────────────────────┐
  │ □ سرور خودم را دارم (BYO)                │
  │   host + user + password یا key file      │
  │                                           │
  │ □ به من سرور ابری بگیر (Managed)         │
  │   فقط API key از RunPod                   │
  │                                           │
  │ □ از free tier API استفاده کن (Fallback)  │
  │   HuggingFace Inference / Replicate       │
  └───────────────────────────────────────────┘
```

### BYO (Bring-Your-Own-Server)

کاربر یک سرور Hetzner / Vast.ai / RunPod / لپ‌تاپ-خانگی-GPU دارد. اپ
از طریق SSH + Paramiko وصل می‌شود، bootstrap اجرا می‌کند، worker را
نصب می‌کند، job ها را می‌فرستد.

### Managed (مدیریت‌شده توسط اپ)

کاربر فقط RunPod API key می‌گذارد. اپ خودش pod ایجاد می‌کند، job ها
را اجرا می‌کند، در پایان terminate می‌کند. هزینه live نمایش داده
می‌شود.

### Fallback API

برای کاربری که نمی‌خواهد pod مدیریت کند: `Replicate
victor-upmeet/whisperx` HTTP POST. هر فایل ~$۰.۰۰۲ یعنی per-file
billing. ساده‌ترین UX ولی hotwords / initial_prompt محدود.

---

## ۴. ۵ صفحه ویزارد (UX کامل)

**صفحه ۱ — Toggle در Settings**
کاربر «پردازش راه دور» را فعال می‌کند. ویزارد ماژوله باز می‌شود.
هیچ اتصال شبکه‌ای رخ نداده.

**صفحه ۲ — انتخاب طعم**
سه دکمه‌ی بزرگ (BYO / Managed / Fallback). توضیح کوتاه هر کدام +
هزینه تقریبی + GDPR badge.

**صفحه ۳ — ورود credential**
چهار فیلد BYO: host، port (پیش‌فرض 22)، username، یکی از password
یا upload key file. در پس‌زمینه به محض submit:

1. اتصال SSH تست می‌شود
2. سیستم‌عامل ریموت تشخیص داده می‌شود (`cat /etc/os-release`)
3. اپ یک کلید RSA 4096 محلی تولید می‌کند، public را در
   `~/.ssh/authorized_keys` ریموت می‌نویسد، password از حافظه پاک
   می‌شود (الگوی `ssh-copy-id`)
4. private key در Windows Credential Manager (DPAPI) از طریق `keyring`
   ذخیره می‌شود

**از این لحظه به بعد کاربر هرگز password نخواهد داد.**

**صفحه ۴ — Bootstrap + تخمین هزینه**
نوار پیشرفت با چهار گام: «بررسی GPU» → «نصب ffmpeg» → «نصب
faster-whisper» → «دانلود مدل». لاگ verbose قابل گسترش است.

اگر BYO باشد هزینه نشان داده نمی‌شود؛ اگر Managed باشد بر اساس نرخ
provider:

```
RTX 4090 RunPod Community: $0.34/hr
A100 80GB:                 $1.19/hr
H100:                      $2.49/hr
```

**صفحه ۵ — تایید + badge "remote: hetzner-gpu1"**
ویزارد بسته می‌شود. در پنل اصلی یک badge کوچک نشان می‌دهد کجا کار
می‌رود. هر کار جدید به remote route می‌شود، با نوار وضعیت سه‌حالته:
upload → transcribe → download.

---

## ۵. معماری: SSH + SFTP + JSON-stdio (الگوی VS Code Remote-SSH)

**چرا این انتخاب؟**

- VS Code Remote-SSH (الگوی طلایی) دقیقاً همین کار را می‌کند: دو
  اتصال SSH باز، یک کارگر روی `$HOME/.vscode-server` نصب، تونل پورت
  SSH برای RPC.
- JetBrains Gateway همان الگو + TLS 1.3 درون تونل SSH (overkill اختیاری).
- چرا نه REST خالص؟ کاربر غیرفنی نمی‌خواهد TLS cert بسازد / port
  forward کند / nginx بنویسد.
- چرا نه Modal/container-only؟ معماری ما را عوض می‌کند، queue ادامه‌دار
  ما را می‌شکند.
- **بزرگ‌ترین برد**: همان `core/worker.py` فعلی روی remote کار می‌کند
  — فقط transport عوض می‌شود.

**جزئیات لایه‌ها**:

```
┌──────────────────────────────────────────────────────┐
│  Windows desktop (Tk GUI + queue + history.db)       │
│                                                      │
│  ┌────────────────────────────────────────┐         │
│  │ Paramiko: SSH client + SFTP            │         │
│  │ Multi-worker: 4 Transport channels     │         │
│  └────────────────────────────────────────┘         │
└────────────────┬─────────────────────────────────────┘
                 │ SSH (AES-256-GCM)
                 │ optional: Tailscale WireGuard layer
                 ▼
┌──────────────────────────────────────────────────────┐
│  Remote GPU server (Ubuntu + nvidia-smi)             │
│                                                      │
│  /opt/whisper-remote/                                │
│    venv/                  ← faster-whisper, stable-ts│
│    models/large-v3.bin    ← pre-downloaded, mounted  │
│    jobs/<uuid>/           ← per-job dir, auto-delete │
│    worker.py              ← same core/worker.py      │
│  systemd unit: whisper-remote.service                │
└──────────────────────────────────────────────────────┘
```

**Transport per file type**:

- **آپلود audio**: SFTP با chunk-resume. حجم ۱۰-۵۰۰ MB روی ۵۰ Mbit
  خانگی = ۲-۸۰ ثانیه.
- **ارسال job + receive status**: همان JSON-stdio روی یک کانال SSH
  exec. **هیچ تغییری در worker code**.
- **مدل وزن‌ها**: یک‌بار pre-download روی persistent volume، نه per-job.

**Multi-worker parallelism**: Paramiko ControlMaster (OpenSSH
multiplexing) را پشتیبانی نمی‌کند — برای ۴ کارگر موازی باید ۴
Transport جدا داشت. هزینه‌ی کمی است.

---

## ۶. Bootstrap script (idempotent)

```bash
set -e
test -d /opt/whisper-remote || mkdir -p /opt/whisper-remote
which ffmpeg || apt-get install -y ffmpeg
test -d /opt/whisper-remote/venv || python3 -m venv /opt/whisper-remote/venv
/opt/whisper-remote/venv/bin/pip install --upgrade \
    faster-whisper==<pinned> ctranslate2==<pinned>
test -f /opt/whisper-remote/models/large-v3.bin \
    || /opt/whisper-remote/venv/bin/python -m download_model large-v3
systemctl --user list-unit-files | grep -q whisper-remote \
    || cp whisper-remote.service ~/.config/systemd/user/
systemctl --user enable --now whisper-remote
```

هر بار اجرا فقط delta را تغییر می‌دهد.

**روش push worker** — سه گزینه:

1. **`pip install whisper-remote-worker` از PyPI** — توصیه‌شده.
   به‌روزرسانی ساده، signed wheel، نسخه‌بندی واضح.
2. `git clone` از مخزن عمومی — ساده اما به اعتماد به GitHub وابسته
   است.
3. scp کل tarball — بدترین، به نسخه‌ی محلی اپ گره می‌خورد.

**نسخه‌بندی**: یک فایل `version.json` در `/opt/whisper-remote/`
نوشته می‌شود. اپ هنگام اتصال آن را می‌خواند، اگر کوچک‌تر از
`minimum_required` باشد reinstall می‌کند.

**حالت "دو نسخه‌ی متفاوت"**: suffix → `/opt/whisper-remote-v0.9/` و
`/opt/whisper-remote-v1.0/` با systemd unit جدا.

---

## ۷. حالت‌های شکست — پیام انسانی

| ریشه‌ی فنی | پیغام به کاربر |
|---|---|
| SSH timeout | «سرور پاسخ نمی‌دهد. host و port را بررسی کنید» + دکمه‌ی retry |
| auth failed | «نام کاربری یا رمز نادرست است» (بدون افشای detail) |
| nvidia-smi missing | «این سرور GPU ندارد — می‌توانید با CPU ادامه دهید؟» |
| disk full روی remote | «روی سرور حافظه‌ی کافی نیست (نیاز: ۸ GB، موجود: ۲ GB)» |
| upload dropped | resume خودکار، بعد از ۳ تلاش fallback به local |
| لپ‌تاپ بسته شد | **کار روی remote ادامه می‌یابد** (systemd persistent). در reopen، اپ status را poll می‌کند و result را pull می‌کند. **این feature است نه bug** — مشابه VS Code که server روی remote persistent است. |
| installation failed | "show full log" در دیالوگ + دکمه‌ی "report to GitHub" که issue خودکار باز می‌کند |

---

## ۸. امنیت — privacy-first اصول حفظ شد

- **در ترانزیت**: SSH AES-256-GCM. اگر Tailscale انتخاب شده باشد، لایه‌ی
  WireGuard اضافه می‌شود (overkill عمدی).
- **روی سرور**: فایل‌ها در `/opt/whisper-remote/jobs/<uuid>/` با mode
  0700، auto-delete بعد از ۲۴ ساعت. مدل وزن‌ها read-only mounted.
- **روی Windows**:
  - private SSH key در DPAPI از طریق `keyring` package
  - password اولیه فقط ۳۰ ثانیه در حافظه (برای key push)، سپس wiped
  - history.db رمز نمی‌شود اما tags حساس را hash می‌کند
- **revocation**: کلید عمومی pushed شده با comment
  `whisper-remote@<host>-<install-id>` تا کاربر بتواند بعداً دستی revoke
  کند

---

## ۹. حریم خصوصی و انطباق per provider

| Provider | At-rest encryption | EU region | SOC 2 | GDPR | HIPAA |
|---|---|---|---|---|---|
| **RunPod Community** | yes | yes | Type II ✓ (2026) | ✓ | ✓ |
| Vast.ai | host-dependent (متنوع) | varies | no | risky | no |
| Lambda Labs | yes | yes | Type II ✓ | ✓ | — |
| Hetzner | yes | yes (DE/FI) | ISO 27001 | ✓ default | — |
| Genesis Cloud | yes | EU-native | ✓ | ✓ | — |

**برای کاربر اروپایی** (داده‌های حساس): RunPod EU region یا Hetzner.
**Vast.ai مناسب نیست** برای داده‌های حساس به دلیل تنوع host.

---

## ۱۰. UX رقبا — چه‌کاری می‌کنند

**MacWhisper Pro** (مرجع طلایی):
- صفحه‌ای در تنظیمات با نام "Cloud Transcription"
- کاربر کلید API ارائه‌دهنده‌ی انتخابی را paste می‌کند
- اعتبارنامه‌ها در macOS Keychain
- جریان: paste-key → toggle on → drag audio → done

**Sonix**: B2B SaaS، نه desktop. self-hosted GPU ندارد. Skip.

**Whispering, Aqua Voice**: عمدتاً local + Groq/ElevenLabs fallback.

**نتیجه**: یک toggle "Use cloud GPU" + Windows Credential Manager
storage + تخمین هزینه قبل از submit کافی است.

---

## ۱۱. ابزارهای کلیدی برای پیاده‌سازی

- `paramiko` — SSH + SFTP, MIT licensed
- `keyring` — Windows Credential Manager (DPAPI) integration
- `runpod` — Python SDK رسمی، MIT
- `vastai` — CLI + SDK در یک package
- `replicate` — Python SDK رسمی برای HTTP API
- `tailscale` — Python package روی PyPI برای ephemeral nodes (اختیاری
  برای NAT'd home servers)

---

## ۱۲. تخمین تلاش + cut-down v0.9

**M-L scale**: ۴-۶ هفته مهندس تمام‌وقت برای v0.9 کامل.

**شکست هفته‌به‌هفته**:

- هفته ۱: Paramiko + SFTP + sessionful execution
- هفته ۲: bootstrap idempotent + systemd + version detection
- هفته ۳: UX wizard ۵ مرحله‌ای + Windows Credential Manager
- هفته ۴: handling قطع شدن، resume، تست end-to-end با Hetzner واقعی
- هفته ۵-۶: managed path روی RunPod + Replicate fallback

**کوچک‌ترین MVP** (۲۰٪ کار، ۸۰٪ ارزش): **فقط BYO + password + SSH
key auto-push**.

- کاربر host + رمز می‌دهد
- اپ کلید SSH می‌سازد و push می‌کند
- bootstrap idempotent اجرا می‌شود
- transcription با همان JSON-stdio روی `ssh exec` می‌رود
- **هیچ Tailscale، هیچ managed cloud، هیچ REST**
- ۲ هفته کار

**مسیر پیشنهادی تکاملی**:

1. **v0.8**: BYO mode فقط (۲ هفته)
2. **v0.9**: Managed RunPod اضافه (۴ هفته)
3. **v1.0**: Tailscale overlay برای NAT'd home servers (۲ هفته)
4. **هرگز**: managed Modal + multi-cloud abstraction layer
   (over-engineering)

این مسیر، پروژه را از «یک Whisper desktop tool» به «desktop +
burst-compute on demand» تبدیل می‌کند بدون اینکه نقطه قوت offline +
privacy-first را از دست بدهد.

---

## ۱۳. مراجع کلیدی (~۴۰ منبع جمع شد، انتخاب مهم‌ترین‌ها)

### Cloud providers
- [RunPod Pricing](https://www.runpod.io/pricing)
- [RunPod Serverless Pricing Docs](https://docs.runpod.io/serverless/pricing)
- [RunPod Python SDK on GitHub](https://github.com/runpod/runpod-python)
- [runpod-workers/worker-faster_whisper](https://github.com/runpod-workers/worker-faster_whisper)
- [RunPod Security & Compliance](https://docs.runpod.io/references/security-and-compliance)
- [RunPod SOC 2 Type II Announcement](https://www.runpod.io/blog/runpod-achieves-soc-2-type-ii-certification)
- [Vast.ai Pricing](https://vast.ai/pricing)
- [Vast.ai Python SDK Quickstart](https://docs.vast.ai/sdk/python/quickstart)
- [Vast.ai CLI on GitHub](https://github.com/vast-ai/vast-cli)
- [Lambda Labs Pricing](https://lambda.ai/pricing)
- [Hetzner GEX44 — RTX 4000 Ada 20GB](https://www.hetzner.com/dedicated-rootserver/gex44/)
- [Hetzner GEX131 — RTX PRO 6000 Blackwell](https://www.hetzner.com/dedicated-rootserver/gex131/)
- [Modal Pricing](https://modal.com/pricing)
- [Replicate WhisperX (victor-upmeet)](https://replicate.com/victor-upmeet/whisperx)
- [SaladCloud Whisper Large V3 Cost Study](https://blog.salad.com/whisper-large-v3/)

### Architecture references
- [VS Code Remote Development using SSH](https://code.visualstudio.com/docs/remote/ssh)
- [JetBrains Gateway Remote Development](https://www.jetbrains.com/help/idea/remote-development-a.html)
- [Tailscale Auth Keys](https://tailscale.com/kb/1085/auth-keys)
- [Tailscale Ephemeral Nodes](https://tailscale.com/docs/features/ephemeral-nodes)
- [tailscale Python package on PyPI](https://pypi.org/project/tailscale/)
- [Paramiko SSH client API](https://docs.paramiko.org/en/stable/api/client.html)
- [Paramiko SFTP API](https://docs.paramiko.org/en/stable/api/sftp.html)
- [Paramiko Key handling](https://docs.paramiko.org/en/stable/api/keys.html)
- [Paramiko reverse-tunnel demo](https://github.com/paramiko/paramiko/blob/main/demos/rforward.py)
- [Paramiko ControlMaster limitation — issue 852](https://github.com/paramiko/paramiko/issues/852)
- [Deploy SSH public key with paramiko (29a.ch)](https://29a.ch/2010/9/8/deploy-ssh-public-key-multiple-servers-python-paramiko)

### Credential storage
- [Python keyring package on PyPI](https://pypi.org/project/keyring/)

### UX references
- [MacWhisper Cloud Transcription Setup](https://macwhisper.helpscoutdocs.com/article/18-cloud-transcription)
- [Sonix API](https://sonix.ai/api)
- [Syncthing Introducer Configuration](https://docs.syncthing.net/users/introducer.html)

### Performance / benchmarks
- [Whisper Performance on RTX 4090 (Wehrens)](https://owehrens.com/whisper-performance-on-nvidia-rtx-4090/)
- [SynpixCloud 2026 GPU Pricing Comparison](https://www.synpixcloud.com/blog/cloud-gpu-pricing-comparison-2026)
- [Spheron 2026 GPU Cloud Pricing](https://www.spheron.network/blog/gpu-cloud-pricing-comparison-2026/)
- [Linuxconfig — faster-whisper on Ubuntu + GPU + systemd](https://linuxconfig.org/how-to-use-openai-whisper-voice-to-text-with-gpu-on-debian-ubuntu)
- [Hugging Face Inference Providers](https://huggingface.co/docs/inference-providers/index)

---

## ۱۴. وابستگی‌های لازم برای v0.9

```toml
# pyproject.toml additions for the "remote" optional group:
[project.optional-dependencies]
remote = [
    "paramiko>=3.4",          # SSH + SFTP
    "keyring>=24.0",          # Windows Credential Manager DPAPI
    "runpod>=1.0",            # RunPod provider (optional)
]
remote_replicate_fallback = [
    "replicate>=0.40",        # HTTP API client (optional)
]
remote_tailscale = [
    "tailscale>=0.5",         # ephemeral nodes (optional)
]
```

نکته: نگه داشتن aspectsهای remote در optional groups مهم است — کاربر
local-only هیچ ضرری نمی‌بیند.

---

## ۱۵. آیتم‌های آینده / "Worth investigating"

- **Multi-server load balancing**: کاربر چند سرور دارد، اپ خودکار کار
  را بین آن‌ها تقسیم می‌کند. نیاز به work-stealing queue. M-L effort.
- **Hybrid mode**: کارهای کوچک local، کارهای بزرگ remote. سیاست
  decision در config. S-M effort.
- **Cost guardrails**: کاربر سقف ماهانه می‌گذارد، اپ قبل از تجاوز هشدار
  می‌دهد یا متوقف می‌کند. S effort.
- **Provider abstraction layer**: مشترک بین RunPod / Vast.ai / Replicate
  / Hetzner. **Over-engineering ریسک** — بهتر است هر provider در یک
  module جداگانه باشد.
- **Audit log روی remote**: همه‌ی job ها در سرور log می‌شوند، کاربر
  می‌تواند verify کند داده‌اش drift نکرده. M effort.

---

## ۱۶. وابستگی این تحقیق به v0.8

این فاز (remote-mode) **بعد از** Track 1-3 از v0.8 منطقی است:

- اگر Track 1 (Live mic) باشد، remote mode می‌تواند streaming را هم به
  remote بفرستد — یک طراحی پیچیده‌تر.
- اگر Track 2 (Local LLM) باشد، چالش جدیدی پیش می‌آید: آیا LLM روی
  remote اجرا شود یا local؟ پاسخ: روی remote اگر GPU است (سریع‌تر +
  cheap)، روی local اگر CPU است.
- اگر Track 3 (Hardware wizard) باشد، خوبست. وابستگی ندارد.

**توصیه**: v0.8 = features، v0.9 = remote-mode. ترتیب درست است.

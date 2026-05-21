# v0.9 Remote-Mode Research — Burst compute on a GPU server

Two parallel research shards: cloud GPU providers + pricing + APIs,
and remote architecture + non-tech UX patterns. Goal: a "click a
button, get a server, transcribe, tear down" mode where a non-technical
user only pastes an API key.

## TL;DR — recommended decision

**Stack**: RunPod Community Cloud (RTX 4090 $0.34/hr, per-ms billing,
Python SDK, SOC 2 Type II) as the primary provider.

**Architecture**: SSH + SFTP + the existing `core/worker.py` on the
remote, with **JSON-stdio over an SSH channel** — the worker code
doesn't change, only the transport (VS Code Remote-SSH pattern).

**UX**: 5-step wizard. Password is typed once, the app generates and
pushes an SSH key, and the user never types a password again.

**Smallest MVP**: BYO mode + password + SSH key auto-push only — **2
weeks of work, 80% of the value with 20% of the effort.**

**Marketing pitch**: "100 hours of audio ≈ $3 of GPU, only while you
use it."

---

## 1. Provider comparison (2026)

| Provider | RTX 4090 | RTX 3090 | A100 80GB | L40S | H100 | Billing | API Quality |
|---|---|---|---|---|---|---|---|
| **RunPod (Community)** | $0.34/hr | ~$0.22 | $1.19/hr | $1.90/hr | ~$2.49 | per-ms | Excellent: Python SDK + GraphQL + runpodctl CLI + SSH |
| RunPod (Secure) | $0.59/hr | n/a | ~$2.49 | ~$2.49 | ~$2.99 | per-ms | same |
| **Vast.ai** | $0.31/hr | $0.13/hr | ~$0.75 | ~$1.20 | ~$1.65 | per-sec | Excellent: `pip install vastai` (SDK+CLI in one) |
| Lambda Labs | n/a | n/a | $1.29/hr | n/a | $2.49-2.99 | per-min | REST API, no spot, no 4090/3090 |
| Modal | n/a | n/a | $3.73/hr | n/a | $3.95/hr | per-sec | Container-only, no SSH |
| **Replicate** | n/a | n/a | n/a | n/a | n/a | per-run | Highest-level: HTTP POST audio in, JSON out |
| Hyperbolic | $0.50/hr | n/a | $1.80/hr | n/a | $3.00-3.20 | per-hr | OpenAI-compatible API |
| TensorDock | $0.35/hr | n/a | $0.75-1.20 | n/a | $1.91-2.25 | per-hr | REST, KVM (Windows OK), spot |
| Hetzner GEX44 | RTX-4000 Ada 20GB | — | — | — | — | monthly | SSH/bare-metal, no API for ad-hoc |
| Hetzner GEX131 | RTX PRO 6000 Blackwell | — | — | — | — | monthly | same |

**Winners**: RunPod Community + Vast.ai marketplaces are far and away
the cheapest.

---

## 2. Cost reality (100 hours of audio)

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

**Marketing pitch**: "100 hours of audio ≈ $3 of GPU on RTX 4090. 1000
hours under $30. Pay only while you use it."

**SaladCloud benchmark** (sanity check): official report claims 1
million hours of audio at large-v3 = $5,110 on a network of home RTX
3060s — roughly half a cent per hour of audio. Suggests low-tier GPU is
viable for very large backlogs.

---

## 3. Three flavours in one wizard

```
Settings → Remote processing →
  ┌───────────────────────────────────────────┐
  │ □ I have my own server (BYO)              │
  │   host + user + password or key file      │
  │                                           │
  │ □ Get me a cloud server (Managed)         │
  │   Just paste a RunPod API key             │
  │                                           │
  │ □ Use a free-tier API (Fallback)          │
  │   HuggingFace Inference / Replicate       │
  └───────────────────────────────────────────┘
```

### BYO (Bring-Your-Own-Server)

User already has a Hetzner / Vast.ai / RunPod / home-GPU machine. The
app connects via SSH + Paramiko, runs the bootstrap, installs the
worker, dispatches jobs.

### Managed (app provisions a cloud GPU)

User pastes a RunPod API key. The app spawns a pod, dispatches jobs,
terminates billing on exit. Live cost shown.

### Fallback API

For users who don't want to manage pods: `Replicate
victor-upmeet/whisperx` HTTP POST. ~$0.002 per file = per-file billing.
Simplest UX but custom hotwords / initial_prompt are limited.

---

## 4. 5-step wizard (full UX flow)

**Step 1 — Toggle in Settings**
User flips "Enable remote processing". A modal wizard opens. No
network call yet.

**Step 2 — Choose flavour**
Three big buttons (BYO / Managed / Fallback). Short blurb under each +
ballpark cost + GDPR badge.

**Step 3 — Enter credentials**
BYO has four fields: host, port (default 22), username, and either
password or an upload key file. On submit, in the background:

1. SSH connection is tested
2. Remote OS is detected (`cat /etc/os-release`)
3. The app generates a local RSA 4096 key, writes the public half to
   `~/.ssh/authorized_keys` on the remote, wipes the password from
   memory (`ssh-copy-id` pattern)
4. The private key is stored in Windows Credential Manager (DPAPI) via
   the `keyring` package

**From this point on the user never types a password again.**

**Step 4 — Bootstrap + cost estimate**
Progress bar with four steps: "Check GPU" → "Install ffmpeg" →
"Install faster-whisper" → "Download model". A verbose log is
expandable on demand.

For BYO no cost is shown; for Managed the provider rate is shown:

```
RunPod Community RTX 4090: $0.34/hr
A100 80GB:                 $1.19/hr
H100:                      $2.49/hr
```

**Step 5 — Confirmation + a "remote: hetzner-gpu1" badge**
The wizard closes. A small badge in the main panel indicates where
jobs run. Each new job routes remote, with a 3-state status bar:
upload → transcribe → download.

---

## 5. Architecture: SSH + SFTP + JSON-stdio (VS Code Remote-SSH pattern)

**Why this choice?**

- VS Code Remote-SSH (the gold standard) does exactly this: two open
  SSH connections, a worker installed at `$HOME/.vscode-server`, an
  SSH port tunnel for RPC.
- JetBrains Gateway uses the same pattern + TLS 1.3 inside the SSH
  tunnel (optional overkill).
- Why not pure REST? A non-technical user can't make a TLS cert /
  port-forward / write nginx config.
- Why not Modal/container-only? Changes our architecture and breaks
  our persistent queue.
- **Biggest win**: the existing `core/worker.py` works unchanged on
  the remote — only the transport changes.

**Layer details**:

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

- **Audio upload**: SFTP with chunk-resume. 10-500 MB on a 50 Mbit
  home link = 2-80 seconds.
- **Job dispatch + status**: the existing JSON-stdio over one SSH exec
  channel. **No worker-code change.**
- **Model weights**: pre-downloaded once on a persistent volume, not
  per-job.

**Multi-worker parallelism**: Paramiko doesn't support OpenSSH
ControlMaster multiplexing — for 4 parallel workers, use 4 separate
Transport channels. Cheap.

---

## 6. Bootstrap script (idempotent)

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

Idempotent — only delta changes on each run.

**Worker push strategies** (three options):

1. **`pip install whisper-remote-worker` from PyPI** — recommended.
   Simple updates, signed wheel, clear versioning.
2. `git clone` from a public repo — simple but trusts GitHub.
3. scp the whole tarball — worst, ties it to the local app version.

**Versioning**: a `version.json` is written to `/opt/whisper-remote/`.
The app reads it on connect; if smaller than `minimum_required`, it
reinstalls.

**Two-versions-side-by-side**: suffix → `/opt/whisper-remote-v0.9/` and
`/opt/whisper-remote-v1.0/` with separate systemd units.

---

## 7. Failure modes — human-readable messages

| Technical cause | User-facing message |
|---|---|
| SSH timeout | "Server didn't answer. Check host and port." + retry button |
| Auth failed | "Username or password is wrong." (no detail leakage) |
| nvidia-smi missing | "This server has no GPU — continue with CPU?" |
| Disk full on remote | "Not enough disk on the server (need 8 GB, free 2 GB)" |
| Upload dropped | Auto-resume; after 3 retries, fall back to local |
| Laptop lid closed | **Job keeps running on the remote** (systemd persistent). When the app reopens, it polls status and pulls the result. **This is a feature, not a bug** — like VS Code's persistent remote server. |
| Installation failed | "Show full log" in the dialog + "Report to GitHub" button that opens an issue automatically |

---

## 8. Security — privacy-first principles preserved

- **In transit**: SSH AES-256-GCM. With Tailscale selected, an extra
  WireGuard layer (deliberate overkill).
- **On the server**: files in `/opt/whisper-remote/jobs/<uuid>/` with
  mode 0700, auto-delete after 24 hours. Model weights read-only
  mounted.
- **On Windows**:
  - Private SSH key stored in DPAPI via the `keyring` package
  - Initial password kept in memory only for ~30 seconds (long enough
    to push the key), then wiped
  - history.db is not encrypted but sensitive tags are hashed
- **Revocation**: the pushed public key is marked with the comment
  `whisper-remote@<host>-<install-id>` so the user can revoke later
  manually

---

## 9. Privacy + compliance per provider

| Provider | At-rest encryption | EU region | SOC 2 | GDPR | HIPAA |
|---|---|---|---|---|---|
| **RunPod Community** | yes | yes | Type II ✓ (2026) | ✓ | ✓ |
| Vast.ai | host-dependent (varies) | varies | no | risky | no |
| Lambda Labs | yes | yes | Type II ✓ | ✓ | — |
| Hetzner | yes | yes (DE/FI) | ISO 27001 | ✓ default | — |
| Genesis Cloud | yes | EU-native | ✓ | ✓ | — |

**For EU users with sensitive data**: RunPod EU region or Hetzner.
**Vast.ai is not suitable** for sensitive data due to heterogeneous
hosts.

---

## 10. Competitor UX — what they do

**MacWhisper Pro** (the gold standard):
- A "Cloud Transcription" page in Settings
- Paste the chosen provider's API key
- Credentials are kept in macOS Keychain
- Flow: paste-key → toggle on → drag audio → done

**Sonix**: B2B SaaS, not desktop. Doesn't offer self-hosted GPU. Skip.

**Whispering, Aqua Voice**: mostly local + Groq / ElevenLabs fallback.

**Conclusion**: a "Use cloud GPU" toggle + Windows Credential Manager
storage + cost estimate before submit is enough.

---

## 11. Key Python libraries for implementation

- `paramiko` — SSH + SFTP, MIT-licensed
- `keyring` — Windows Credential Manager (DPAPI) integration
- `runpod` — official RunPod Python SDK, MIT
- `vastai` — CLI + SDK in one package
- `replicate` — official Python SDK for the HTTP API
- `tailscale` — Python package on PyPI for ephemeral nodes (optional,
  for NAT'd home servers)

---

## 12. Effort estimate + cut-down v0.9

**M-L scale**: 4-6 weeks of full-time engineer for a full v0.9.

**Week-by-week breakdown**:

- Week 1: Paramiko + SFTP + sessionful execution
- Week 2: idempotent bootstrap + systemd + version detection
- Week 3: 5-step UX wizard + Windows Credential Manager
- Week 4: connection-drop handling, resume, end-to-end test on a real
  Hetzner box
- Weeks 5-6: managed path on RunPod + Replicate fallback

**Smallest MVP** (20% effort, 80% value): **BYO + password + SSH key
auto-push only**.

- User enters host + password
- App generates an SSH key and pushes it
- Idempotent bootstrap runs
- Transcription runs over `ssh exec` with the existing JSON-stdio
- **No Tailscale, no managed cloud, no REST**
- 2 weeks of work

**Evolutionary roadmap**:

1. **v0.8**: BYO mode only (2 weeks)
2. **v0.9**: add Managed RunPod (4 weeks)
3. **v1.0**: add Tailscale overlay for NAT'd home servers (2 weeks)
4. **Never**: managed Modal + multi-cloud abstraction layer
   (over-engineering)

This path turns the project from "a Whisper desktop tool" into
"desktop + burst-compute on demand" without sacrificing the offline +
privacy-first edge.

---

## 13. Key references (~40 sources gathered, key ones below)

### Cloud providers
- [RunPod Pricing](https://www.runpod.io/pricing)
- [RunPod Serverless Pricing Docs](https://docs.runpod.io/serverless/pricing)
- [RunPod Python SDK on GitHub](https://github.com/runpod/runpod-python)
- [runpod-workers/worker-faster_whisper](https://github.com/runpod-workers/worker-faster_whisper)
- [RunPod Security & Compliance](https://docs.runpod.io/references/security-and-compliance)
- [RunPod SOC 2 Type II announcement](https://www.runpod.io/blog/runpod-achieves-soc-2-type-ii-certification)
- [Vast.ai Pricing](https://vast.ai/pricing)
- [Vast.ai Python SDK Quickstart](https://docs.vast.ai/sdk/python/quickstart)
- [Vast.ai CLI on GitHub](https://github.com/vast-ai/vast-cli)
- [Lambda Labs Pricing](https://lambda.ai/pricing)
- [Hetzner GEX44 — RTX 4000 Ada 20GB](https://www.hetzner.com/dedicated-rootserver/gex44/)
- [Hetzner GEX131 — RTX PRO 6000 Blackwell](https://www.hetzner.com/dedicated-rootserver/gex131/)
- [Modal Pricing](https://modal.com/pricing)
- [Replicate WhisperX (victor-upmeet)](https://replicate.com/victor-upmeet/whisperx)
- [SaladCloud Whisper Large V3 cost study](https://blog.salad.com/whisper-large-v3/)

### Architecture references
- [VS Code Remote Development using SSH](https://code.visualstudio.com/docs/remote/ssh)
- [JetBrains Gateway Remote Development](https://www.jetbrains.com/help/idea/remote-development-a.html)
- [Tailscale Auth Keys](https://tailscale.com/kb/1085/auth-keys)
- [Tailscale Ephemeral Nodes](https://tailscale.com/docs/features/ephemeral-nodes)
- [`tailscale` Python package on PyPI](https://pypi.org/project/tailscale/)
- [Paramiko SSH client API](https://docs.paramiko.org/en/stable/api/client.html)
- [Paramiko SFTP API](https://docs.paramiko.org/en/stable/api/sftp.html)
- [Paramiko key handling](https://docs.paramiko.org/en/stable/api/keys.html)
- [Paramiko reverse-tunnel demo](https://github.com/paramiko/paramiko/blob/main/demos/rforward.py)
- [Paramiko ControlMaster limitation — issue 852](https://github.com/paramiko/paramiko/issues/852)
- [Deploy SSH public key with paramiko (29a.ch)](https://29a.ch/2010/9/8/deploy-ssh-public-key-multiple-servers-python-paramiko)

### Credential storage
- [`keyring` Python package on PyPI](https://pypi.org/project/keyring/)

### UX references
- [MacWhisper Cloud Transcription setup](https://macwhisper.helpscoutdocs.com/article/18-cloud-transcription)
- [Sonix API](https://sonix.ai/api)
- [Syncthing Introducer configuration](https://docs.syncthing.net/users/introducer.html)

### Performance / benchmarks
- [Whisper performance on RTX 4090 (Wehrens)](https://owehrens.com/whisper-performance-on-nvidia-rtx-4090/)
- [SynpixCloud 2026 GPU pricing comparison](https://www.synpixcloud.com/blog/cloud-gpu-pricing-comparison-2026)
- [Spheron 2026 GPU cloud pricing](https://www.spheron.network/blog/gpu-cloud-pricing-comparison-2026/)
- [Linuxconfig — faster-whisper on Ubuntu + GPU + systemd](https://linuxconfig.org/how-to-use-openai-whisper-voice-to-text-with-gpu-on-debian-ubuntu)
- [Hugging Face Inference Providers](https://huggingface.co/docs/inference-providers/index)

---

## 14. Required dependencies for v0.9

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

Keep all remote bits in optional groups so local-only users see no
penalty.

---

## 15. Worth-investigating future items

- **Multi-server load balancing**: user has several servers; the app
  auto-shards work across them. Needs a work-stealing queue. M-L
  effort.
- **Hybrid mode**: small jobs local, big jobs remote. Decision policy
  in config. S-M effort.
- **Cost guardrails**: monthly cap; app warns or pauses before
  exceeding. S effort.
- **Provider abstraction layer**: common over RunPod / Vast.ai /
  Replicate / Hetzner. **Over-engineering risk** — better to keep each
  provider in its own module.
- **Audit log on the remote**: all jobs logged on the server so the
  user can verify no drift. M effort.

---

## 16. Dependency on v0.8

This phase (remote-mode) makes sense **after** Tracks 1-3 of v0.8:

- If Track 1 (Live mic) ships, remote mode can stream to the remote
  too — a more complex design.
- If Track 2 (Local LLM) ships, a new question arises: should the LLM
  run on the remote or local? Answer: remote if GPU available
  (faster + cheap), local otherwise.
- If Track 3 (Hardware wizard) ships, no dependency.

**Recommended order**: v0.8 = features, v0.9 = remote-mode. The order
matters.

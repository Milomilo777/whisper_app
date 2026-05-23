# UML

Two diagrams: a component view of the modules, and a sequence view of one transcribe round-trip.

## Component diagram

```mermaid
flowchart TB
    subgraph entry [Entry]
        GUI[gui.py]
    end

    subgraph app [app/]
        APP[app.App]
        DROP[widgets.DropZone]
        DLG_HUB[dialogs.hub_setup]
        DLG_DOWNLOAD[dialogs.model_download]
        DLG_LOAD[dialogs.model_loading]
        DLG_DIAG[dialogs.diagnose]
        DLG_LOG[dialogs.show_log]
        DLG_ABOUT[dialogs.about]
        DLG_CRASH[dialogs.crash]
    end

    subgraph core [core/]
        CONFIG[config]
        PATHS[paths]
        LOG[logging_setup]
        HW[hardware]
        HUB[hub]
        MM[model_manager]
        TASK[task]
        TRANS[transcriber]
        WORKER[worker]
        WRITERS[writers/]
        ERR[error_messages]
        HEALTH[health_check]
    end

    subgraph bin [bin/]
        FF[ffmpeg + ffprobe]
    end

    GUI --> APP
    GUI --> WORKER
    APP --> DROP
    APP --> DLG_HUB
    APP --> DLG_DOWNLOAD
    APP --> DLG_LOAD
    APP --> DLG_DIAG
    APP --> DLG_LOG
    APP --> DLG_ABOUT
    APP --> DLG_CRASH
    APP --> CONFIG
    APP --> HEALTH
    APP --> MM
    APP --> TASK
    APP --> LOG
    APP -.spawns.-> WORKER

    WORKER --> CONFIG
    WORKER --> TRANS
    WORKER --> ERR
    WORKER --> LOG

    TRANS --> WRITERS
    TRANS --> HW
    TRANS --> CONFIG
    TRANS --> PATHS
    TRANS --> TASK
    TRANS -.calls.-> FF

    MM --> HUB
    MM --> CONFIG
    HEALTH --> PATHS
    HEALTH --> CONFIG
    HEALTH --> HUB
    DLG_HUB --> HUB
    DLG_HUB --> CONFIG
    DLG_DOWNLOAD --> MM
```

## Sequence diagram — first Transcribe click

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant App as App (Tk main thread)
    participant DL as ModelDownloadDialog
    participant ML as ModelLoadingDialog
    participant W as Worker subprocess
    participant FS as Disk
    User->>App: Drop file + click Transcribe
    App->>FS: is_model_on_disk?
    alt model missing
        App->>DL: show modal
        DL->>FS: ensure_model() — download + MD5 verify
        DL-->>App: success
    end
    App->>W: subprocess.Popen("gui.py --worker")
    App->>ML: show modal
    W->>FS: load WhisperModel(model_path)
    W-->>App: {"event":"ready"}
    App->>ML: mark_success_and_close()
    App->>W: {"action":"transcribe","file_path":"..."}
    loop one event per segment
        W-->>App: {"event":"progress","percent":N}
        App->>App: update progress bar + Treeview
    end
    W->>FS: write .srt + .json + .txt (atomic)
    W-->>App: {"event":"done","file_path":"..."}
    App->>App: dispatch next queued task
```

## Sequence diagram — error path

```mermaid
sequenceDiagram
    autonumber
    participant App
    participant W as Worker
    participant ERR as core.error_messages
    Note over W: transcribe raises (e.g. CUDA OOM)
    W->>ERR: friendly_error(exc)
    ERR-->>W: ("Your GPU ran out of memory.", "Close other GPU-heavy apps…")
    W-->>App: {"event":"error","message":"...","suggestion":"...","file_path":"..."}
    App->>App: show messagebox.showerror with message + suggestion
    App->>App: leave worker alive; dispatch next task
```

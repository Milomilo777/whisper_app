
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
import json,re,subprocess,sys,threading,time,os
from queue import Empty, Queue
from core.task import TranscriptionTask
from core.config import load_config, save_config
from core.model_manager import DownloadCancelled, ensure_model

queue=[]
download_queue=[]
download_current=None

SUBTITLE_LANGUAGES=[
    ("Automatic",""),
    ("English","en"),
    ("Spanish","es"),
    ("French","fr"),
    ("German","de"),
    ("Italian","it"),
    ("Portuguese","pt"),
    ("Russian","ru"),
    ("Japanese","ja"),
    ("Korean","ko"),
    ("Chinese (Simplified)","zh-Hans"),
    ("Chinese (Traditional)","zh-Hant"),
    ("Arabic","ar"),
    ("Hindi","hi"),
    ("Dutch","nl"),
    ("Polish","pl"),
    ("Turkish","tr"),
    ("Vietnamese","vi"),
    ("Thai","th"),
    ("Indonesian","id"),
    ("Swedish","sv"),
    ("Norwegian","no"),
    ("Danish","da"),
    ("Finnish","fi"),
    ("Greek","el"),
    ("Hebrew","he"),
    ("Czech","cs"),
    ("Hungarian","hu"),
    ("Romanian","ro"),
    ("Ukrainian","uk"),
    ("Persian","fa"),
]

def fmt_bytes(value):
    value=float(value or 0)
    for unit in ("B","KB","MB","GB","TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} {unit}"
        value/=1024

def fmt_duration(seconds):
    if seconds is None:
        return "--:--"
    seconds=max(0,int(seconds))
    h=seconds//3600
    m=(seconds%3600)//60
    s=seconds%60
    return f"{h:02}:{m:02}:{s:02}" if h else f"{m:02}:{s:02}"

class ModelDownloadDialog(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Preparing Whisper model")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self.cancel)

        self.events=Queue()
        self.cancel_event=threading.Event()
        self.done=False
        self.success=False
        self.error=None
        self.started=time.time()

        self.status_var=tk.StringVar(value="Starting model setup...")
        self.detail_var=tk.StringVar(value="")
        self.elapsed_var=tk.StringVar(value="Elapsed: 00:00")
        self.remaining_var=tk.StringVar(value="Remaining: --:--")
        self.speed_var=tk.StringVar(value="Speed: --")
        self.size_var=tk.StringVar(value="Total: unknown")

        body=ttk.Frame(self,padding=18)
        body.grid(row=0,column=0,sticky="nsew")

        ttk.Label(body,text="Downloading required model",font=("Segoe UI",11,"bold")).grid(row=0,column=0,columnspan=2,sticky="w")
        ttk.Label(body,textvariable=self.status_var).grid(row=1,column=0,columnspan=2,sticky="w",pady=(10,4))

        self.pb=ttk.Progressbar(body,length=420,mode="determinate",maximum=100)
        self.pb.grid(row=2,column=0,columnspan=2,sticky="ew",pady=(0,8))

        ttk.Label(body,textvariable=self.detail_var).grid(row=3,column=0,columnspan=2,sticky="w")
        ttk.Label(body,textvariable=self.elapsed_var).grid(row=4,column=0,sticky="w",pady=(10,0))
        ttk.Label(body,textvariable=self.remaining_var).grid(row=4,column=1,sticky="e",pady=(10,0))
        ttk.Label(body,textvariable=self.speed_var).grid(row=5,column=0,sticky="w")
        ttk.Label(body,textvariable=self.size_var).grid(row=5,column=1,sticky="e")

        self.cancel_btn=ttk.Button(body,text="Cancel",command=self.cancel)
        self.cancel_btn.grid(row=6,column=1,sticky="e",pady=(14,0))

        body.columnconfigure(0,weight=1)
        body.columnconfigure(1,weight=1)

        self.update_idletasks()
        x=master.winfo_rootx() + (master.winfo_width()-self.winfo_width())//2
        y=master.winfo_rooty() + (master.winfo_height()-self.winfo_height())//2
        self.geometry(f"+{max(x,0)}+{max(y,0)}")

        threading.Thread(target=self.worker,daemon=True).start()
        self.after(100,self.poll)

    def worker(self):
        def status(msg):
            self.events.put(("status",msg))

        def progress(payload):
            self.events.put(("progress",payload))

        try:
            ensure_model(load_config(),status,progress,self.cancel_event)
            self.success=True
        except DownloadCancelled:
            self.success=False
        except Exception as e:
            self.error=str(e)
            self.success=False
        finally:
            self.done=True
            self.events.put(("done",None))

    def cancel(self):
        self.cancel_event.set()
        self.status_var.set("Cancelling download...")
        self.cancel_btn.configure(state="disabled")

    def poll(self):
        while True:
            try:
                kind,payload=self.events.get_nowait()
            except Empty:
                break

            if kind=="status":
                self.status_var.set(payload)
            elif kind=="progress":
                self.apply_progress(payload)
            elif kind=="done":
                if self.success:
                    self.destroy()
                    return
                if self.error:
                    messagebox.showerror("Model setup failed",self.error,parent=self)
                self.destroy()
                return

        elapsed=time.time()-self.started
        self.elapsed_var.set(f"Elapsed: {fmt_duration(elapsed)}")
        self.after(100,self.poll)

    def apply_progress(self,payload):
        percent=payload.get("percent")
        if percent is not None:
            self.pb["value"]=percent

        if payload.get("status"):
            self.status_var.set(payload["status"])
        if payload.get("detail"):
            self.detail_var.set(payload["detail"])

        total=payload.get("total")
        downloaded=payload.get("downloaded")
        speed=payload.get("speed")
        remaining=payload.get("remaining")

        if total:
            self.size_var.set(f"Total: {fmt_bytes(total)}")
        if downloaded is not None and total:
            self.size_var.set(f"Total: {fmt_bytes(downloaded)} / {fmt_bytes(total)}")
        if speed:
            self.speed_var.set(f"Speed: {fmt_bytes(speed)}/s")
        if "remaining" in payload:
            self.remaining_var.set(f"Remaining: {fmt_duration(remaining)}")

class VideoDownloadTask:
    def __init__(self, url, folder, format_label, format_info, title="", subtitles_enabled=False, subtitle_lang="", detected_language=""):
        self.url=url
        self.folder=folder
        self.format_label=format_label
        self.format_info=format_info
        self.title=title
        self.status="waiting"
        self.progress=0
        self.start_time=None
        self.process=None
        self.cancelled=False
        self.subtitles_enabled=subtitles_enabled
        self.subtitle_lang=subtitle_lang
        self.detected_language=detected_language

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Transcription helper")
        self.geometry("900x600")
        self.protocol("WM_DELETE_WINDOW",self.on_exit)

        self.status_var=tk.StringVar(value="Initializing...")
        self.model_ready=False
        self.model_loading=False
        self.model_setup_running=False
        self.workers=[]
        self.worker_events=Queue()
        self.worker_ready=False
        self.app_config=load_config()
        self.parallel_workers=max(1,int(self.app_config.get("parallel_workers",2)))
        self.next_worker_id=1
        self.format_events=Queue()
        self.download_events=Queue()
        self.audio_format_map={}
        self.video_format_map={}
        self.current_video_title=""
        self.current_video_language=""
        self.format_lookup_after=None

        self.menu()
        self.tabs()
        self.console()

        self.after(100,self.start_standby_worker)
        self.after(300,self.loop)

    def model_status(self,msg):
        self.status_var.set(msg)
        self.log(msg)
        if "Model loaded" in msg:
            self.model_ready=True

    def active_workers(self):
        return [w for w in self.workers if w["process"] and w["process"].poll() is None]

    def ready_workers(self):
        return [w for w in self.active_workers() if w["ready"]]

    def idle_workers(self):
        return [w for w in self.ready_workers() if w["task"] is None]

    def update_model_state(self):
        ready_count=len(self.ready_workers())
        self.worker_ready=ready_count > 0
        self.model_ready=self.worker_ready
        self.model_loading=not self.worker_ready
        if ready_count:
            self.status_var.set(f"Model ready ({ready_count} worker{'s' if ready_count != 1 else ''})")

    def start_standby_worker(self):
        if not self.active_workers():
            self.start_worker(temporary=False)
        self.update_model_state()

    def start_worker(self, worker=None, temporary=False):
        if worker and worker["process"] and worker["process"].poll() is None:
            return

        if worker is None:
            worker={"id":self.next_worker_id,"process":None,"ready":False,"task":None,"temporary":temporary}
            self.next_worker_id+=1
            self.workers.append(worker)
        else:
            worker["temporary"]=temporary

        self.model_loading=True
        worker["ready"]=False
        worker["task"]=None
        self.status_var.set(f"Loading model worker {worker['id']}...")

        cmd=[sys.executable,"-u","-m","core.worker"]
        kwargs={
            "cwd":os.path.dirname(os.path.abspath(__file__)),
            "stdin":subprocess.PIPE,
            "stdout":subprocess.PIPE,
            "stderr":subprocess.STDOUT,
            "text":True,
            "encoding":"utf-8",
            "errors":"replace",
        }
        if os.name=="nt":
            kwargs["creationflags"]=subprocess.CREATE_NO_WINDOW

        process=subprocess.Popen(cmd,**kwargs)
        worker["process"]=process

        def run():
            for line in process.stdout:
                line=line.strip()
                if not line:
                    continue

                try:
                    event=json.loads(line)
                except json.JSONDecodeError:
                    event={"event":"log","message":line}

                event["_pid"]=process.pid
                event["_worker_id"]=worker["id"]
                self.worker_events.put(event)

            return_code=process.wait()
            self.worker_events.put({"event":"worker_exit","return_code":return_code,"_pid":process.pid,"_worker_id":worker["id"]})

        threading.Thread(target=run,daemon=True).start()
        self.after(100,self.poll_worker_events)

    def worker_for_event(self,event):
        for worker in self.workers:
            process=worker.get("process")
            if worker["id"] == event.get("_worker_id") and process and process.pid == event.get("_pid"):
                return worker
        return None

    def stop_worker(self, worker):
        process=worker.get("process")
        if process and process.poll() is None:
            try:
                if process.stdin:
                    process.stdin.write(json.dumps({"action":"shutdown"})+"\n")
                    process.stdin.flush()
            except Exception:
                pass
            process.terminate()

    def stop_workers(self):
        for worker in self.active_workers():
            self.stop_worker(worker)

    def restart_worker(self, worker):
        self.stop_worker(worker)
        worker["process"]=None
        worker["ready"]=False
        worker["task"]=None
        self.model_loading=True
        self.after(300,lambda:self.start_worker(worker,temporary=worker.get("temporary",False)))

    def retire_worker(self, worker):
        self.stop_worker(worker)
        worker["process"]=None
        worker["ready"]=False
        worker["task"]=None
        if worker in self.workers:
            self.workers.remove(worker)
        self.update_model_state()

    def poll_worker_events(self):
        while True:
            try:
                event=self.worker_events.get_nowait()
            except Empty:
                break

            event_type=event.get("event")
            worker=self.worker_for_event(event)
            if not worker:
                continue

            if event_type=="log":
                self.model_status(event.get("message",""))
            elif event_type=="ready":
                worker["ready"]=True
                self.update_model_state()
            elif event_type=="startup_error":
                worker["ready"]=False
                self.log(event.get("message","Existing model failed to load."))
                if not self.model_setup_running:
                    self.log("Existing model failed to load. Starting required download.")
                    self.stop_workers()
                    self.workers=[]
                    self.ensure_model_with_modal(mandatory=True)
            elif event_type=="started":
                pass
            elif event_type=="progress":
                if worker["task"]:
                    p=event.get("percent",0)
                    worker["task"].progress=p
                    self.update_overall_progress()
            elif event_type=="done":
                self.finish_worker_task(worker)
            elif event_type=="error":
                if worker["task"]:
                    worker["task"].status="error"
                    self.log(event.get("message","Worker error"))
                    self.finish_worker_task(worker,keep_status=True)
                else:
                    self.log(event.get("message","Worker error"))
            elif event_type=="worker_exit":
                worker["ready"]=False
                worker["process"]=None
                if worker["task"] and worker["task"].status=="running":
                    worker["task"].status="error"
                    self.log(f"Transcription worker exited with code {event.get('return_code')}")
                    self.finish_worker_task(worker,keep_status=True)
                self.update_model_state()

        if self.active_workers():
            self.after(100,self.poll_worker_events)

    def ensure_model_with_modal(self, mandatory=False):
        if self.model_ready:
            self.model_ready=True
            self.status_var.set("Model loaded")
            return True

        if self.model_setup_running:
            return False

        self.model_setup_running=True
        dialog=ModelDownloadDialog(self)
        self.wait_window(dialog)
        self.model_setup_running=False

        if dialog.success:
            self.log("Model downloaded. Starting standby worker.")
            self.start_standby_worker()
            return True

        self.model_ready=False
        self.status_var.set("Model is required")
        if mandatory:
            self.log("Model setup was cancelled or failed. Requests will not be queued until the model is ready.")
        return False

    def menu(self):
        m=tk.Menu(self)
        f=tk.Menu(m,tearoff=0)
        f.add_command(label="Exit",command=self.on_exit)
        a=tk.Menu(m,tearoff=0)
        a.add_command(label="About",command=lambda:messagebox.showinfo("About","Whisper"))
        m.add_cascade(label="File",menu=f)
        m.add_cascade(label="About",menu=a)
        self.config(menu=m)

    def on_exit(self):
        active=[t for t in queue if t.status not in ("finished","cancelled","error")]
        active_downloads=[t for t in download_queue if t.status not in ("finished","cancelled","error")]
        if active or active_downloads:
            if not messagebox.askyesno("Exit with queued tasks","There are queued or running tasks. Exit anyway?",parent=self):
                return
        for task in download_queue:
            if task.process and task.process.poll() is None:
                task.process.terminate()
        self.stop_workers()
        self.destroy()

    def tabs(self):
        self.nb=ttk.Notebook(self);self.nb.pack(fill="both",expand=True)
        self.t1=ttk.Frame(self.nb);self.t2=ttk.Frame(self.nb);self.t3=ttk.Frame(self.nb)
        self.nb.add(self.t1,text="Transcribe");self.nb.add(self.t2,text="Transcription Queue");self.nb.add(self.t3,text="Download Videos")

        tk.Label(self.t1,text="File").grid(row=0,column=0)
        self.fv=tk.StringVar()
        tk.Entry(self.t1,textvariable=self.fv,width=60).grid(row=0,column=1)
        tk.Button(self.t1,text="Browse",command=self.browse).grid(row=0,column=2)
        tk.Button(self.t1,text="Transcribe",command=self.add).grid(row=1,column=1)
        tk.Button(self.t2,text="Clear completed",command=self.clear_completed).pack(anchor="e",padx=10,pady=6)

        cols=("file","status","progress","time")
        self.tree=ttk.Treeview(self.t2,columns=cols,show="headings")
        for c in cols:
            self.tree.heading(c,text=c)
        self.tree.pack(fill="both",expand=True)

        self.pb=ttk.Progressbar(self.t2,length=400)
        self.pb.pack(fill="x",padx=10,pady=10)

        tk.Label(self.t2,textvariable=self.status_var).pack()

        self.tree.bind("<Button-3>",self.menu_row)
        self.row_map={}

        self.download_tab()

    def download_tab(self):
        top=ttk.Frame(self.t3,padding=10)
        top.pack(fill="x")

        ttk.Label(top,text="URL").grid(row=0,column=0,sticky="w")
        self.download_url_var=tk.StringVar()
        self.download_url_var.trace_add("write",lambda *_:self.schedule_format_lookup())
        ttk.Entry(top,textvariable=self.download_url_var,width=80).grid(row=0,column=1,columnspan=2,sticky="ew",padx=(6,0))

        ttk.Label(top,text="Folder").grid(row=1,column=0,sticky="w",pady=(8,0))
        self.download_folder_var=tk.StringVar(value=self.app_config.get("download_folder",""))
        ttk.Entry(top,textvariable=self.download_folder_var,width=70).grid(row=1,column=1,sticky="ew",padx=(6,0),pady=(8,0))
        ttk.Button(top,text="Browse",command=self.browse_download_folder).grid(row=1,column=2,sticky="ew",padx=(6,0),pady=(8,0))

        ttk.Label(top,text="Mode").grid(row=2,column=0,sticky="w",pady=(8,0))
        self.download_mode_var=tk.StringVar(value="Audio and video")
        self.download_mode_combo=ttk.Combobox(top,textvariable=self.download_mode_var,state="readonly",values=("Audio and video","Audio"),width=24)
        self.download_mode_combo.grid(row=2,column=1,sticky="w",padx=(6,0),pady=(8,0))
        self.download_mode_combo.bind("<<ComboboxSelected>>",lambda _e:self.update_download_mode())

        ttk.Label(top,text="Audio").grid(row=3,column=0,sticky="w",pady=(8,0))
        self.audio_format_var=tk.StringVar()
        self.audio_format_combo=ttk.Combobox(top,textvariable=self.audio_format_var,state="readonly",width=76)
        self.audio_format_combo.grid(row=3,column=1,columnspan=2,sticky="ew",padx=(6,0),pady=(8,0))

        ttk.Label(top,text="Video").grid(row=4,column=0,sticky="w",pady=(8,0))
        self.video_format_var=tk.StringVar()
        self.video_format_combo=ttk.Combobox(top,textvariable=self.video_format_var,state="readonly",width=76)
        self.video_format_combo.grid(row=4,column=1,columnspan=2,sticky="ew",padx=(6,0),pady=(8,0))

        ttk.Label(top,text="Output").grid(row=5,column=0,sticky="w",pady=(8,0))
        self.output_format_var=tk.StringVar(value="mp4")
        self.output_format_combo=ttk.Combobox(top,textvariable=self.output_format_var,state="readonly",width=20)
        self.output_format_combo.grid(row=5,column=1,sticky="w",padx=(6,0),pady=(8,0))

        ttk.Label(top,text="Subtitles").grid(row=6,column=0,sticky="w",pady=(8,0))
        sub_frame=ttk.Frame(top)
        sub_frame.grid(row=6,column=1,columnspan=2,sticky="ew",padx=(6,0),pady=(8,0))
        self.download_subtitles_var=tk.BooleanVar(value=False)
        ttk.Checkbutton(sub_frame,text="Download automatic subtitles",variable=self.download_subtitles_var,command=self.update_subtitle_state).pack(side="left")
        self.subtitle_lang_var=tk.StringVar(value=SUBTITLE_LANGUAGES[0][0])
        self.subtitle_lang_combo=ttk.Combobox(sub_frame,textvariable=self.subtitle_lang_var,state="readonly",values=[name for name,_ in SUBTITLE_LANGUAGES],width=24)
        self.subtitle_lang_combo.pack(side="left",padx=(10,0))

        self.format_status_var=tk.StringVar(value="Enter a URL to load available formats")
        ttk.Label(top,textvariable=self.format_status_var).grid(row=7,column=1,columnspan=2,sticky="w",padx=(6,0),pady=(4,0))
        ttk.Button(top,text="Download",command=self.add_download).grid(row=8,column=2,sticky="e",pady=(10,0))

        top.columnconfigure(1,weight=1)

        bottom=ttk.Frame(self.t3,padding=(10,0,10,10))
        bottom.pack(fill="both",expand=True)

        cols=("name","url","format","status","progress","time")
        self.download_tree=ttk.Treeview(bottom,columns=cols,show="headings",height=8)
        for c in cols:
            self.download_tree.heading(c,text=c)
        self.download_tree.column("name",width=220)
        self.download_tree.column("url",width=420)
        self.download_tree.column("format",width=180)
        self.download_tree.column("status",width=100)
        self.download_tree.column("progress",width=80)
        self.download_tree.column("time",width=80)
        self.download_tree.pack(fill="both",expand=True)
        self.download_tree.bind("<Button-3>",self.download_menu_row)
        self.download_row_map={}

        self.update_download_mode()
        self.update_subtitle_state()
        self.after(200,self.poll_format_events)
        self.after(300,self.poll_download_events)

    def browse(self):
        f=filedialog.askopenfilename()
        if f:
            self.fv.set(f)

    def yt_dlp_path(self):
        exe="yt-dlp.exe" if os.name=="nt" else "yt-dlp"
        return os.path.join(os.path.dirname(os.path.abspath(__file__)),"bin",exe)

    def bin_path(self):
        return os.path.join(os.path.dirname(os.path.abspath(__file__)),"bin")

    def browse_download_folder(self):
        folder=filedialog.askdirectory()
        if folder:
            self.download_folder_var.set(folder)
            self.app_config["download_folder"]=folder
            save_config(self.app_config)

    def schedule_format_lookup(self):
        if self.format_lookup_after:
            self.after_cancel(self.format_lookup_after)
        self.format_lookup_after=self.after(800,self.lookup_formats)

    def update_download_mode(self):
        audio_only=self.download_mode_var.get()=="Audio"
        if audio_only:
            self.video_format_combo.configure(state="disabled")
            outputs=("mp3","m4a","aac","opus","flac","wav")
            if self.output_format_var.get() not in outputs:
                self.output_format_var.set("mp3")
        else:
            self.video_format_combo.configure(state="readonly")
            outputs=("mp4","mkv","webm")
            if self.output_format_var.get() not in outputs:
                self.output_format_var.set("mp4")
        self.output_format_combo["values"]=outputs

    def update_subtitle_state(self):
        if self.download_subtitles_var.get():
            self.subtitle_lang_combo.configure(state="readonly")
        else:
            self.subtitle_lang_combo.configure(state="disabled")

    def lookup_formats(self):
        url=self.download_url_var.get().strip()
        self.format_lookup_after=None
        self.audio_format_map={}
        self.video_format_map={}
        self.current_video_title=""
        self.current_video_language=""
        self.audio_format_combo["values"]=[]
        self.video_format_combo["values"]=[]
        self.audio_format_var.set("")
        self.video_format_var.set("")
        if not url:
            self.format_status_var.set("Enter a URL to load available formats")
            return

        self.format_status_var.set("Loading formats...")

        def run():
            try:
                cmd=[self.yt_dlp_path(),"--ffmpeg-location",self.bin_path(),"--dump-single-json","--no-playlist","--no-warnings",url]
                r=subprocess.run(cmd,cwd=os.path.dirname(os.path.abspath(__file__)),capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=60)
                if r.returncode:
                    raise RuntimeError((r.stderr or r.stdout or "yt-dlp could not read this URL").strip())
                info=json.loads(r.stdout)
                self.format_events.put(("formats",url,info))
            except Exception as e:
                self.format_events.put(("error",url,str(e)))

        threading.Thread(target=run,daemon=True).start()

    def poll_format_events(self):
        while True:
            try:
                kind,url,payload=self.format_events.get_nowait()
            except Empty:
                break

            if url != self.download_url_var.get().strip():
                continue

            if kind=="error":
                self.format_status_var.set(payload)
                continue

            audio_values=["Best audio"]
            video_values=["Best video"]
            self.audio_format_map={"Best audio":{"kind":"best_audio"}}
            self.video_format_map={"Best video":{"kind":"best_video"}}
            self.current_video_title=payload.get("title","")
            self.current_video_language=payload.get("language") or ""

            for fmt in payload.get("formats",[]):
                format_id=str(fmt.get("format_id",""))
                ext=fmt.get("ext") or "unknown"
                resolution=fmt.get("resolution") or (f"{fmt.get('width')}x{fmt.get('height')}" if fmt.get("width") and fmt.get("height") else "")
                note=fmt.get("format_note") or ""
                acodec=fmt.get("acodec") or ""
                vcodec=fmt.get("vcodec") or ""
                if not format_id:
                    continue

                if acodec and acodec != "none" and (not vcodec or vcodec == "none"):
                    abr=f"{fmt.get('abr')}k" if fmt.get("abr") else ""
                    label=" | ".join(part for part in (format_id,ext,note,abr,f"a:{acodec}") if part)
                    if label not in self.audio_format_map:
                        audio_values.append(label)
                        self.audio_format_map[label]={"kind":"format_id","format_id":format_id}

                if vcodec and vcodec != "none":
                    fps=f"{fmt.get('fps')}fps" if fmt.get("fps") else ""
                    label=" | ".join(part for part in (format_id,ext,resolution,note,fps,f"v:{vcodec}") if part)
                    if label not in self.video_format_map:
                        video_values.append(label)
                        self.video_format_map[label]={"kind":"format_id","format_id":format_id}

            self.audio_format_combo["values"]=audio_values
            self.video_format_combo["values"]=video_values
            if audio_values:
                self.audio_format_var.set(audio_values[0])
            if video_values:
                self.video_format_var.set(video_values[0])
            self.update_download_mode()
            if audio_values or video_values:
                self.format_status_var.set(f"{len(audio_values)} audio and {len(video_values)} video formats loaded")
            else:
                self.format_status_var.set("No formats found")

        self.after(200,self.poll_format_events)

    def add_download(self):
        url=self.download_url_var.get().strip()
        folder=self.download_folder_var.get().strip()
        mode=self.download_mode_var.get()
        audio_label=self.audio_format_var.get()
        video_label=self.video_format_var.get()
        output=self.output_format_var.get()
        if not url:
            messagebox.showwarning("Missing URL","Enter a URL first.",parent=self)
            return
        if not folder:
            messagebox.showwarning("Missing folder","Select a download folder first.",parent=self)
            return
        if not audio_label or audio_label not in self.audio_format_map:
            messagebox.showwarning("Missing audio format","Wait for formats to load, then select an audio format.",parent=self)
            return
        if mode=="Audio and video" and (not video_label or video_label not in self.video_format_map):
            messagebox.showwarning("Missing video format","Wait for formats to load, then select a video format.",parent=self)
            return
        if not output:
            messagebox.showwarning("Missing output","Select an output format.",parent=self)
            return

        os.makedirs(folder,exist_ok=True)
        self.app_config["download_folder"]=folder
        save_config(self.app_config)
        title=self.current_video_title or url
        subtitles_enabled=self.download_subtitles_var.get()
        sub_lang_name=self.subtitle_lang_var.get()
        sub_lang_code=next((code for name,code in SUBTITLE_LANGUAGES if name==sub_lang_name),"")
        label_extra=""
        if subtitles_enabled:
            label_extra=f" + subs ({sub_lang_name})"
        format_label=f"{mode} -> {output}{label_extra}"
        format_info={
            "mode":mode,
            "audio":self.audio_format_map[audio_label],
            "video":self.video_format_map.get(video_label),
            "output":output,
        }
        download_queue.append(VideoDownloadTask(
            url,folder,format_label,format_info,title,
            subtitles_enabled=subtitles_enabled,
            subtitle_lang=sub_lang_code,
            detected_language=self.current_video_language,
        ))
        self.refresh_download_queue()
        self.process_download_queue()

    def download_menu_row(self,e):
        item=self.download_tree.identify_row(e.y)
        if not item:
            return
        task=self.download_row_map.get(item)
        if not task:
            return
        m=tk.Menu(self,tearoff=0)
        if task.status in ("waiting","running"):
            m.add_command(label="Cancel",command=lambda:self.cancel_download(task))
        elif task.status in ("finished","cancelled","error"):
            m.add_command(label="Remove",command=lambda:self.remove_download(task))
        m.tk_popup(e.x_root,e.y_root)

    def cancel_download(self,task):
        task.cancelled=True
        task.status="cancelled"
        if task.process and task.process.poll() is None:
            task.process.terminate()
        self.refresh_download_queue()

    def remove_download(self,task):
        if task in download_queue:
            download_queue.remove(task)
        self.refresh_download_queue()

    def add(self):
        if not self.fv.get():
            return
        if not self.model_ready:
            if self.model_loading:
                self.log("Request was not queued because the model is still being checked.")
                return
            if not messagebox.askyesno("Model required","The Whisper model must be downloaded before requests can be queued. Download it now?",parent=self):
                self.log("Request was not queued because the required model is not ready.")
                return
            if not self.ensure_model_with_modal():
                self.log("Request was not queued because the required model is not ready.")
                return
        queue.append(TranscriptionTask(self.fv.get()))
        self.pb["value"]=0
        self.nb.select(self.t2)
        self.refresh()

    def menu_row(self,e):
        item=self.tree.identify_row(e.y)
        if not item:
            return

        self.tree.selection_set(item)

        task=self.row_map.get(item)

        if not task:
            return

        m=tk.Menu(self,tearoff=0)

        if task.status=="waiting":
            m.add_command(label="Cancel",command=lambda:self.cancel(task))

        elif task.status=="running":
            m.add_command(label="Cancel",command=lambda:self.cancel(task))

        elif task.status=="paused":
            m.add_command(label="Resume",command=lambda:self.resume(task))
            m.add_command(label="Cancel",command=lambda:self.cancel(task))

        elif task.status in ("finished","cancelled","error"):
            m.add_command(label="Remove",command=lambda:self.remove_task(task))

        m.tk_popup(e.x_root,e.y_root)

    def pause(self,t):
        t.paused=True
        t.status="paused"
        self.refresh()

    def resume(self,t):
        t.paused=False
        t.status="running"
        self.refresh()

    def cancel(self,t):
        t.cancelled=True
        t.status="cancelled"
        for worker in self.workers:
            if worker["task"] == t:
                self.log("Cancelling running task and restarting its worker...")
                worker["task"]=None
                if worker.get("temporary") and not any(task.status=="waiting" for task in queue):
                    self.retire_worker(worker)
                else:
                    self.restart_worker(worker)
                break
        self.refresh()

    def remove_task(self,t):
        if t in queue:
            queue.remove(t)
        self.refresh()

    def clear_completed(self):
        queue[:]=[t for t in queue if t.status not in ("finished","cancelled","error")]
        self.refresh()

    def fmt_time(self,t):
        if not t.start_time:
            return ""
        s=time.time()-t.start_time
        h=int(s//3600);m=int((s%3600)//60);sec=int(s%60)
        return f"{h:02}:{m:02}:{sec:02}"

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        self.row_map={}

        for idx,t in enumerate(queue):
            item_id=self.tree.insert("", "end", values=(
                os.path.basename(t.file_path),
                t.status,
                f"{t.progress}%",
                self.fmt_time(t)
            ))

            self.row_map[item_id]=t

    def refresh_download_queue(self):
        self.download_tree.delete(*self.download_tree.get_children())
        self.download_row_map={}

        for task in download_queue:
            item_id=self.download_tree.insert("", "end", values=(
                task.title,
                task.url,
                task.format_label,
                task.status,
                f"{task.progress}%",
                self.fmt_time(task)
            ))
            self.download_row_map[item_id]=task

    def log(self,msg):
        print(msg)
        self.txt.insert("end",msg+"\n")
        self.txt.see("end")

    def resolve_subtitle_lang(self,task):
        lang=task.subtitle_lang or task.detected_language or ""
        return lang.strip()

    def build_subtitle_command(self,task,lang):
        output=os.path.join(task.folder,"%(title)s.%(ext)s")
        return [
            self.yt_dlp_path(),
            "--ffmpeg-location",self.bin_path(),
            "--newline",
            "--skip-download",
            "--write-auto-subs",
            "--sub-langs",f"{lang}.*",
            "--no-playlist",
            "-o",output,
            task.url,
        ]

    def build_download_command(self,task):
        output=os.path.join(task.folder,"%(title)s.%(ext)s")
        command=[self.yt_dlp_path(),"--ffmpeg-location",self.bin_path(),"--newline","-o",output]
        fmt=task.format_info
        output_format=fmt.get("output","mp4")
        audio=fmt.get("audio") or {"kind":"best_audio"}
        video=fmt.get("video") or {"kind":"best_video"}

        if fmt.get("mode")=="Audio":
            audio_selector="ba/bestaudio" if audio["kind"]=="best_audio" else audio["format_id"]
            command.extend(["-f",audio_selector,"-x","--audio-format",output_format])
        else:
            if video["kind"]=="best_video":
                video_selector="bv*[ext=mp4]/bestvideo[ext=mp4]/bv*/bestvideo" if output_format=="mp4" else "bv*/bestvideo"
            else:
                video_selector=video["format_id"]
            if audio["kind"]=="best_audio":
                audio_selector="ba[ext=m4a]/bestaudio[ext=m4a]/ba/bestaudio" if output_format=="mp4" else "ba/bestaudio"
            else:
                audio_selector=audio["format_id"]
            command.extend(["-f",f"{video_selector}+{audio_selector}/best","--merge-output-format",output_format])
        command.append(task.url)
        return command

    def process_download_queue(self):
        global download_current
        if download_current:
            return
        task=next((t for t in download_queue if t.status=="waiting"),None)
        if not task:
            return

        download_current=task
        task.status="running"
        task.progress=0
        task.start_time=time.time()
        self.refresh_download_queue()

        def run():
            global download_current
            try:
                update_cmd=[self.yt_dlp_path(),"--update"]
                update=subprocess.run(update_cmd,cwd=os.path.dirname(os.path.abspath(__file__)),capture_output=True,text=True,encoding="utf-8",errors="replace")
                if update.stdout.strip():
                    self.download_events.put(("log",task,update.stdout.strip()))
                if update.stderr.strip():
                    self.download_events.put(("log",task,update.stderr.strip()))
                if update.returncode:
                    raise RuntimeError("yt-dlp update failed")

                if task.subtitles_enabled and not task.cancelled:
                    sub_lang=self.resolve_subtitle_lang(task)
                    if not sub_lang:
                        self.download_events.put(("log",task,"Skipping auto subtitles: original language could not be detected."))
                    else:
                        self.download_events.put(("log",task,f"Downloading auto subtitles (lang: {sub_lang})..."))
                        task.process=subprocess.Popen(
                            self.build_subtitle_command(task,sub_lang),
                            cwd=os.path.dirname(os.path.abspath(__file__)),
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            text=True,
                            encoding="utf-8",
                            errors="replace",
                            creationflags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0,
                        )
                        for line in task.process.stdout:
                            line=line.rstrip()
                            if line:
                                self.download_events.put(("log",task,line))
                        sub_rc=task.process.wait()
                        task.process=None
                        if task.cancelled:
                            self.download_events.put(("done",task,"cancelled"))
                            return
                        if sub_rc:
                            self.download_events.put(("log",task,f"Auto subtitle download exited with code {sub_rc} (continuing with media)"))

                task.process=subprocess.Popen(
                    self.build_download_command(task),
                    cwd=os.path.dirname(os.path.abspath(__file__)),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name=="nt" else 0,
                )

                percent_re=re.compile(r"\[download\]\s+(\d+(?:\.\d+)?)%")
                for line in task.process.stdout:
                    line=line.rstrip()
                    match=percent_re.search(line)
                    if match:
                        self.download_events.put(("progress",task,float(match.group(1))))
                    elif line:
                        self.download_events.put(("log",task,line))

                return_code=task.process.wait()
                if task.cancelled:
                    self.download_events.put(("done",task,"cancelled"))
                elif return_code:
                    self.download_events.put(("error",task,f"yt-dlp exited with code {return_code}"))
                else:
                    self.download_events.put(("done",task,"finished"))
            except Exception as e:
                self.download_events.put(("error",task,str(e)))
            finally:
                task.process=None

        threading.Thread(target=run,daemon=True).start()

    def poll_download_events(self):
        global download_current
        while True:
            try:
                kind,task,payload=self.download_events.get_nowait()
            except Empty:
                break

            if kind=="progress":
                task.progress=min(100,int(payload))
            elif kind=="log":
                self.log(payload)
            elif kind=="done":
                task.status=payload
                if payload=="finished":
                    task.progress=100
                if download_current == task:
                    download_current=None
                self.process_download_queue()
            elif kind=="error":
                task.status="error"
                self.log(payload)
                if download_current == task:
                    download_current=None
                self.process_download_queue()

            self.refresh_download_queue()

        self.after(300,self.poll_download_events)

    def process(self):
        if not queue:
            return

        waiting=[task for task in queue if task.status=="waiting"]
        if not waiting:
            return

        active_count=len(self.active_workers())
        idle_count=len(self.idle_workers())
        needed=min(len(waiting),self.parallel_workers)-idle_count
        for _ in range(max(0,needed)):
            if active_count >= self.parallel_workers:
                break
            self.start_worker(temporary=True)
            active_count+=1

        idle=self.idle_workers()
        if not idle:
            return

        for worker,t in zip(idle,waiting):
            worker["task"]=t
            t.status="running"
            t.progress=0
            t.start_time=time.time()
            self.update_overall_progress()

            try:
                command={"action":"transcribe","file_path":t.file_path}
                worker["process"].stdin.write(json.dumps(command)+"\n")
                worker["process"].stdin.flush()
            except Exception as e:
                t.status="error"
                worker["task"]=None
                self.log(f"Failed to start transcription: {e}")
                self.restart_worker(worker)

    def finish_worker_task(self, worker, keep_status=False):
        task=worker["task"]
        if not task:
            return
        if not keep_status and not task.cancelled:
            task.status="finished"
            task.progress=100
        worker["task"]=None
        self.update_overall_progress()
        if worker.get("temporary") and not any(t.status=="waiting" for t in queue):
            self.retire_worker(worker)

    def update_overall_progress(self):
        running=[t for t in queue if t.status=="running"]
        if not running:
            self.pb["value"]=0
            return
        self.pb["value"]=sum(t.progress for t in running)/len(running)

    def console(self):
        self.txt=tk.Text(self,height=8,bg="black",fg="lime")
        self.txt.pack(fill="x")

    def loop(self):
        self.refresh()
        self.process()
        self.process_download_queue()
        self.after(500,self.loop)

if __name__=="__main__":
    App().mainloop()

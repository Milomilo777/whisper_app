
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
import threading,time,os
from queue import Empty, Queue
from core.task import TranscriptionTask
from core.model_manager import DownloadCancelled
from core.transcriber import transcribe,load_model,load_existing_model,is_model_ready

queue=[]
current=None

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
            self.success=load_model(status,progress,self.cancel_event)
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

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Whisper GUI")
        self.geometry("900x600")
        self.protocol("WM_DELETE_WINDOW",self.on_exit)

        self.status_var=tk.StringVar(value="Initializing...")
        self.model_ready=False
        self.model_loading=False
        self.model_setup_running=False
        self.startup_events=Queue()

        self.menu()
        self.tabs()
        self.console()

        self.after(100,self.start_background_existing_model_load)
        self.after(300,self.loop)

    def model_status(self,msg):
        self.status_var.set(msg)
        self.log(msg)
        if "Model loaded" in msg:
            self.model_ready=True

    def start_background_existing_model_load(self):
        self.model_loading=True
        self.status_var.set("Loading existing model...")

        def run():
            def status(msg):
                self.startup_events.put(("status",msg))

            success=load_existing_model(status)
            self.startup_events.put(("done",success))

        threading.Thread(target=run,daemon=True).start()
        self.after(100,self.poll_startup_model_load)

    def poll_startup_model_load(self):
        while True:
            try:
                kind,payload=self.startup_events.get_nowait()
            except Empty:
                break

            if kind=="status":
                self.model_status(payload)
            elif kind=="done":
                self.model_loading=False
                if payload or is_model_ready():
                    self.model_ready=True
                    self.status_var.set("Model loaded")
                    return

                self.model_ready=False
                self.log("Existing model failed to load. Starting required download.")
                self.ensure_model_with_modal(mandatory=True)
                return

        if self.model_loading:
            self.after(100,self.poll_startup_model_load)

    def ensure_model_with_modal(self, mandatory=False):
        if self.model_ready or is_model_ready():
            self.model_ready=True
            self.status_var.set("Model loaded")
            return True

        if self.model_setup_running:
            return False

        self.model_setup_running=True
        dialog=ModelDownloadDialog(self)
        self.wait_window(dialog)
        self.model_setup_running=False

        if dialog.success or is_model_ready():
            self.model_ready=True
            self.status_var.set("Model loaded")
            self.log("Model loaded")
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
        if current or active:
            if not messagebox.askyesno("Exit with queued tasks","There are queued or running transcription tasks. Exit anyway?",parent=self):
                return
        self.destroy()

    def tabs(self):
        nb=ttk.Notebook(self);nb.pack(fill="both",expand=True)
        self.t1=ttk.Frame(nb);self.t2=ttk.Frame(nb)
        nb.add(self.t1,text="New");nb.add(self.t2,text="Queue")

        tk.Label(self.t1,text="File").grid(row=0,column=0)
        self.fv=tk.StringVar()
        tk.Entry(self.t1,textvariable=self.fv,width=60).grid(row=0,column=1)
        tk.Button(self.t1,text="Browse",command=self.browse).grid(row=0,column=2)
        tk.Button(self.t1,text="Transcribe",command=self.add).grid(row=1,column=1)

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

    def browse(self):
        f=filedialog.askopenfilename()
        if f:
            self.fv.set(f)

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
            m.add_command(label="Pause",command=lambda:self.pause(task))
            m.add_command(label="Cancel",command=lambda:self.cancel(task))

        elif task.status=="paused":
            m.add_command(label="Resume",command=lambda:self.resume(task))
            m.add_command(label="Cancel",command=lambda:self.cancel(task))

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

    def log(self,msg):
        print(msg)
        self.txt.insert("end",msg+"\n")
        self.txt.see("end")

    def process(self):
        global current

        if current or not queue:
            return

        t=queue[0]

        if t.status=="cancelled":
            queue.pop(0)
            return

        current=t

        def run():
            try:
                t.status="running"
                t.start_time=time.time()

                def prog(p):
                    t.progress=p
                    self.pb["value"]=p

                transcribe(t,prog,self.log)

                if not t.cancelled:
                    t.status="finished"
                    t.progress=100

            except Exception as e:
                t.status="error"
                self.log(str(e))

            finally:
                if queue and queue[0]==t:
                    queue.pop(0)

                globals()["current"]=None

        threading.Thread(target=run,daemon=True).start()

    def console(self):
        self.txt=tk.Text(self,height=8,bg="black",fg="lime")
        self.txt.pack(fill="x")

    def loop(self):
        self.refresh()
        self.process()
        self.after(500,self.loop)

if __name__=="__main__":
    App().mainloop()


import tkinter as tk
from tkinter import ttk,filedialog,messagebox
import threading,time,os
from core.task import TranscriptionTask
from core.transcriber import transcribe,start_background_model_load

queue=[]
current=None

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Whisper GUI")
        self.geometry("900x600")

        self.status_var=tk.StringVar(value="Initializing...")
        self.model_ready=False

        self.menu()
        self.tabs()
        self.console()

        start_background_model_load(self.model_status)

        self.after(300,self.loop)

    def model_status(self,msg):
        self.status_var.set(msg)
        self.log(msg)
        if "Model loaded" in msg:
            self.model_ready=True

    def menu(self):
        m=tk.Menu(self)
        f=tk.Menu(m,tearoff=0)
        f.add_command(label="Exit",command=self.quit)
        a=tk.Menu(m,tearoff=0)
        a.add_command(label="About",command=lambda:messagebox.showinfo("About","Whisper"))
        m.add_cascade(label="File",menu=f)
        m.add_cascade(label="About",menu=a)
        self.config(menu=m)

    def tabs(self):
        nb=ttk.Notebook(self);nb.pack(fill="both",expand=True)
        self.t1=ttk.Frame(nb);self.t2=ttk.Frame(nb)
        nb.add(self.t1,text="New");nb.add(self.t2,text="Queue")

        tk.Label(self.t1,text="File").grid(row=0,column=0)
        self.fv=tk.StringVar()
        tk.Entry(self.t1,textvariable=self.fv,width=60).grid(row=0,column=1)
        tk.Button(self.t1,text="Browse",command=self.browse).grid(row=0,column=2)
        tk.Button(self.t1,text="Add",command=self.add).grid(row=1,column=1)

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


import os,time,json,subprocess,threading
from faster_whisper import WhisperModel
from .config import load_config
from .model_manager import ensure_model

config = load_config()

MODEL=None
MODEL_READY=False
MODEL_ERROR=None

def log(msg, cb=None):
    print(msg)
    if cb: cb(msg)

def detect_device():
    try:
        import torch
        if config["device"]=="auto" and torch.cuda.is_available():
            return "cuda","float16"
    except:
        pass
    return "cpu",config["compute_type"]

device,compute_type=detect_device()

def load_model_async(status_cb=None):
    global MODEL, MODEL_READY, MODEL_ERROR
    try:
        model_path=ensure_model(config, status_cb)
        if status_cb: status_cb("Loading Whisper model...")
        MODEL=WhisperModel(model_path,device=device,compute_type=compute_type)
        MODEL_READY=True
        if status_cb: status_cb("Model loaded")
    except Exception as e:
        MODEL_ERROR=str(e)
        if status_cb: status_cb(f"ERROR: {e}")

def start_background_model_load(status_cb=None):
    threading.Thread(target=load_model_async,args=(status_cb,),daemon=True).start()

def get_duration(path):
    r=subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",path],capture_output=True,text=True)
    return float(r.stdout.strip())

def fmt(sec):
    h=int(sec//3600);m=int((sec%3600)//60);s=int(sec%60)
    return f"{h:02}:{m:02}:{s:02}"

def transcribe(task,progress_cb=None,log_cb=None):
    global MODEL
    while not MODEL_READY:
        if MODEL_ERROR:
            raise RuntimeError(MODEL_ERROR)
        time.sleep(0.5)

    duration=get_duration(task.file_path)
    start=time.time()
    log(f"Processing: {task.file_path}",log_cb)

    segments,_=MODEL.transcribe(task.file_path)
    base=os.path.splitext(task.file_path)[0]

    srt=[];data=[]
    for i,seg in enumerate(segments,1):
        if task.cancelled:
            log("Task cancelled",log_cb)
            return

        while task.paused and not task.cancelled:
            time.sleep(0.2)

        percent=min(100,int((seg.end/duration)*100))
        msg=f"[{percent}%] {fmt(seg.start)} --> {fmt(seg.end)} | {seg.text.strip()}"
        log(msg,log_cb)

        if progress_cb:
            progress_cb(percent)

        srt.append(f"{i}\n{fmt(seg.start)} --> {fmt(seg.end)}\n{seg.text.strip()}\n")
        data.append({"start":seg.start,"end":seg.end,"text":seg.text.strip()})

    with open(base+".srt","w",encoding="utf-8") as f:
        f.write("\n".join(srt))

    with open(base+".json","w",encoding="utf-8") as f:
        json.dump(data,f,indent=2)

    if progress_cb:
        progress_cb(100)

    elapsed=time.time()-start
    log(f"Done in {elapsed:.2f}s",log_cb)

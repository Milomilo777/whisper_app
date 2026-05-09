import json, os, sys

def config_path():
    base = os.path.dirname(sys.executable if getattr(sys,"frozen",False) else __file__)
    return os.path.abspath(os.path.join(base, "..", "config.json"))

def load_config():
    with open(config_path(),"r") as f:
        return json.load(f)

def save_config(config):
    with open(config_path(),"w") as f:
        json.dump(config,f,indent=2)
        f.write("\n")

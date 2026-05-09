import json, os, sys
def load_config():
    base = os.path.dirname(sys.executable if getattr(sys,"frozen",False) else __file__)
    config_path = os.path.abspath(os.path.join(base, "..", "config.json"))
    with open(config_path,"r") as f:
        return json.load(f)

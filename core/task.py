class TranscriptionTask:
    def __init__(self, file_path):
        self.file_path = file_path
        self.status = "waiting"
        self.progress = 0
        self.start_time = None
        self.paused = False
        self.cancelled = False

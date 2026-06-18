from enum import Enum
from pathlib import Path

import threading
file_lock = threading.Lock()

class LogLevel(Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    FATAL = "FATAL"

class Logger:
    LOG_FILE = "log.txt"
    FILE_PATH = Path(LOG_FILE)

    def __init__(self):
        # Create the file if it doesn't exist
        # If it does exist just keep the OG file
        self.FILE_PATH.touch(exist_ok=True)

    def log(self, level: LogLevel, info: str):
        # Prints both to screen and also saves to file
        print(f"{level.value}: {info}")
        with file_lock:
            with open(self.LOG_FILE, "a", encoding="utf-8") as f:
                f.write(f"{level.value}: {info}\n")

                

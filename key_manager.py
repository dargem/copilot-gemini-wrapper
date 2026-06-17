import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from collections import deque

load_dotenv()
GEMINI_API_KEY = os.getenv("KEY_0")

class Limits:
    def __init__(self, RPM, TPM, RPD):
        self.RPM = RPM
        self.TPM = TPM
        self.RPD = RPD

# Update when changed
# https://aistudio.google.com/rate-limit?timeRange=last-28-days
model_limits = {
    "gemini-3.5-flash": Limits(5, 250000, 20),
    "gemini-3-flash": Limits(5, 250000, 20),
    "gemini-3.1-flash-lite": Limits(15, 250000, 500) # but its kinda shit
}

class ModelUsage:

    def __init__(self, limits: Limits):
        self.limits = limits
        self.rolling_TPM = 0
        self.RPD_Made = 0
        # API limits reset at midnight
        self.last_request_date = datetime.now(ZoneInfo("America/Los_Angeles")).date()
        self.past_uses = deque()

    def check_availability(self):
        today = datetime.now(ZoneInfo("America/Los_Angeles")).date()

        if self.last_request_date < today:
            # We can reset our rate limits for today
            self.RPD_Made = 0
        
        if self.RPD_Made >= self.limits.RPD:
            return False
        if self.rolling_TPM >= self.limits.TPM:
            return False
        if len(self.past_uses) >= self.limits.RPM:
            return False
        
        return True

    def record_use(self, tokens_used):
        current_time = datetime.now(ZoneInfo("America/Los_Angeles"))

        class Record:
            def __init__(self, tokens_used, date):
                self.tokens = tokens_used
                self.date = date

        self.last_request_date = current_time.date()
        self.past_uses.append(Record(tokens_used, current_time))
        self.rolling_TPM += tokens_used
        self.RPD_Made += 1

        while (len(self.past_uses) > 0):
            # Add some leeway on the 1 minute reset
            if current_time - self.past_uses[0].date > timedelta(minutes=1, seconds=5):
                record = self.past_uses.popleft()
                self.rolling_TPM -= record.tokens
            else:
                # Early break its a queue data structure
                break


class KeyInfo:
    def __init__(self, key):
        self.key = key

class KeyManager:
    def __init__(self):
        self.keys = [key for id, key in os.environ.items() if "KEY_" in id]


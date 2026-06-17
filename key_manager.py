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
    "gemini-3.1-flash-lite": Limits(15, 250000, 500)
}

class Record:
    def __init__(self, tokens_used, date):
        self.tokens = tokens_used
        self.date = date
        
class ModelUsage:

    def __init__(self, limits: Limits):
        self.limits = limits
        self.rolling_TPM = 0
        self.RPD_Made = 0
        # API limits reset at midnight
        self.last_request_date = datetime.now(ZoneInfo("America/Los_Angeles")).date()
        self.past_uses = deque()

    def check_availability(self):
        """Call before reserving this model to see if you can"""
        now = datetime.now(ZoneInfo("America/Los_Angeles"))
        today = now.date()

        while len(self.past_uses) > 0 and now - self.past_uses[0].date > timedelta(minutes=1, seconds=5):
            record = self.past_uses.popleft()
            self.rolling_TPM -= record.tokens

        if self.last_request_date < today:
            # We can reset our rate limits for today
            self.RPD_Made = 0
            self.last_request_date = today
        
        if self.RPD_Made >= self.limits.RPD:
            return False
        if self.rolling_TPM >= self.limits.TPM:
            return False
        if len(self.past_uses) >= self.limits.RPM:
            return False
        
        return True

    def reserve(self) -> Record:
        """Call the moment you commit to this key, before the request goes out."""
        current_time = datetime.now(ZoneInfo("America/Los_Angeles"))
        self.last_request_date = current_time.date()

        record = Record(0, current_time)
        self.past_uses.append(record)
        self.RPD_Made += 1
        return record

    def finalize(self, record, tokens_used):
        """Call once you know the real token count, after the response completes."""
        if self.past_uses:
            record.tokens = tokens_used
            self.rolling_TPM += tokens_used

class KeyInfo:
    def __init__(self, key):
        self.key = key
        self.model_usages = {model: ModelUsage(limit) for model, limit in model_limits.items()}

    def has_model_available(self, model):
        return self.model_usages[model].check_availability()
    
    def reserve_model(self, model) -> Record:
        return self.model_usages[model].reserve()
    
    def finalize(self, model, record: Record, tokens_used):
        self.model_usages[model].finalize(record, tokens_used)

class KeyManager:
    def __init__(self):
        self.keys = [key for id, key in os.environ.items() if "KEY_" in id]


import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from collections import deque
from enum import Enum

load_dotenv()
GEMINI_API_KEY = os.getenv("KEY_0")

class Limits:
    def __init__(self, RPM, TPM, RPD):
        self.RPM = RPM
        self.TPM = TPM
        self.RPD = RPD

# Update when changed, put preferred models higher
# https://aistudio.google.com/rate-limit?timeRange=last-28-days
model_limits = {
    "gemini-3.5-flash": Limits(5, 250000, 20),
    "gemini-3-flash-preview": Limits(5, 250000, 20),
    "gemini-3.1-flash-lite": Limits(15, 250000, 500)
}

class Record:
    def __init__(self, tokens_used, date):
        self.tokens = tokens_used
        self.date = date
        self.RPM_error = False
        self.TPM_error = False
        self.RPD_error = False

        
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

    def finalize(self, record: Record, tokens_used):
        """Call once you know the real token count, after the response completes."""
        if self.past_uses:
            record.tokens = tokens_used
            self.rolling_TPM += tokens_used

        # We may have gotten an error also, our tracking isn't persistent between server saves
        # and stuff can be finicky so if API returns an error we update to match it
        if record.RPD_error:
            self.RPD_Made = self.limits.RPD
        if record.RPM_error:
            for _ in range(self.limits.RPM):
                self.past_uses.append(Record(0, datetime.now(ZoneInfo("America/Los_Angeles"))))
        if record.TPM_error:
            self.past_uses.append(Record(self.limits.TPM, datetime.now(ZoneInfo("America/Los_Angeles"))))

class KeyInfo:
    def __init__(self):
        self.model_usages = {model: ModelUsage(limit) for model, limit in model_limits.items()}

    def has_model_available(self, model):
        return self.model_usages[model].check_availability()
    
    def reserve_model(self, model) -> Record:
        return self.model_usages[model].reserve()
    
    def finalize(self, model, record: Record, tokens_used):
        self.model_usages[model].finalize(record, tokens_used)

class APIRecord:
    def __init__(self, api_key, model, record: Record):
        self.key = api_key
        self.model = model
        self.record = record

class ModelManager:
    def __init__(self):
        self.key_infos = {key : KeyInfo() for id, key in os.environ.items() if "KEY_" in id}

    def reserve_model(self, model) -> APIRecord:
        for key, info in self.key_infos.items():

            if not info.has_model_available(model):
                continue

            return APIRecord(key, model, info.reserve_model(model))
        
        # In this case no models are available of this type so throw
        raise Exception("No keys have this model currently available")
    
    """ Can return None if all models are exhausted """
    def reserve_best_model(self) -> APIRecord:
        for model in model_limits.keys():
            # The preferred models are inserted first
            try:
                return self.reserve_model(model)
            except Exception:
                # Give up if no keys are currently available for this model
                # And try it with just a worse model
                pass
    
        return None
    
    def finalize(self, API_record: APIRecord, tokens_used):
        self.key_infos[API_record.key].finalize(API_record.model, API_record.record, tokens_used)

            


    


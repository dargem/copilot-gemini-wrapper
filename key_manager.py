class Limits:
    RPM = 0
    TPM = 0
    RPD = 0

    def __init__(self, RPM, TPM, RPD):
        self.RPM = RPM
        self.TPM = TPM
        self.RPD = RPD

model_limits = {
    "gemini-3.5-flash": Limits(5, 250000, 20),
    "gemini-3-flash": Limits(5, 250000, 20),
    "gemini-3.1-flash-lite": Limits(15, 250000, 500) # but its kinda shit
}


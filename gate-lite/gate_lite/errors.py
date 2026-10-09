"""Structured refusals raised when a gate-lite runtime is not qualified."""


class PreflightError(RuntimeError):
    def __init__(self, code: str, message: str, *, expected=None, found=None, action=None):
        super().__init__(message)
        self.code = code
        self.expected = expected
        self.found = found
        self.action = action or "install the pinned gate-lite dependencies and retry"

    def as_dict(self):
        return {
            "error": self.code,
            "detail": str(self),
            "expected": self.expected,
            "found": self.found,
            "action": self.action,
        }

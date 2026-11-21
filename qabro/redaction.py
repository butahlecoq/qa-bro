"""Redact known credentials before storing browser evidence."""

import re


REDACTED = "[redacted]"
SENSITIVE_KEYS = frozenset({
    "authorization", "proxyauthorization", "cookie", "setcookie",
    "password", "passwd", "secret", "token", "accesstoken", "refreshtoken", "apikey",
})
HEADER = re.compile(r"(?im)^(\s*(?:authorization|proxy-authorization|cookie|set-cookie)\s*:)[^\r\n]*")


class TraceRedactor:
    def __init__(self, secrets: tuple[str, ...] = ()):
        self._secrets = tuple(sorted({secret for secret in secrets if secret}, key=len, reverse=True))

    def __call__(self, value: object) -> object:
        if isinstance(value, str):
            for secret in self._secrets:
                value = value.replace(secret, REDACTED)
            return HEADER.sub(r"\1 " + REDACTED, value)
        if isinstance(value, dict):
            return {
                key: REDACTED if self._sensitive_key(key) else self(item)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [self(item) for item in value]
        return value

    @staticmethod
    def _sensitive_key(key: str) -> bool:
        return re.sub(r"[^a-z]", "", key.lower()) in SENSITIVE_KEYS

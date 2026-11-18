import hashlib
import json


def cache_key(prefix: str, payload) -> str:
    """Stable cache key: prefix plus a hash of the JSON-serialised payload."""
    digest = hashlib.sha1(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
    return prefix + digest

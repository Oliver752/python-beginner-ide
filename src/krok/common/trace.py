"""Model stopy vykonávania spoločný pre backend a frontend."""

from dataclasses import dataclass

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class Limits:
    """Tvrdé limity záznamu (NFR-02). Po prekročení vznikne čiastočná stopa."""

    steps: int = 100_000
    seconds: float = 15.0
    memory_mb: int = 256

"""Priority-based input source arbitration with stale-heartbeat failover."""
from dataclasses import dataclass
from enum import IntEnum
from threading import RLock
from time import monotonic
from typing import Optional

class SourcePriority(IntEnum):
    REMOTE = 10
    VISION = 20
    AIRPODS = 30

@dataclass(frozen=True)
class SourceState:
    name: str
    priority: SourcePriority
    connected: bool
    enabled: bool
    last_seen: float

class SourceArbiter:
    def __init__(self, stale_after: float = 2.0) -> None:
        if stale_after <= 0:
            raise ValueError("stale_after must be positive")
        self.stale_after = stale_after
        self._sources: dict[str, SourceState] = {}
        self._active: Optional[str] = None
        self._lock = RLock()

    def update(self, name: str, priority: SourcePriority, *, connected: bool,
               enabled: bool = True, now: Optional[float] = None) -> Optional[str]:
        if not name:
            raise ValueError("source name cannot be empty")
        stamp = monotonic() if now is None else now
        with self._lock:
            self._sources[name] = SourceState(name, priority, connected, enabled, stamp)
            self._active = self._choose(stamp)
            return self._active

    def heartbeat(self, name: str, *, now: Optional[float] = None) -> Optional[str]:
        stamp = monotonic() if now is None else now
        with self._lock:
            old = self._sources.get(name)
            if old is None:
                return self._active
            self._sources[name] = SourceState(old.name, old.priority, old.connected, old.enabled, stamp)
            self._active = self._choose(stamp)
            return self._active

    def active_source(self, *, now: Optional[float] = None) -> Optional[str]:
        stamp = monotonic() if now is None else now
        with self._lock:
            self._active = self._choose(stamp)
            return self._active

    def _choose(self, now: float) -> Optional[str]:
        live = [s for s in self._sources.values()
                if s.connected and s.enabled and 0 <= now - s.last_seen <= self.stale_after]
        return max(live, key=lambda s: (s.priority, s.last_seen)).name if live else None

"""AirCursor Core Engine (Cross-Platform).

Reverse-engineered from macOS AirCursor Swift codebase.
Provides exact algorithmic equivalence with zero external dependencies.
"""

from .actions import (
    ACTION_GROUPS,
    ActionMap,
    PointerAction,
    Trigger,
)
from .dwell import (
    DwellDetector,
    DwellUpdate,
)
from .gestures import (
    GestureDetector,
    GestureEvent,
    HeadGesture,
)
from .math_util import (
    AngleMath,
    Vec2,
)
from .motion import (
    AngularRates,
    MotionDifferentiator,
    MotionSample,
)
from .pointer import (
    CursorHistory,
    PointerMapper,
    PointerSmoother,
)
from .settings import (
    AppSettings,
    DwellSettings,
    GestureSettings,
    PointerSettings,
)
from .updates import (
    AppVersion,
    AvailableUpdate,
    ReleaseAsset,
    ReleaseInfo,
    ReleaseNotes,
    UpdatePolicy,
)
from .arbiter import (
    FallbackPolicy,
    InputArbiter,
    TrackingSource,
)
from .vision_tracker import (
    HandGesture,
    VisionFrameResult,
    VisionTracker,
    VisionTrackerSettings,
    VisionTrackerState,
)
from .pairing_qr import (
    PairingQR,
    get_local_ip,
    get_pairing_url,
)
from .web_remote_server import (
    WebRemoteRequestHandler,
    WebRemoteServer,
)

__version__ = "1.0.5"

__all__ = [
    # Math
    "Vec2",
    "AngleMath",
    # Motion
    "MotionSample",
    "AngularRates",
    "MotionDifferentiator",
    # Pointer
    "PointerMapper",
    "PointerSmoother",
    "CursorHistory",
    # Gestures
    "HeadGesture",
    "GestureEvent",
    "GestureDetector",
    # Dwell
    "DwellDetector",
    "DwellUpdate",
    # Actions
    "Trigger",
    "PointerAction",
    "ActionMap",
    "ACTION_GROUPS",
    # Settings
    "PointerSettings",
    "GestureSettings",
    "DwellSettings",
    "AppSettings",
    # Updates
    "AppVersion",
    "ReleaseAsset",
    "ReleaseInfo",
    "AvailableUpdate",
    "ReleaseNotes",
    "UpdatePolicy",
    # Arbiter
    "TrackingSource",
    "FallbackPolicy",
    "InputArbiter",
    # Vision
    "HandGesture",
    "VisionTrackerState",
    "VisionFrameResult",
    "VisionTrackerSettings",
    "VisionTracker",
    # Pairing & QR
    "PairingQR",
    "get_local_ip",
    "get_pairing_url",
    # Web Remote Server
    "WebRemoteServer",
    "WebRemoteRequestHandler",
]

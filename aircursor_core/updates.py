"""Release checking and version comparison logic.

Matches AirCursor/Sources/AirCursorCore/Updates.swift.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Union


class AppVersion:
    """A dotted release version such as "1.0.4" or tag "v1.2".

    Pre-release suffixes ("-beta.1", "+build") are ignored, so "1.1.0-beta" compares equal to "1.1.0".
    """

    def __init__(self, string: str):
        s = string.strip()
        if not s:
            raise ValueError("Empty version string")
        if s.startswith("v") or s.startswith("V"):
            s = s[1:]
        # Cut off pre-release / build metadata
        for cut_char in ("-", "+"):
            if cut_char in s:
                s = s.split(cut_char, 1)[0]

        parts = s.split(".")
        if not (1 <= len(parts) <= 4):
            raise ValueError(f"Invalid part count in version: {string}")

        numbers: List[int] = []
        for part in parts:
            if not part.isascii() or not part.isdigit():
                raise ValueError(f"Invalid version component: {part}")
            numbers.append(int(part))

        # Trailing zeros don't matter: 1.2 == 1.2.0.
        while len(numbers) > 1 and numbers[-1] == 0:
            numbers.pop()

        self.components: List[int] = numbers

    @classmethod
    def parse(cls, string: str) -> Optional[AppVersion]:
        try:
            return cls(string)
        except Exception:
            return None

    @property
    def description(self) -> str:
        parts = list(self.components)
        while len(parts) < 3:
            parts.append(0)
        return ".".join(str(p) for p in parts)

    def __str__(self) -> str:
        return self.description

    def __repr__(self) -> str:
        return f"AppVersion({self.description!r})"

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, AppVersion):
            return False
        max_len = max(len(self.components), len(other.components))
        for i in range(max_len):
            l = self.components[i] if i < len(self.components) else 0
            r = other.components[i] if i < len(other.components) else 0
            if l != r:
                return False
        return True

    def __lt__(self, other: Any) -> bool:
        if not isinstance(other, AppVersion):
            return NotImplemented
        max_len = max(len(self.components), len(other.components))
        for i in range(max_len):
            l = self.components[i] if i < len(self.components) else 0
            r = other.components[i] if i < len(other.components) else 0
            if l != r:
                return l < r
        return False

    def __le__(self, other: Any) -> bool:
        return self < other or self == other

    def __gt__(self, other: Any) -> bool:
        return not (self <= other)

    def __ge__(self, other: Any) -> bool:
        return not (self < other)


@dataclass
class ReleaseAsset:
    """A file attached to a GitHub release."""

    name: str
    url: str
    size: int


@dataclass
class ReleaseInfo:
    """The parts of GitHub's "latest release" response that AirCursor uses."""

    tag_name: str
    html_url: str
    name: Optional[str] = None
    body: Optional[str] = None
    draft: bool = False
    prerelease: bool = False
    assets: List[ReleaseAsset] = field(default_factory=list)

    # CamelCase property aliases
    @property
    def tagName(self) -> str:
        return self.tag_name

    @property
    def htmlURL(self) -> str:
        return self.html_url

    @property
    def file_version(self) -> str:
        """The version as the release workflow writes it in file names ("v1.0.5" -> "1.0.5")."""
        if self.tag_name.startswith("v") or self.tag_name.startswith("V"):
            return self.tag_name[1:]
        return self.tag_name

    fileVersion = file_version

    @property
    def archive(self) -> Optional[ReleaseAsset]:
        target = f"AirCursor-{self.file_version}.zip"
        for a in self.assets:
            if a.name == target:
                return a
        return None

    @property
    def archive_signature(self) -> Optional[ReleaseAsset]:
        target = f"AirCursor-{self.file_version}.zip.sig"
        for a in self.assets:
            if a.name == target:
                return a
        return None

    archiveSignature = archive_signature

    @property
    def version(self) -> Optional[AppVersion]:
        return AppVersion.parse(self.tag_name)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> ReleaseInfo:
        assets_data = d.get("assets", [])
        assets = [
            ReleaseAsset(
                name=a.get("name", ""),
                url=a.get("browser_download_url", a.get("url", "")),
                size=a.get("size", 0),
            )
            for a in assets_data
            if isinstance(a, dict)
        ]
        return cls(
            tag_name=d.get("tag_name", ""),
            html_url=d.get("html_url", ""),
            name=d.get("name"),
            body=d.get("body"),
            draft=d.get("draft", False),
            prerelease=d.get("prerelease", False),
            assets=assets,
        )


@dataclass
class AvailableUpdate:
    """A newer release the user hasn't dismissed."""

    version: AppVersion
    release: ReleaseInfo


class ReleaseNotes:
    """Turns GitHub's generated release notes into short plain lines."""

    PR_SUFFIX_PATTERN = re.compile(r"\s+by @[A-Za-z0-9-]+(\[bot\])?\s+in\s+\S+$")

    @classmethod
    def summary(cls, body: Optional[str], max_lines: int = 8) -> List[str]:
        if not body:
            return []
        lines: List[str] = []
        for raw in body.splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or line.startswith("**Full Changelog**") or line.startswith("<!--"):
                continue
            for bullet in ("* ", "- ", "+ "):
                if line.startswith(bullet):
                    line = line[len(bullet) :]
                    break
            line = cls.PR_SUFFIX_PATTERN.sub("", line)
            line = line.strip()
            if line:
                lines.append(line)
            if len(lines) == max_lines:
                break
        return lines


class UpdatePolicy:
    """Policy for checking and offering updates."""

    CHECK_INTERVAL: float = 24.0 * 60.0 * 60.0  # 1 day in seconds
    checkInterval: float = CHECK_INTERVAL

    @classmethod
    def is_check_due(
        cls,
        last_check: Optional[Union[float, datetime]],
        now: Union[float, datetime],
        interval: float = CHECK_INTERVAL,
    ) -> bool:
        if last_check is None:
            return True

        t_last = last_check.timestamp() if isinstance(last_check, datetime) else float(last_check)
        t_now = now.timestamp() if isinstance(now, datetime) else float(now)

        # Clock moved backwards shouldn't block checks forever
        if t_last > t_now:
            return True
        return (t_now - t_last) >= interval

    isCheckDue = is_check_due

    @classmethod
    def update(
        cls,
        current: str,
        release: ReleaseInfo,
        skipped_version: Optional[str] = None,
        include_skipped: bool = False,
    ) -> Optional[AvailableUpdate]:
        if release.draft or release.prerelease:
            return None

        latest = release.version
        installed = AppVersion.parse(current)
        if latest is None or installed is None:
            return None

        if not (latest > installed):
            return None

        if not include_skipped and skipped_version is not None:
            skipped = AppVersion.parse(skipped_version)
            if skipped is not None and skipped == latest:
                return None

        return AvailableUpdate(version=latest, release=release)

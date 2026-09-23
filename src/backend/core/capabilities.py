"""Non-authoritative product capability contract for clients."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class CapabilitySet:
    local_file_picker: bool = False
    model_download: bool = False
    billing: bool = False
    workspace_members: bool = False

    def to_dict(self) -> dict[str, bool]:
        return asdict(self)

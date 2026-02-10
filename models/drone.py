"""
Drone model — dataclass representing a drone in the fleet.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)


def _parse_list(raw: str) -> List[str]:
    if not raw or str(raw).strip() in ("", "–", "-", "nan", "None"):
        return []
    return [item.strip() for item in str(raw).split(",") if item.strip()]


def _parse_date(raw: str) -> Optional[date]:
    if not raw or str(raw).strip() in ("", "–", "-", "nan", "None"):
        return None
    try:
        return datetime.strptime(str(raw).strip(), "%Y-%m-%d").date()
    except ValueError:
        logger.warning(f"Invalid date format: {raw}")
        return None


@dataclass
class Drone:
    drone_id: str
    model: str
    capabilities: List[str] = field(default_factory=list)
    status: str = "Available"  # Available | Assigned | Maintenance
    location: str = ""
    current_assignment: str = ""
    maintenance_due: Optional[date] = None

    @classmethod
    def from_dict(cls, row: dict) -> Drone:
        """Create a Drone from a CSV/sheet row dictionary."""
        assignment = str(row.get("current_assignment", "")).strip()
        if assignment in ("–", "-", "", "nan", "None"):
            assignment = ""
        return cls(
            drone_id=str(row.get("drone_id", "")).strip(),
            model=str(row.get("model", "")).strip(),
            capabilities=_parse_list(row.get("capabilities", "")),
            status=str(row.get("status", "Available")).strip(),
            location=str(row.get("location", "")).strip(),
            current_assignment=assignment,
            maintenance_due=_parse_date(row.get("maintenance_due", "")),
        )

    def to_dict(self) -> dict:
        return {
            "drone_id": self.drone_id,
            "model": self.model,
            "capabilities": ", ".join(self.capabilities),
            "status": self.status,
            "location": self.location,
            "current_assignment": self.current_assignment or "–",
            "maintenance_due": self.maintenance_due.isoformat() if self.maintenance_due else "",
        }

    @property
    def is_available(self) -> bool:
        return self.status == "Available"

    @property
    def needs_maintenance(self) -> bool:
        if self.maintenance_due is None:
            return False
        return self.maintenance_due <= date.today()

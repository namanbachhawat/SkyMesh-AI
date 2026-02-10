"""
Pilot model — dataclass representing a drone pilot.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)


def _parse_list(raw: str) -> List[str]:
    """Parse a comma-separated string into a cleaned list."""
    if not raw or str(raw).strip() in ("", "–", "-", "nan", "None"):
        return []
    return [item.strip() for item in str(raw).split(",") if item.strip()]


def _parse_date(raw: str) -> Optional[date]:
    """Parse a date string (YYYY-MM-DD) safely."""
    if not raw or str(raw).strip() in ("", "–", "-", "nan", "None"):
        return None
    try:
        return datetime.strptime(str(raw).strip(), "%Y-%m-%d").date()
    except ValueError:
        logger.warning(f"Invalid date format: {raw}")
        return None


@dataclass
class Pilot:
    pilot_id: str
    name: str
    skills: List[str] = field(default_factory=list)
    certifications: List[str] = field(default_factory=list)
    location: str = ""
    status: str = "Available"  # Available | Assigned | On Leave
    current_assignment: str = ""
    available_from: Optional[date] = None

    @classmethod
    def from_dict(cls, row: dict) -> Pilot:
        """Create a Pilot from a CSV/sheet row dictionary."""
        assignment = str(row.get("current_assignment", "")).strip()
        if assignment in ("–", "-", "", "nan", "None"):
            assignment = ""
        return cls(
            pilot_id=str(row.get("pilot_id", "")).strip(),
            name=str(row.get("name", "")).strip(),
            skills=_parse_list(row.get("skills", "")),
            certifications=_parse_list(row.get("certifications", "")),
            location=str(row.get("location", "")).strip(),
            status=str(row.get("status", "Available")).strip(),
            current_assignment=assignment,
            available_from=_parse_date(row.get("available_from", "")),
        )

    def to_dict(self) -> dict:
        """Serialize back to a flat dict for CSV/Sheets writing."""
        return {
            "pilot_id": self.pilot_id,
            "name": self.name,
            "skills": ", ".join(self.skills),
            "certifications": ", ".join(self.certifications),
            "location": self.location,
            "status": self.status,
            "current_assignment": self.current_assignment or "–",
            "available_from": self.available_from.isoformat() if self.available_from else "",
        }

    @property
    def is_available(self) -> bool:
        return self.status == "Available"

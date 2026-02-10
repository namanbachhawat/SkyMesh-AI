"""
Mission model — dataclass representing a drone mission / project.
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


# Priority ranking for comparison (lower number = higher urgency)
PRIORITY_RANK = {
    "Urgent": 1,
    "High": 2,
    "Standard": 3,
    "Low": 4,
}


@dataclass
class Mission:
    project_id: str
    client: str
    location: str = ""
    required_skills: List[str] = field(default_factory=list)
    required_certs: List[str] = field(default_factory=list)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    priority: str = "Standard"
    assigned_pilot: str = ""
    assigned_drone: str = ""

    @classmethod
    def from_dict(cls, row: dict) -> Mission:
        """Create a Mission from a CSV/sheet row dictionary."""
        assigned_pilot = str(row.get("assigned_pilot", "")).strip()
        if assigned_pilot in ("–", "-", "", "nan", "None"):
            assigned_pilot = ""
        assigned_drone = str(row.get("assigned_drone", "")).strip()
        if assigned_drone in ("–", "-", "", "nan", "None"):
            assigned_drone = ""
        return cls(
            project_id=str(row.get("project_id", "")).strip(),
            client=str(row.get("client", "")).strip(),
            location=str(row.get("location", "")).strip(),
            required_skills=_parse_list(row.get("required_skills", "")),
            required_certs=_parse_list(row.get("required_certs", "")),
            start_date=_parse_date(row.get("start_date", "")),
            end_date=_parse_date(row.get("end_date", "")),
            priority=str(row.get("priority", "Standard")).strip(),
            assigned_pilot=assigned_pilot,
            assigned_drone=assigned_drone,
        )

    def to_dict(self) -> dict:
        return {
            "project_id": self.project_id,
            "client": self.client,
            "location": self.location,
            "required_skills": ", ".join(self.required_skills),
            "required_certs": ", ".join(self.required_certs),
            "start_date": self.start_date.isoformat() if self.start_date else "",
            "end_date": self.end_date.isoformat() if self.end_date else "",
            "priority": self.priority,
            "assigned_pilot": self.assigned_pilot or "–",
            "assigned_drone": self.assigned_drone or "–",
        }

    @property
    def priority_rank(self) -> int:
        return PRIORITY_RANK.get(self.priority, 3)

    def overlaps_with(self, other: Mission) -> bool:
        """Check if this mission's date range overlaps with another's."""
        if not all([self.start_date, self.end_date, other.start_date, other.end_date]):
            return False
        return self.start_date <= other.end_date and other.start_date <= self.end_date

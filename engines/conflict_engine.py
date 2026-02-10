"""
Conflict Engine — detects assignment conflicts across pilots, drones, and missions.

Conflict types:
  1. Double Booking — pilot or drone assigned to overlapping missions
  2. Skill Mismatch — pilot lacks required skills or certifications
  3. Maintenance Conflict — drone maintenance due before mission ends
  4. Location Mismatch — pilot/drone location ≠ mission location
"""
from __future__ import annotations
import logging
from dataclasses import dataclass
from datetime import date
from typing import List

from models.pilot import Pilot
from models.drone import Drone
from models.mission import Mission

logger = logging.getLogger(__name__)


@dataclass
class Conflict:
    """Represents a single detected conflict."""
    conflict_type: str    # "Double Booking" | "Skill Mismatch" | "Maintenance" | "Location Mismatch"
    severity: str         # "Critical" | "Warning" | "Info"
    entity_id: str        # pilot_id or drone_id
    entity_name: str
    mission_id: str
    description: str

    def __str__(self) -> str:
        icon = {"Critical": "🔴", "Warning": "🟡", "Info": "🔵"}.get(self.severity, "⚪")
        return f"{icon} **{self.conflict_type}** [{self.severity}] — {self.description}"


def detect_all_conflicts(
    pilots: List[Pilot],
    drones: List[Drone],
    missions: List[Mission],
) -> List[Conflict]:
    """Run all conflict checks and return a combined list."""
    conflicts: List[Conflict] = []
    conflicts.extend(detect_double_bookings(pilots, missions))
    conflicts.extend(detect_drone_double_bookings(drones, missions))
    conflicts.extend(detect_skill_mismatches(pilots, missions))
    conflicts.extend(detect_maintenance_conflicts(drones, missions))
    conflicts.extend(detect_location_mismatches(pilots, drones, missions))
    return conflicts


# ---- 1. Double Booking (Pilots) ----

def detect_double_bookings(
    pilots: List[Pilot], missions: List[Mission]
) -> List[Conflict]:
    """Detect pilots assigned to overlapping missions."""
    conflicts = []
    pilot_map = {p.pilot_id: p for p in pilots}

    # Group missions by assigned pilot
    pilot_missions: dict[str, List[Mission]] = {}
    for m in missions:
        if m.assigned_pilot and m.assigned_pilot in pilot_map:
            pilot_missions.setdefault(m.assigned_pilot, []).append(m)

    for pid, m_list in pilot_missions.items():
        for i in range(len(m_list)):
            for j in range(i + 1, len(m_list)):
                if m_list[i].overlaps_with(m_list[j]):
                    p = pilot_map[pid]
                    conflicts.append(Conflict(
                        conflict_type="Double Booking",
                        severity="Critical",
                        entity_id=pid,
                        entity_name=p.name,
                        mission_id=f"{m_list[i].project_id} & {m_list[j].project_id}",
                        description=(
                            f"Pilot {p.name} ({pid}) is assigned to overlapping missions "
                            f"{m_list[i].project_id} ({m_list[i].start_date}–{m_list[i].end_date}) "
                            f"and {m_list[j].project_id} ({m_list[j].start_date}–{m_list[j].end_date})."
                        ),
                    ))
    return conflicts


# ---- 1b. Double Booking (Drones) ----

def detect_drone_double_bookings(
    drones: List[Drone], missions: List[Mission]
) -> List[Conflict]:
    """Detect drones assigned to overlapping missions."""
    conflicts = []
    drone_map = {d.drone_id: d for d in drones}

    drone_missions: dict[str, List[Mission]] = {}
    for m in missions:
        if m.assigned_drone and m.assigned_drone in drone_map:
            drone_missions.setdefault(m.assigned_drone, []).append(m)

    for did, m_list in drone_missions.items():
        for i in range(len(m_list)):
            for j in range(i + 1, len(m_list)):
                if m_list[i].overlaps_with(m_list[j]):
                    d = drone_map[did]
                    conflicts.append(Conflict(
                        conflict_type="Double Booking",
                        severity="Critical",
                        entity_id=did,
                        entity_name=d.model,
                        mission_id=f"{m_list[i].project_id} & {m_list[j].project_id}",
                        description=(
                            f"Drone {d.model} ({did}) assigned to overlapping missions "
                            f"{m_list[i].project_id} and {m_list[j].project_id}."
                        ),
                    ))
    return conflicts


# ---- 2. Skill Mismatch ----

def detect_skill_mismatches(
    pilots: List[Pilot], missions: List[Mission]
) -> List[Conflict]:
    """Detect pilots assigned to missions they lack skills/certs for."""
    conflicts = []
    pilot_map = {p.pilot_id: p for p in pilots}

    for m in missions:
        if not m.assigned_pilot or m.assigned_pilot not in pilot_map:
            continue
        p = pilot_map[m.assigned_pilot]
        p_skills = {s.lower().strip() for s in p.skills}
        p_certs = {c.lower().strip() for c in p.certifications}

        missing_skills = [s for s in m.required_skills if s.lower().strip() not in p_skills]
        missing_certs = [c for c in m.required_certs if c.lower().strip() not in p_certs]

        if missing_skills:
            conflicts.append(Conflict(
                conflict_type="Skill Mismatch",
                severity="Critical",
                entity_id=p.pilot_id,
                entity_name=p.name,
                mission_id=m.project_id,
                description=f"Pilot {p.name} is missing required skills: {', '.join(missing_skills)} for {m.project_id}.",
            ))
        if missing_certs:
            conflicts.append(Conflict(
                conflict_type="Skill Mismatch",
                severity="Critical",
                entity_id=p.pilot_id,
                entity_name=p.name,
                mission_id=m.project_id,
                description=f"Pilot {p.name} is missing required certifications: {', '.join(missing_certs)} for {m.project_id}.",
            ))
    return conflicts


# ---- 3. Maintenance Conflict ----

def detect_maintenance_conflicts(
    drones: List[Drone], missions: List[Mission]
) -> List[Conflict]:
    """Detect drones assigned to missions that extend past their maintenance date."""
    conflicts = []
    drone_map = {d.drone_id: d for d in drones}

    for m in missions:
        if not m.assigned_drone or m.assigned_drone not in drone_map:
            continue
        d = drone_map[m.assigned_drone]

        # Drone currently in maintenance
        if d.status == "Maintenance":
            conflicts.append(Conflict(
                conflict_type="Maintenance",
                severity="Critical",
                entity_id=d.drone_id,
                entity_name=d.model,
                mission_id=m.project_id,
                description=f"Drone {d.model} ({d.drone_id}) is currently in Maintenance and cannot be assigned to {m.project_id}.",
            ))
            continue

        # Maintenance due before mission ends
        if d.maintenance_due and m.end_date and d.maintenance_due <= m.end_date:
            conflicts.append(Conflict(
                conflict_type="Maintenance",
                severity="Warning",
                entity_id=d.drone_id,
                entity_name=d.model,
                mission_id=m.project_id,
                description=(
                    f"Drone {d.model} ({d.drone_id}) has maintenance due on {d.maintenance_due} "
                    f"but mission {m.project_id} ends on {m.end_date}."
                ),
            ))
    return conflicts


# ---- 4. Location Mismatch ----

def detect_location_mismatches(
    pilots: List[Pilot],
    drones: List[Drone],
    missions: List[Mission],
) -> List[Conflict]:
    """Detect mismatch between pilot/drone location and mission location."""
    conflicts = []
    pilot_map = {p.pilot_id: p for p in pilots}
    drone_map = {d.drone_id: d for d in drones}

    for m in missions:
        if not m.location:
            continue

        # Pilot location check
        if m.assigned_pilot and m.assigned_pilot in pilot_map:
            p = pilot_map[m.assigned_pilot]
            if p.location and p.location.lower().strip() != m.location.lower().strip():
                conflicts.append(Conflict(
                    conflict_type="Location Mismatch",
                    severity="Warning",
                    entity_id=p.pilot_id,
                    entity_name=p.name,
                    mission_id=m.project_id,
                    description=(
                        f"Pilot {p.name} is in {p.location} but mission {m.project_id} is in {m.location}."
                    ),
                ))

        # Drone location check
        if m.assigned_drone and m.assigned_drone in drone_map:
            d = drone_map[m.assigned_drone]
            if d.location and d.location.lower().strip() != m.location.lower().strip():
                conflicts.append(Conflict(
                    conflict_type="Location Mismatch",
                    severity="Warning",
                    entity_id=d.drone_id,
                    entity_name=d.model,
                    mission_id=m.project_id,
                    description=(
                        f"Drone {d.model} ({d.drone_id}) is in {d.location} but mission {m.project_id} is in {m.location}."
                    ),
                ))
    return conflicts

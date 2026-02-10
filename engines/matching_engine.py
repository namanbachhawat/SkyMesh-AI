"""
Matching Engine — scores and ranks pilots and drones for a given mission.
Uses weighted scoring: skill=40%, cert=30%, location=15%, availability=15%.
Returns top 3 candidates for each category.
"""
from __future__ import annotations
import logging
from datetime import date
from typing import Dict, List, Tuple

from models.pilot import Pilot
from models.drone import Drone
from models.mission import Mission
from utils.scoring import set_overlap_ratio, location_match_score, weighted_score

logger = logging.getLogger(__name__)


def score_pilot_for_mission(pilot: Pilot, mission: Mission) -> Tuple[float, Dict[str, float]]:
    """
    Score a pilot against a mission. Returns (total_score, breakdown_dict).
    """
    skill_s = set_overlap_ratio(set(mission.required_skills), set(pilot.skills))
    cert_s = set_overlap_ratio(set(mission.required_certs), set(pilot.certifications))
    loc_s = location_match_score(pilot.location, mission.location)

    # Availability: pilot's available_from <= mission start_date
    if pilot.available_from and mission.start_date:
        avail_s = 1.0 if pilot.available_from <= mission.start_date else 0.0
    else:
        avail_s = 0.5  # Unknown availability — give partial credit

    total = weighted_score(skill_s, cert_s, loc_s, avail_s)
    breakdown = {
        "skill_match": round(skill_s, 2),
        "cert_match": round(cert_s, 2),
        "location_match": round(loc_s, 2),
        "availability": round(avail_s, 2),
        "total_score": round(total, 2),
    }
    return total, breakdown


def score_drone_for_mission(drone: Drone, mission: Mission) -> Tuple[float, Dict[str, float]]:
    """
    Score a drone against a mission.
    Capability match = 50%, Location = 30%, Maintenance safety = 20%.
    """
    cap_s = set_overlap_ratio(set(mission.required_skills), set(drone.capabilities))
    loc_s = location_match_score(drone.location, mission.location)

    # Maintenance safety: drone's maintenance_due > mission end_date
    if drone.maintenance_due and mission.end_date:
        maint_s = 1.0 if drone.maintenance_due > mission.end_date else 0.0
    else:
        maint_s = 0.5

    # Custom weights for drones
    total = cap_s * 0.50 + loc_s * 0.30 + maint_s * 0.20
    breakdown = {
        "capability_match": round(cap_s, 2),
        "location_match": round(loc_s, 2),
        "maintenance_safe": round(maint_s, 2),
        "total_score": round(total, 2),
    }
    return total, breakdown


def find_best_pilots(
    pilots: List[Pilot], mission: Mission, top_n: int = 3
) -> List[Tuple[Pilot, float, Dict[str, float]]]:
    """
    Return top N available pilots ranked by score for a mission.
    Only considers pilots with status 'Available'.
    """
    candidates = []
    for pilot in pilots:
        if not pilot.is_available:
            continue
        score, breakdown = score_pilot_for_mission(pilot, mission)
        candidates.append((pilot, score, breakdown))

    candidates.sort(key=lambda x: x[1], reverse=True)
    return candidates[:top_n]


def find_best_drones(
    drones: List[Drone], mission: Mission, top_n: int = 3
) -> List[Tuple[Drone, float, Dict[str, float]]]:
    """
    Return top N available drones ranked by score for a mission.
    Only considers drones with status 'Available'.
    """
    candidates = []
    for drone in drones:
        if not drone.is_available:
            continue
        score, breakdown = score_drone_for_mission(drone, mission)
        candidates.append((drone, score, breakdown))

    candidates.sort(key=lambda x: x[1], reverse=True)
    return candidates[:top_n]

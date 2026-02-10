"""
Scoring utilities — shared weighted scoring functions used by matching & reassignment engines.
"""
from typing import List, Set


def set_overlap_ratio(required: Set[str], available: Set[str]) -> float:
    """
    Calculate the fraction of required items that are present in available.
    Returns 1.0 if all required items are met, 0.0 if none.
    Case-insensitive comparison.
    """
    if not required:
        return 1.0  # No requirements = automatically satisfied
    req_lower = {r.lower().strip() for r in required}
    avail_lower = {a.lower().strip() for a in available}
    matched = req_lower & avail_lower
    return len(matched) / len(req_lower)


def location_match_score(location_a: str, location_b: str) -> float:
    """Binary location match — 1.0 if same city, 0.0 otherwise."""
    if not location_a or not location_b:
        return 0.0
    return 1.0 if location_a.strip().lower() == location_b.strip().lower() else 0.0


def weighted_score(
    skill_score: float,
    cert_score: float,
    location_score: float,
    availability_score: float,
    weights: dict = None,
) -> float:
    """
    Compute a weighted composite score.
    Default weights: skill=40%, cert=30%, location=15%, availability=15%
    """
    if weights is None:
        weights = {
            "skill": 0.40,
            "cert": 0.30,
            "location": 0.15,
            "availability": 0.15,
        }
    return (
        skill_score * weights["skill"]
        + cert_score * weights["cert"]
        + location_score * weights["location"]
        + availability_score * weights["availability"]
    )

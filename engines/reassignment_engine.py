"""
Reassignment Engine — handles urgent mission reassignment.

Logic:
  1. Find available pilots/drones that match the urgent mission.
  2. If none available → find pilots on LOW/STANDARD priority missions that can be swapped.
  3. Score each swap plan with a risk score (0-100, lower = safer).
  4. Return ranked suggestions with justification.
"""
from __future__ import annotations
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from models.pilot import Pilot
from models.drone import Drone
from models.mission import Mission
from engines.matching_engine import (
    find_best_pilots,
    find_best_drones,
    score_pilot_for_mission,
    score_drone_for_mission,
)

logger = logging.getLogger(__name__)


@dataclass
class SwapPlan:
    """A proposed reassignment plan for an urgent mission."""
    urgent_mission_id: str
    # New assignments
    suggested_pilot: Optional[Pilot] = None
    pilot_score: float = 0.0
    pilot_breakdown: Dict[str, float] = field(default_factory=dict)
    suggested_drone: Optional[Drone] = None
    drone_score: float = 0.0
    drone_breakdown: Dict[str, float] = field(default_factory=dict)
    # If swapping from another mission
    displaced_from_mission: Optional[str] = None
    displaced_mission_priority: Optional[str] = None
    # Risk & reasoning
    risk_score: int = 0  # 0 (safe) to 100 (dangerous)
    justification: str = ""
    warnings: List[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [f"### Swap Plan for {self.urgent_mission_id}"]
        risk_icon = "🟢" if self.risk_score < 30 else ("🟡" if self.risk_score < 60 else "🔴")
        lines.append(f"**Risk Score:** {risk_icon} {self.risk_score}/100")
        if self.suggested_pilot:
            lines.append(
                f"**Pilot:** {self.suggested_pilot.name} ({self.suggested_pilot.pilot_id}) "
                f"— Score: {self.pilot_score:.0%}"
            )
        if self.suggested_drone:
            lines.append(
                f"**Drone:** {self.suggested_drone.model} ({self.suggested_drone.drone_id}) "
                f"— Score: {self.drone_score:.0%}"
            )
        if self.displaced_from_mission:
            lines.append(
                f"⚠️ Pilot displaced from **{self.displaced_from_mission}** "
                f"(Priority: {self.displaced_mission_priority})"
            )
        lines.append(f"**Justification:** {self.justification}")
        for w in self.warnings:
            lines.append(f"⚠️ {w}")
        return "\n".join(lines)


def _compute_risk_score(
    pilot_score: float,
    drone_score: float,
    is_swap: bool,
    displaced_priority: Optional[str] = None,
) -> int:
    """
    Risk score 0-100:
      - High pilot/drone match = lower risk
      - Swapping from existing mission = higher risk
      - Displacing a high-priority mission = much higher risk
    """
    base_risk = int((1.0 - (pilot_score + drone_score) / 2) * 50)

    if is_swap:
        base_risk += 20
        if displaced_priority == "High":
            base_risk += 20
        elif displaced_priority == "Urgent":
            base_risk += 30  # Shouldn't happen, but safety
        elif displaced_priority in ("Standard", "Low"):
            base_risk += 5

    return max(0, min(100, base_risk))


def suggest_reassignment(
    urgent_mission: Mission,
    pilots: List[Pilot],
    drones: List[Drone],
    missions: List[Mission],
) -> List[SwapPlan]:
    """
    Generate reassignment plans for an urgent mission, ranked by risk score.
    """
    plans: List[SwapPlan] = []

    # ── Phase 1: Try available pilots & drones ──
    best_pilots = find_best_pilots(pilots, urgent_mission, top_n=3)
    best_drones = find_best_drones(drones, urgent_mission, top_n=3)

    if best_pilots and best_drones:
        for pilot, p_score, p_bd in best_pilots[:2]:
            drone, d_score, d_bd = best_drones[0]
            risk = _compute_risk_score(p_score, d_score, is_swap=False)
            plans.append(SwapPlan(
                urgent_mission_id=urgent_mission.project_id,
                suggested_pilot=pilot,
                pilot_score=p_score,
                pilot_breakdown=p_bd,
                suggested_drone=drone,
                drone_score=d_score,
                drone_breakdown=d_bd,
                risk_score=risk,
                justification=f"Available pilot {pilot.name} and drone {drone.model} match the mission requirements.",
            ))

    # ── Phase 2: If no available options, try swapping from low-priority missions ──
    if not best_pilots:
        logger.info("No available pilots — looking for swap candidates.")
        # Sort missions by priority (lowest priority first = best swap candidates)
        reassignable = sorted(
            [m for m in missions if m.assigned_pilot and m.priority in ("Low", "Standard")],
            key=lambda m: m.priority_rank,
            reverse=True,  # Low priority first
        )

        pilot_map = {p.pilot_id: p for p in pilots}
        for m in reassignable:
            if m.assigned_pilot not in pilot_map:
                continue
            candidate = pilot_map[m.assigned_pilot]
            p_score, p_bd = score_pilot_for_mission(candidate, urgent_mission)
            if p_score < 0.3:
                continue  # Too poor a match

            drone_for_plan = best_drones[0] if best_drones else None
            d_score = drone_for_plan[1] if drone_for_plan else 0.0
            d_bd = drone_for_plan[2] if drone_for_plan else {}
            drone_obj = drone_for_plan[0] if drone_for_plan else None

            risk = _compute_risk_score(
                p_score, d_score, is_swap=True, displaced_priority=m.priority
            )
            warnings = [
                f"Mission {m.project_id} ({m.client}) will be left without a pilot.",
            ]
            plans.append(SwapPlan(
                urgent_mission_id=urgent_mission.project_id,
                suggested_pilot=candidate,
                pilot_score=p_score,
                pilot_breakdown=p_bd,
                suggested_drone=drone_obj,
                drone_score=d_score,
                drone_breakdown=d_bd,
                displaced_from_mission=m.project_id,
                displaced_mission_priority=m.priority,
                risk_score=risk,
                justification=(
                    f"Swap pilot {candidate.name} from {m.project_id} (Priority: {m.priority}) "
                    f"to urgent mission {urgent_mission.project_id}."
                ),
                warnings=warnings,
            ))

    # If still no drones and we have pilot plans, add a warning
    if not best_drones:
        for plan in plans:
            plan.warnings.append("No available drones found. Manual drone assignment needed.")
            plan.risk_score = min(100, plan.risk_score + 15)

    # Sort by risk score ascending (safest first)
    plans.sort(key=lambda p: p.risk_score)
    return plans


def execute_reassignment(
    plan: SwapPlan,
    pilots: List[Pilot],
    drones: List[Drone],
    missions: List[Mission],
) -> str:
    """
    Execute a chosen swap plan — update assignments in data.
    Returns a summary string of changes made.
    """
    changes: List[str] = []

    # Find the urgent mission
    urgent = next((m for m in missions if m.project_id == plan.urgent_mission_id), None)
    if not urgent:
        return f"❌ Mission {plan.urgent_mission_id} not found."

    # Assign pilot
    if plan.suggested_pilot:
        # Un-assign from previous mission if swap
        if plan.displaced_from_mission:
            old_mission = next(
                (m for m in missions if m.project_id == plan.displaced_from_mission), None
            )
            if old_mission:
                old_mission.assigned_pilot = ""
                changes.append(f"Removed {plan.suggested_pilot.name} from {old_mission.project_id}")

        # Update pilot
        pilot = next(p for p in pilots if p.pilot_id == plan.suggested_pilot.pilot_id)
        pilot.status = "Assigned"
        pilot.current_assignment = plan.urgent_mission_id
        urgent.assigned_pilot = pilot.pilot_id
        changes.append(f"Assigned pilot {pilot.name} ({pilot.pilot_id}) to {urgent.project_id}")

    # Assign drone
    if plan.suggested_drone:
        drone = next(d for d in drones if d.drone_id == plan.suggested_drone.drone_id)
        drone.status = "Assigned"
        drone.current_assignment = plan.urgent_mission_id
        urgent.assigned_drone = drone.drone_id
        changes.append(f"Assigned drone {drone.model} ({drone.drone_id}) to {urgent.project_id}")

    return "\n".join(changes) if changes else "No changes were made."

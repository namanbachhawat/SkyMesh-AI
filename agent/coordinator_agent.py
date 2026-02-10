"""
Coordinator Agent — rule-based intent parser + tool router.

Parses natural language queries via keyword/regex matching, routes to the
appropriate engine, and returns structured + human-readable responses.
No LLM dependency — deterministic, fast, works offline.
"""
from __future__ import annotations
import logging
import re
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

from models.pilot import Pilot
from models.drone import Drone
from models.mission import Mission
from engines.matching_engine import find_best_pilots, find_best_drones
from engines.conflict_engine import detect_all_conflicts, Conflict
from engines.reassignment_engine import suggest_reassignment, execute_reassignment, SwapPlan
from services.sheets_service import (
    load_pilots, load_drones, load_missions,
    save_pilots, save_drones, save_missions,
    append_decision_log,
)

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Data cache (refreshed per session / on demand)
# ──────────────────────────────────────────────
class DataStore:
    """In-memory data cache with reload capability."""

    def __init__(self):
        self.pilots: List[Pilot] = []
        self.drones: List[Drone] = []
        self.missions: List[Mission] = []
        self.reload()

    def reload(self):
        self.pilots = load_pilots()
        self.drones = load_drones()
        self.missions = load_missions()
        logger.info(
            f"Data loaded: {len(self.pilots)} pilots, "
            f"{len(self.drones)} drones, {len(self.missions)} missions."
        )

    def save_all(self):
        save_pilots(self.pilots)
        save_drones(self.drones)
        save_missions(self.missions)

    def find_pilot(self, identifier: str) -> Optional[Pilot]:
        """Find pilot by ID or name (case-insensitive partial match)."""
        identifier = identifier.strip().lower()
        for p in self.pilots:
            if p.pilot_id.lower() == identifier or p.name.lower() == identifier:
                return p
        # Partial name match
        for p in self.pilots:
            if identifier in p.name.lower():
                return p
        return None

    def find_drone(self, identifier: str) -> Optional[Drone]:
        identifier = identifier.strip().lower()
        for d in self.drones:
            if d.drone_id.lower() == identifier or d.model.lower() == identifier:
                return d
        for d in self.drones:
            if identifier in d.model.lower():
                return d
        return None

    def find_mission(self, identifier: str) -> Optional[Mission]:
        identifier = identifier.strip().lower()
        for m in self.missions:
            if m.project_id.lower() == identifier:
                return m
        # Try partial match on client or id
        for m in self.missions:
            if identifier in m.project_id.lower() or identifier in m.client.lower():
                return m
        return None


# ──────────────────────────────────────────────
# Intent detection
# ──────────────────────────────────────────────
class Intent:
    QUERY_PILOTS = "query_pilots"
    QUERY_DRONES = "query_drones"
    QUERY_MISSIONS = "query_missions"
    ASSIGN = "assign"
    CONFLICTS = "conflicts"
    URGENT_REASSIGN = "urgent_reassign"
    UPDATE_STATUS = "update_status"
    CANCEL_MISSION = "cancel_mission"
    UNASSIGN = "unassign"
    RESOLVE_CONFLICT = "resolve_conflict"
    HELP = "help"
    UNKNOWN = "unknown"


def detect_intent(message: str) -> Tuple[str, Dict]:
    """
    Parse the user message to determine intent and extract parameters.
    Returns (intent_name, extracted_params).
    """
    msg = message.lower().strip()
    params: Dict = {"raw": message}

    # ── Cancel / unassign mission ──
    if any(kw in msg for kw in ["cancel mission", "cancel assignment", "unassign mission", "remove assignment", "clear assignment", "abort mission"]):
        mid = _extract_id(msg, prefix=["prj", "m", "mission"])
        params["mission_id"] = mid
        return Intent.CANCEL_MISSION, params

    # ── Unassign pilot / drone ──
    if any(kw in msg for kw in ["unassign", "free up", "release"]):
        params["pilot_name"] = _extract_name(msg)
        pid = _extract_id(msg, prefix=["p"])
        did = _extract_id(msg, prefix=["d"])
        params["pilot_id"] = pid
        params["drone_id"] = did
        return Intent.UNASSIGN, params

    # ── Resolve conflict ──
    if any(kw in msg for kw in ["resolve", "fix conflict", "handle conflict"]):
        mid = _extract_id(msg, prefix=["prj", "m", "mission"])
        params["mission_id"] = mid
        return Intent.RESOLVE_CONFLICT, params

    # ── Urgent reassignment ──
    if any(kw in msg for kw in ["urgent", "reassign", "swap", "emergency"]):
        mid = _extract_id(msg, prefix=["prj", "m", "mission"])
        params["mission_id"] = mid
        return Intent.URGENT_REASSIGN, params

    # ── Conflict check ──
    if any(kw in msg for kw in ["conflict", "overlap", "double book", "mismatch", "issue"]):
        return Intent.CONFLICTS, params

    # ── Assignment ──
    if any(kw in msg for kw in ["assign", "match", "best pilot", "best drone", "recommend"]):
        mid = _extract_id(msg, prefix=["prj", "m", "mission"])
        params["mission_id"] = mid
        return Intent.ASSIGN, params

    # ── Update / mark status ──
    if any(kw in msg for kw in ["mark", "update", "set", "change status"]):
        params["pilot_name"] = _extract_name(msg)
        for status in ["on leave", "available", "assigned", "inactive"]:
            if status in msg:
                params["new_status"] = status.title()
                break
        return Intent.UPDATE_STATUS, params

    # ── Query pilots ──
    if any(kw in msg for kw in ["pilot", "roster"]):
        params["filters"] = _extract_query_filters(msg)
        return Intent.QUERY_PILOTS, params

    # ── Query drones ──
    if any(kw in msg for kw in ["drone", "fleet", "uav"]):
        params["filters"] = _extract_query_filters(msg)
        return Intent.QUERY_DRONES, params

    # ── Query missions ──
    if any(kw in msg for kw in ["mission", "project", "prj"]):
        params["filters"] = _extract_query_filters(msg)
        return Intent.QUERY_MISSIONS, params

    # ── Help ──
    if any(kw in msg for kw in ["help", "what can you", "how to", "commands"]):
        return Intent.HELP, params

    return Intent.UNKNOWN, params


def _extract_id(msg: str, prefix: list) -> Optional[str]:
    """Extract an ID like PRJ001, M102 from text."""
    for p in prefix:
        match = re.search(rf'\b({p}\d+)\b', msg, re.IGNORECASE)
        if match:
            return match.group(1).upper()
    return None


def _extract_name(msg: str) -> Optional[str]:
    """Try to extract a proper name from the message."""
    # Look for "pilot <Name>" or "mark <Name>"
    patterns = [
        r'pilot\s+(\w+)',
        r'mark\s+(\w+)',
        r'update\s+(\w+)',
    ]
    for pat in patterns:
        match = re.search(pat, msg, re.IGNORECASE)
        if match:
            name = match.group(1)
            # Filter out common non-name words
            if name.lower() not in ("as", "to", "the", "status", "a", "an", "is"):
                return name
    return None


def _extract_query_filters(msg: str) -> Dict:
    """Extract filter parameters from a query message."""
    filters = {}
    # Location
    cities = ["bangalore", "mumbai", "delhi", "chennai", "hyderabad", "pune", "kolkata"]
    for city in cities:
        if city in msg.lower():
            filters["location"] = city.title()
            break

    # Skills / capabilities
    skills = ["mapping", "survey", "inspection", "thermal", "lidar", "rgb", "photogrammetry"]
    found_skills = [s.title() for s in skills if s in msg.lower()]
    if found_skills:
        filters["skills"] = found_skills

    # Certifications
    certs = ["dgca", "night ops", "beyond vlos", "bvlos"]
    found_certs = [c.upper() if c == "dgca" else c.title() for c in certs if c in msg.lower()]
    if found_certs:
        filters["certifications"] = found_certs

    # Status
    for status in ["available", "assigned", "on leave", "maintenance"]:
        if status in msg.lower():
            filters["status"] = status.title()
            break

    return filters


# ──────────────────────────────────────────────
# Response generation
# ──────────────────────────────────────────────

def handle_message(message: str, store: DataStore) -> str:
    """
    Main entry point: parse intent, route to handler, return formatted response.
    """
    intent, params = detect_intent(message)
    logger.info(f"Intent: {intent} | Params: {params}")

    handlers = {
        Intent.QUERY_PILOTS: _handle_query_pilots,
        Intent.QUERY_DRONES: _handle_query_drones,
        Intent.QUERY_MISSIONS: _handle_query_missions,
        Intent.ASSIGN: _handle_assign,
        Intent.CONFLICTS: _handle_conflicts,
        Intent.URGENT_REASSIGN: _handle_urgent_reassign,
        Intent.UPDATE_STATUS: _handle_update_status,
        Intent.CANCEL_MISSION: _handle_cancel_mission,
        Intent.UNASSIGN: _handle_unassign,
        Intent.RESOLVE_CONFLICT: _handle_resolve_conflict,
        Intent.HELP: _handle_help,
    }

    handler = handlers.get(intent, _handle_unknown)
    try:
        return handler(params, store)
    except Exception as e:
        logger.exception(f"Error handling intent {intent}")
        return f"❌ An error occurred: {str(e)}"


def _handle_query_pilots(params: Dict, store: DataStore) -> str:
    """Filter and display pilot roster."""
    filters = params.get("filters", {})
    results = store.pilots

    if "location" in filters:
        results = [p for p in results if p.location.lower() == filters["location"].lower()]
    if "status" in filters:
        results = [p for p in results if p.status.lower() == filters["status"].lower()]
    if "skills" in filters:
        req = {s.lower() for s in filters["skills"]}
        results = [p for p in results if req & {s.lower() for s in p.skills}]
    if "certifications" in filters:
        req = {c.lower() for c in filters["certifications"]}
        results = [p for p in results if req & {c.lower() for c in p.certifications}]

    if not results:
        return "No pilots found matching your criteria."

    lines = [f"### 🧑‍✈️ Pilots Found ({len(results)})"]
    for p in results:
        status_icon = {"Available": "🟢", "Assigned": "🔵", "On Leave": "🟠"}.get(p.status, "⚪")
        lines.append(
            f"- {status_icon} **{p.name}** ({p.pilot_id}) | "
            f"Skills: {', '.join(p.skills)} | Certs: {', '.join(p.certifications)} | "
            f"📍 {p.location} | Status: {p.status}"
        )
    return "\n".join(lines)


def _handle_query_drones(params: Dict, store: DataStore) -> str:
    """Filter and display drone fleet."""
    filters = params.get("filters", {})
    results = store.drones

    if "location" in filters:
        results = [d for d in results if d.location.lower() == filters["location"].lower()]
    if "status" in filters:
        results = [d for d in results if d.status.lower() == filters["status"].lower()]
    if "skills" in filters:  # capabilities
        req = {s.lower() for s in filters["skills"]}
        results = [d for d in results if req & {c.lower() for c in d.capabilities}]

    if not results:
        return "No drones found matching your criteria."

    lines = [f"### 🚁 Drones Found ({len(results)})"]
    for d in results:
        status_icon = {"Available": "🟢", "Assigned": "🔵", "Maintenance": "🔴"}.get(d.status, "⚪")
        maint = f"🔧 Due: {d.maintenance_due}" if d.maintenance_due else ""
        lines.append(
            f"- {status_icon} **{d.model}** ({d.drone_id}) | "
            f"Capabilities: {', '.join(d.capabilities)} | "
            f"📍 {d.location} | Status: {d.status} {maint}"
        )
    return "\n".join(lines)


def _handle_query_missions(params: Dict, store: DataStore) -> str:
    """Display mission list."""
    filters = params.get("filters", {})
    results = store.missions

    if "location" in filters:
        results = [m for m in results if m.location.lower() == filters["location"].lower()]

    if not results:
        return "No missions found matching your criteria."

    lines = [f"### 📋 Missions ({len(results)})"]
    for m in results:
        priority_icon = {"Urgent": "🔴", "High": "🟡", "Standard": "🔵", "Low": "⚪"}.get(
            m.priority, "⚪"
        )
        pilot_str = m.assigned_pilot or "Unassigned"
        drone_str = m.assigned_drone or "Unassigned"
        lines.append(
            f"- {priority_icon} **{m.project_id}** | Client: {m.client} | 📍 {m.location}\n"
            f"  Skills: {', '.join(m.required_skills)} | Certs: {', '.join(m.required_certs)}\n"
            f"  📅 {m.start_date} → {m.end_date} | Priority: **{m.priority}**\n"
            f"  Pilot: {pilot_str} | Drone: {drone_str}"
        )
    return "\n".join(lines)


def _handle_assign(params: Dict, store: DataStore) -> str:
    """Find best pilot + drone for a mission."""
    mid = params.get("mission_id")
    if not mid:
        return "Please specify a mission ID (e.g., PRJ001). Usage: `Assign best pilot and drone to PRJ001`"

    mission = store.find_mission(mid)
    if not mission:
        return f"❌ Mission **{mid}** not found. Available: {', '.join(m.project_id for m in store.missions)}"

    best_pilots = find_best_pilots(store.pilots, mission)
    best_drones = find_best_drones(store.drones, mission)

    lines = [f"### 🎯 Best Matches for {mission.project_id} ({mission.client})"]
    lines.append(
        f"📍 {mission.location} | Skills: {', '.join(mission.required_skills)} | "
        f"Certs: {', '.join(mission.required_certs)} | Priority: **{mission.priority}**"
    )

    lines.append("\n**Top Pilot Candidates:**")
    if best_pilots:
        for i, (pilot, score, bd) in enumerate(best_pilots, 1):
            lines.append(
                f"{i}. **{pilot.name}** ({pilot.pilot_id}) — Score: **{score:.0%}**\n"
                f"   Skill: {bd['skill_match']:.0%} | Cert: {bd['cert_match']:.0%} | "
                f"Location: {bd['location_match']:.0%} | Avail: {bd['availability']:.0%}"
            )
    else:
        lines.append("⚠️ No available pilots found.")

    lines.append("\n**Top Drone Candidates:**")
    if best_drones:
        for i, (drone, score, bd) in enumerate(best_drones, 1):
            lines.append(
                f"{i}. **{drone.model}** ({drone.drone_id}) — Score: **{score:.0%}**\n"
                f"   Capability: {bd['capability_match']:.0%} | "
                f"Location: {bd['location_match']:.0%} | Maint: {bd['maintenance_safe']:.0%}"
            )
    else:
        lines.append("⚠️ No available drones found.")

    lines.append(
        "\n💡 *Type* `confirm assign <pilot_id> <drone_id> to <mission_id>` *to execute the assignment.*"
    )
    return "\n".join(lines)


def _handle_conflicts(params: Dict, store: DataStore) -> str:
    """Run all conflict checks."""
    conflicts = detect_all_conflicts(store.pilots, store.drones, store.missions)
    if not conflicts:
        return "### ✅ No Conflicts Detected\nAll current assignments look clean!"

    lines = [f"### ⚠️ Conflicts Detected ({len(conflicts)})"]
    for c in conflicts:
        lines.append(str(c))

    lines.append("\n---")
    lines.append("**💡 To resolve conflicts, try:**")
    lines.append("- `Cancel mission PRJ001` — unassign pilot & drone from mission")
    lines.append("- `Unassign P001` — release a pilot back to Available")
    lines.append("- `Resolve conflict for PRJ001` — get AI-suggested fix")
    lines.append("- `Mark Arjun as Available` — change pilot status")
    return "\n".join(lines)


def _handle_urgent_reassign(params: Dict, store: DataStore) -> str:
    """Generate urgent reassignment plans."""
    mid = params.get("mission_id")
    if not mid:
        # Find any Urgent priority mission without assignment
        urgent_missions = [
            m for m in store.missions
            if m.priority == "Urgent" and not m.assigned_pilot
        ]
        if urgent_missions:
            mission = urgent_missions[0]
        else:
            return (
                "Please specify the urgent mission ID (e.g., PRJ002). "
                "Usage: `Urgent reassignment for PRJ002`"
            )
    else:
        mission = store.find_mission(mid)
        if not mission:
            return f"❌ Mission **{mid}** not found."

    plans = suggest_reassignment(mission, store.pilots, store.drones, store.missions)
    if not plans:
        return (
            f"### ❌ No Reassignment Options for {mission.project_id}\n"
            "No available or swappable pilots/drones could be found."
        )

    lines = [f"### 🚨 Urgent Reassignment Plans for {mission.project_id}"]
    lines.append(
        f"Mission: {mission.client} @ {mission.location} | "
        f"Skills: {', '.join(mission.required_skills)} | "
        f"📅 {mission.start_date} → {mission.end_date}\n"
    )
    for i, plan in enumerate(plans, 1):
        lines.append(f"---\n**Option {i}:**")
        lines.append(plan.summary())

    lines.append(
        "\n💡 *Type* `confirm reassignment option <number> for <mission_id>` *to execute.*"
    )

    # Store plans in the DataStore for later confirmation
    store._last_reassignment_plans = plans
    store._last_reassignment_mission = mission

    return "\n".join(lines)


def _handle_update_status(params: Dict, store: DataStore) -> str:
    """Update pilot or drone status."""
    name = params.get("pilot_name")
    new_status = params.get("new_status")

    if not name:
        return "Please specify who to update. Example: `Mark Arjun as On Leave`"
    if not new_status:
        return f"Please specify the new status. Example: `Mark {name} as Available`"

    pilot = store.find_pilot(name)
    if pilot:
        old_status = pilot.status
        pilot.status = new_status
        if new_status in ("On Leave", "Available"):
            pilot.current_assignment = ""
        store.save_all()
        entry = f"Pilot {pilot.name} ({pilot.pilot_id}) status changed: {old_status} → {new_status}"
        append_decision_log(entry)
        return (
            f"### ✅ Status Updated\n"
            f"**{pilot.name}** ({pilot.pilot_id}): {old_status} → **{new_status}**\n"
            f"📝 Decision logged."
        )

    # Try drone
    drone = store.find_drone(name)
    if drone:
        old_status = drone.status
        drone.status = new_status
        store.save_all()
        return (
            f"### ✅ Drone Status Updated\n"
            f"**{drone.model}** ({drone.drone_id}): {old_status} → **{new_status}**"
        )

    return f"❌ Could not find pilot or drone matching '{name}'."


def _handle_help(params: Dict, store: DataStore) -> str:
    return """### 🤖 Drone Operations Coordinator — Help

**Available Commands:**

| Category | Example Query |
|---|---|
| 🧑‍✈️ **Pilots** | `Show available pilots in Bangalore` |
| | `Show pilots with thermal certification` |
| 🚁 **Drones** | `Show available drones in Mumbai` |
| | `Show drones with LiDAR capability` |
| 📋 **Missions** | `Show all missions` |
| 🎯 **Assign** | `Assign best pilot and drone to PRJ001` |
| ⚠️ **Conflicts** | `Check for conflicts` |
| 🔧 **Resolve** | `Resolve conflict for PRJ001` |
| ❌ **Cancel** | `Cancel mission PRJ001` |
| 🔓 **Unassign** | `Unassign P001` or `Free up D002` |
| 🚨 **Urgent** | `Urgent reassignment for PRJ002` |
| ✏️ **Update** | `Mark Arjun as On Leave` |
| 🔄 **Refresh** | `Reload data` |
"""


def _handle_unknown(params: Dict, store: DataStore) -> str:
    return (
        "I'm not sure what you're asking. Try one of these:\n"
        "- `Show available pilots`\n"
        "- `Assign best pilot and drone to PRJ001`\n"
        "- `Check for conflicts`\n"
        "- `Cancel mission PRJ001`\n"
        "- `Resolve conflict for PRJ001`\n"
        "- `Urgent reassignment for PRJ002`\n"
        "- `Mark Arjun as On Leave`\n"
        "- `Help`"
    )


def _handle_cancel_mission(params: Dict, store: DataStore) -> str:
    """Cancel / clear assignment for a mission — unassigns pilot and drone."""
    mid = params.get("mission_id")
    if not mid:
        return "Please specify the mission to cancel. Example: `Cancel mission PRJ001`"

    mission = store.find_mission(mid)
    if not mission:
        return f"❌ Mission **{mid}** not found. Available: {', '.join(m.project_id for m in store.missions)}"

    changes = []

    # Free the assigned pilot
    if mission.assigned_pilot:
        pilot = store.find_pilot(mission.assigned_pilot)
        if pilot:
            pilot.status = "Available"
            pilot.current_assignment = ""
            changes.append(f"Pilot **{pilot.name}** ({pilot.pilot_id}) → Available")
        mission.assigned_pilot = ""

    # Free the assigned drone
    if mission.assigned_drone:
        drone = store.find_drone(mission.assigned_drone)
        if drone:
            drone.status = "Available"
            drone.current_assignment = ""
            changes.append(f"Drone **{drone.model}** ({drone.drone_id}) → Available")
        mission.assigned_drone = ""

    if not changes:
        return f"ℹ️ Mission **{mid}** has no active assignments to cancel."

    store.save_all()
    entry = f"Mission {mid} cancelled / assignments cleared: {'; '.join(changes)}"
    append_decision_log(entry)

    lines = [f"### ✅ Mission {mid} Assignments Cleared"]
    for c in changes:
        lines.append(f"- {c}")
    lines.append(f"\n📝 Decision logged. Data synced.")
    return "\n".join(lines)


def _handle_unassign(params: Dict, store: DataStore) -> str:
    """Unassign / release a specific pilot or drone back to Available."""
    name = params.get("pilot_name")
    pid = params.get("pilot_id")
    did = params.get("drone_id")

    changes = []

    # Try pilot by ID first, then by name
    pilot = None
    if pid:
        pilot = store.find_pilot(pid)
    elif name:
        pilot = store.find_pilot(name)

    if pilot:
        old_assignment = pilot.current_assignment
        if pilot.status == "Assigned" or old_assignment:
            # Also clear from mission
            if old_assignment:
                mission = store.find_mission(old_assignment)
                if mission and mission.assigned_pilot == pilot.pilot_id:
                    mission.assigned_pilot = ""
            pilot.status = "Available"
            pilot.current_assignment = ""
            changes.append(f"Pilot **{pilot.name}** ({pilot.pilot_id}) released from {old_assignment or 'assignment'} → Available")
        else:
            return f"ℹ️ Pilot **{pilot.name}** is already {pilot.status} with no assignment."

    # Try drone by ID
    drone = None
    if did:
        drone = store.find_drone(did)
    elif not pilot and name:
        drone = store.find_drone(name)

    if drone:
        old_assignment = drone.current_assignment
        if drone.status == "Assigned" or old_assignment:
            if old_assignment:
                mission = store.find_mission(old_assignment)
                if mission and mission.assigned_drone == drone.drone_id:
                    mission.assigned_drone = ""
            drone.status = "Available"
            drone.current_assignment = ""
            changes.append(f"Drone **{drone.model}** ({drone.drone_id}) released from {old_assignment or 'assignment'} → Available")
        else:
            return f"ℹ️ Drone **{drone.model}** is already {drone.status} with no assignment."

    if not changes:
        identifier = pid or did or name or "unknown"
        return f"❌ Could not find pilot or drone matching '{identifier}'."

    store.save_all()
    entry = f"Unassignment: {'; '.join(changes)}"
    append_decision_log(entry)

    lines = ["### ✅ Unassignment Complete"]
    for c in changes:
        lines.append(f"- {c}")
    lines.append("\n📝 Decision logged. Data synced.")
    return "\n".join(lines)


def _handle_resolve_conflict(params: Dict, store: DataStore) -> str:
    """Analyze conflicts for a mission and suggest resolution steps."""
    mid = params.get("mission_id")

    all_conflicts = detect_all_conflicts(store.pilots, store.drones, store.missions)

    if mid:
        relevant = [c for c in all_conflicts if c.mission_id == mid]
    else:
        relevant = all_conflicts

    if not relevant:
        target = f" for **{mid}**" if mid else ""
        return f"### ✅ No conflicts found{target}\nEverything looks clean!"

    lines = [f"### 🔧 Conflict Resolution{f' for {mid}' if mid else ''}"]
    lines.append(f"Found **{len(relevant)}** conflict(s). Here are resolution steps:\n")

    for i, c in enumerate(relevant, 1):
        lines.append(f"---")
        lines.append(f"**{i}. {c.conflict_type}** ({c.severity})")
        lines.append(f"   {c.description}\n")

        # Suggest specific fix based on conflict type
        if c.conflict_type == "Double Booking":
            lines.append(f"   **Fix:** Cancel one of the overlapping assignments:")
            lines.append(f"   - `Cancel mission {c.mission_id}`")
            lines.append(f"   - `Unassign {c.entity_id}`")
        elif c.conflict_type == "Skill Mismatch":
            lines.append(f"   **Fix:** Reassign to a qualified pilot/drone:")
            lines.append(f"   - `Cancel mission {c.mission_id}` then `Assign best pilot to {c.mission_id}`")
        elif c.conflict_type == "Maintenance":
            lines.append(f"   **Fix:** Swap the drone or reschedule maintenance:")
            lines.append(f"   - `Cancel mission {c.mission_id}` then `Assign best pilot to {c.mission_id}`")
            lines.append(f"   - Or: `Mark {c.entity_id} as Maintenance`")
        elif c.conflict_type == "Location Mismatch":
            lines.append(f"   **Fix:** Reassign to local resources:")
            lines.append(f"   - `Cancel mission {c.mission_id}` then `Assign best pilot to {c.mission_id}`")
        else:
            lines.append(f"   **Fix:** `Cancel mission {c.mission_id}` and re-assign.")

    return "\n".join(lines)


def handle_confirm_assign(message: str, store: DataStore) -> Optional[str]:
    """
    Handle explicit assignment confirmation:
    'confirm assign P001 D001 to PRJ001'
    """
    msg = message.lower().strip()
    if not msg.startswith("confirm assign"):
        return None

    # Extract IDs
    ids = re.findall(r'\b([pd]\d+|prj\d+)\b', msg, re.IGNORECASE)
    if len(ids) < 3:
        return "Usage: `confirm assign <pilot_id> <drone_id> to <mission_id>`"

    pilot_id, drone_id, mission_id = ids[0].upper(), ids[1].upper(), ids[2].upper()

    pilot = store.find_pilot(pilot_id)
    drone = store.find_drone(drone_id)
    mission = store.find_mission(mission_id)

    errors = []
    if not pilot:
        errors.append(f"Pilot {pilot_id} not found")
    if not drone:
        errors.append(f"Drone {drone_id} not found")
    if not mission:
        errors.append(f"Mission {mission_id} not found")
    if errors:
        return "❌ " + ", ".join(errors)

    # Execute assignment
    pilot.status = "Assigned"
    pilot.current_assignment = mission.project_id
    drone.status = "Assigned"
    drone.current_assignment = mission.project_id
    mission.assigned_pilot = pilot.pilot_id
    mission.assigned_drone = drone.drone_id

    store.save_all()
    entry = (
        f"Assignment executed: Pilot {pilot.name} ({pilot.pilot_id}) + "
        f"Drone {drone.model} ({drone.drone_id}) → Mission {mission.project_id}"
    )
    append_decision_log(entry)

    return (
        f"### ✅ Assignment Confirmed\n"
        f"**{pilot.name}** ({pilot.pilot_id}) + **{drone.model}** ({drone.drone_id}) "
        f"→ **{mission.project_id}** ({mission.client})\n"
        f"📝 Decision logged. Data synced."
    )


def handle_confirm_reassignment(message: str, store: DataStore) -> Optional[str]:
    """
    Handle reassignment confirmation:
    'confirm reassignment option 1 for PRJ002'
    """
    msg = message.lower().strip()
    if "confirm reassignment" not in msg:
        return None

    # Extract option number
    opt_match = re.search(r'option\s+(\d+)', msg)
    if not opt_match:
        return "Please specify which option. Example: `confirm reassignment option 1 for PRJ002`"

    opt_idx = int(opt_match.group(1)) - 1
    plans = getattr(store, "_last_reassignment_plans", [])
    mission = getattr(store, "_last_reassignment_mission", None)

    if not plans or mission is None:
        return "No pending reassignment plans. Please run `urgent reassignment` first."

    if opt_idx < 0 or opt_idx >= len(plans):
        return f"Invalid option. Choose between 1 and {len(plans)}."

    plan = plans[opt_idx]
    result = execute_reassignment(plan, store.pilots, store.drones, store.missions)
    store.save_all()

    entry = (
        f"URGENT REASSIGNMENT EXECUTED for {mission.project_id}: {result} "
        f"| Risk Score: {plan.risk_score}/100"
    )
    append_decision_log(entry)

    return (
        f"### ✅ Reassignment Executed\n{result}\n\n"
        f"Risk Score: {'🟢' if plan.risk_score < 30 else '🟡' if plan.risk_score < 60 else '🔴'} "
        f"{plan.risk_score}/100\n📝 Decision logged. Data synced."
    )


def process_message(message: str, store: DataStore) -> str:
    """
    Top-level message processor — checks for confirmation commands first,
    then falls back to general intent handling.
    """
    # Check for reload
    if message.lower().strip() in ("reload", "refresh", "reload data", "refresh data"):
        store.reload()
        return "### 🔄 Data Reloaded\nPilots, drones, and missions refreshed from data source."

    # Confirmation flows
    result = handle_confirm_assign(message, store)
    if result:
        return result

    result = handle_confirm_reassignment(message, store)
    if result:
        return result

    # General intent handling
    return handle_message(message, store)

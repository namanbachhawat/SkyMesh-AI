# Decision Log — Drone Operations Coordinator Agent

## Assumptions

1. **CSV as primary data store** — Google Sheets is optional. The app must work offline with just CSV files. This removes hard dependencies on external APIs for the prototype.
2. **Hybrid Agent (Rule-based + LLM)** — Primary intents are handled deterministically (regex/keyword). Unrecognized queries fall back to **Google Gemini 1.5 Flash** for natural language understanding. This combines reliability with flexibility.
3. **Location matching is binary** — A pilot in "Bangalore" matches a "Bangalore" mission with 100%, and 0% for any other city. Travel distance or relocation costs are not modeled.
4. **Skills and certifications are exact-match** — "Mapping" matches "Mapping" but not "Advanced Mapping". Fuzzy matching can be added later.
5. **Single pilot + single drone per mission** — The prototype does not support multi-pilot or multi-drone missions.
6. **Maintenance date is a hard cutoff** — If `maintenance_due <= mission.end_date`, it's flagged as a conflict. Partial maintenance windows are not modeled.

## Key Tradeoffs

| Decision | Chose | Alternative | Reason |
|---|---|---|---|
| Agent type | Rule-based keyword matching | LangChain + OpenAI | Zero API cost, deterministic, works offline. Can upgrade later. |
| Data layer | CSV files + optional Sheets | SQLite / PostgreSQL | Simpler deployment, matches Google Sheets mirroring requirement. |
| UI framework | Streamlit | Flask + React | One-file deployment, built-in chat and tables, Streamlit Cloud hosting. |
| Scoring model | Weighted linear composite | ML ranking model | Transparent, auditable, easy to tune weights. ML is overkill for 4 pilots. |
| Conflict engine | Eager full-scan | Event-driven triggers | With <100 records, full scans are instant. Event-driven adds complexity. |

## Urgent Reassignment Interpretation

The reassignment engine follows a **2-phase approach**:

1. **Phase 1 — Available resources**: Find pilots/drones that are currently `Available` and match the urgent mission. If good matches exist, propose them with a low risk score.
2. **Phase 2 — Swap from low-priority**: If no available pilots exist, look at pilots currently assigned to `Standard` or `Low` priority missions. Propose pulling them off their current mission and reassigning to the urgent one. Risk score increases based on the displaced mission's priority.

**Risk scoring** (0–100):
- Base = `(1 - avg_match_score) × 50` — lower match quality = higher risk
- Swap penalty: +20 for any swap, +5 for Standard displacement, +20 for High displacement
- No-drone penalty: +15 if no drone is available

## Scaling Plan

| Scale | Current | Upgrade Path |
|---|---|---|
| Data volume | 4 pilots, 4 drones, 3 missions | Move to PostgreSQL, keep Sheets as sync layer |
| NLP quality | Keyword matching | Add OpenAI / Gemini for intent parsing |
| Multi-region | Single timezone | Add timezone-aware date handling |
| Audit trail | Text file decision log | Structured audit database with user attribution |
| Real-time | Manual refresh | WebSocket or polling for Sheets changes |

## If Had More Time

1. **LLM-powered conversational layer** — Use Gemini or GPT-4 for more natural language understanding and multi-turn conversations.
2. **Map visualization** — Show pilot/drone/mission locations on an interactive map (Folium or Deck.gl).
3. **Automated scheduling optimizer** — Use constraint satisfaction (OR-Tools) to auto-schedule all missions optimally.
4. **Notification system** — Email/Slack alerts when conflicts are detected or urgent missions arrive.
5. **Role-based access** — Admin vs. dispatcher vs. read-only roles.
6. **Historical analytics** — Mission completion rates, pilot utilization, drone flight hours dashboard.

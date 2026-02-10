# 🚁 Drone Operations Coordinator Agent

AI-powered agent for managing pilot rosters, drone fleets, mission assignments, conflict detection, and urgent reassignments — with Google Sheets 2-way sync.

## ⚡ Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run the app
streamlit run app.py
```

That's it. The app runs with CSV data out of the box — no API keys needed.

## 🏗 Architecture

```
┌──────────────────────────────────────────────────┐
│                   STREAMLIT UI                    │
│  ┌─────────────┐  ┌───────────┐  ┌────────────┐ │
│  │ Chat Window  │  │  Sidebar  │  │  Conflict  │ │
│  │             │  │  Tables   │  │   Alerts   │ │
│  └──────┬──────┘  └───────────┘  └────────────┘ │
├─────────┼────────────────────────────────────────┤
│         ▼          AGENT LAYER                    │
│  ┌──────────────────────────────┐                │
│  │   Coordinator Agent          │                │
│  │   Intent Parser → Router     │                │
│  └──────┬───────────────────────┘                │
├─────────┼────────────────────────────────────────┤
│         ▼      BUSINESS LOGIC                     │
│  ┌──────────┐ ┌──────────┐ ┌───────────────┐    │
│  │ Matching │ │ Conflict │ │ Reassignment  │    │
│  │  Engine  │ │  Engine  │ │    Engine     │    │
│  └──────────┘ └──────────┘ └───────────────┘    │
├──────────────────────────────────────────────────┤
│              DATA LAYER                           │
│  ┌────────────────┐  ┌─────────────────────┐    │
│  │  CSV Files      │  │  Google Sheets      │    │
│  │  (Primary)      │  │  (Optional Sync)    │    │
│  └────────────────┘  └─────────────────────┘    │
└──────────────────────────────────────────────────┘
```

## 📁 Project Structure

```
skylark-drones/
├── app.py                          # Streamlit entry point
├── agent/
│   └── coordinator_agent.py        # Intent parser + tool router
├── engines/
│   ├── matching_engine.py          # Weighted scoring (skill/cert/location/avail)
│   ├── conflict_engine.py          # 4 conflict detectors
│   └── reassignment_engine.py      # Urgent swap logic with risk scores
├── models/
│   ├── pilot.py                    # Pilot dataclass
│   ├── drone.py                    # Drone dataclass
│   └── mission.py                  # Mission dataclass
├── services/
│   └── sheets_service.py           # CSV + Google Sheets read/write
├── utils/
│   └── scoring.py                  # Weighted scoring utilities
├── data/
│   ├── pilot_roster.csv            # Working pilot data
│   ├── drone_fleet.csv             # Working drone data
│   └── missions.csv                # Working mission data
├── requirements.txt
├── .env.example
├── DECISION_LOG.md
└── README.md
```

## 💬 Example Queries

| Query | What it does |
|---|---|
| `Show available pilots in Bangalore` | Filters pilots by location + status |
| `Show pilots with thermal certification` | Filters by certification |
| `Show available drones in Mumbai` | Filters drones by location |
| `Assign best pilot and drone to PRJ001` | Runs matching engine, returns top 3 |
| `Check for conflicts` | Runs all 4 conflict detectors |
| `Urgent reassignment for PRJ002` | Generates swap plans with risk scores |
| `Mark Arjun as On Leave` | Updates status, syncs data, logs decision |
| `Reload data` | Refreshes from CSV / Sheets |

## 🎯 Matching Algorithm

**Pilot scoring** (weighted composite):
| Factor | Weight |
|---|---|
| Skill match | 40% |
| Certification match | 30% |
| Location match | 15% |
| Availability | 15% |

**Drone scoring**: Capability 50% · Location 30% · Maintenance safety 20%

## ⚠️ Conflict Detection

| Type | Severity | Description |
|---|---|---|
| Double Booking | 🔴 Critical | Pilot/drone assigned to overlapping missions |
| Skill Mismatch | 🔴 Critical | Pilot missing required skills/certifications |
| Maintenance | 🟡 Warning | Drone maintenance due before mission ends |
| Location Mismatch | 🟡 Warning | Pilot/drone location ≠ mission location |

## 🔗 Google Sheets Integration (Optional)

1. Create a Google Cloud service account
2. Share your Google Sheet with the service account email
3. Create 3 worksheets: `Pilots`, `Drones`, `Missions`
4. Set environment variables:
   ```bash
   GOOGLE_SHEETS_CREDS_JSON=path/to/credentials.json
   GOOGLE_SHEET_ID=your-sheet-id
   ```

The app auto-detects credentials and syncs both ways. Without credentials, it runs on local CSVs.

## 🚀 Deployment (Streamlit Cloud)

1. Push this repo to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Connect your GitHub repo
4. Set main file: `app.py`
5. (Optional) Add Google Sheets secrets in the Streamlit Cloud secrets panel
6. Deploy ✅

## 🧪 Test Scenarios

| # | Scenario | How to test |
|---|---|---|
| 1 | Overlapping pilot booking | Assign same pilot to PRJ001 + PRJ002, then `check conflicts` |
| 2 | Drone in maintenance | Try to assign D002 (Maintenance), conflict engine flags it |
| 3 | Certification missing | Assign P003 (no Night Ops) to PRJ002 (needs Night Ops) |
| 4 | Location mismatch | Assign Bangalore pilot to Mumbai mission |
| 5 | Urgent reassignment | `Urgent reassignment for PRJ002` — see swap plans |

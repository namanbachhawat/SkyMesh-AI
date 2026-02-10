"""
Drone Operations Coordinator — Modern SaaS Dashboard
Investor-demo-quality operations dashboard with dark theme,
glassmorphism cards, grid layout, Plotly charts, and integrated chat.
"""
import sys
import os
import logging
from pathlib import Path
from datetime import date, timedelta

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from agent.coordinator_agent import DataStore, process_message
from engines.conflict_engine import detect_all_conflicts

# ─────────────────────────────────────
# Logging
# ─────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s — %(message)s")
logger = logging.getLogger(__name__)

# ─────────────────────────────────────
# Page Config — MUST be first Streamlit call
# ─────────────────────────────────────
st.set_page_config(
    page_title="Drone Ops · Command Center",
    page_icon="🛰️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─────────────────────────────────────
# Data
# ─────────────────────────────────────
@st.cache_resource
def get_data_store():
    return DataStore()

store = get_data_store()
conflicts = detect_all_conflicts(store.pilots, store.drones, store.missions)

# Quick stat helpers
available_pilots = [p for p in store.pilots if p.status == "Available"]
assigned_pilots = [p for p in store.pilots if p.status == "Assigned"]
on_leave_pilots = [p for p in store.pilots if p.status == "On Leave"]
available_drones = [d for d in store.drones if d.status == "Available"]
maint_drones = [d for d in store.drones if d.status == "Maintenance"]
assigned_drones = [d for d in store.drones if d.status == "Assigned"]
urgent_missions = [m for m in store.missions if m.priority == "Urgent"]
high_missions = [m for m in store.missions if m.priority == "High"]

# ─────────────────────────────────────
# CSS — HEAVY custom injection
# ─────────────────────────────────────
st.markdown("""
<style>
    /* ── Import Google Font ── */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

    /* ── GLOBAL RESET ── */
    *, *::before, *::after { font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important; }
    
    /* Hide default Streamlit chrome */
    #MainMenu, footer, header, .stDeployButton { display: none !important; }
    .block-container { padding: 0 !important; max-width: 100% !important; }
    [data-testid="stSidebar"] { display: none !important; }
    [data-testid="collapsedControl"] { display: none !important; }
    .stApp { background: #0a0e1a !important; }
    
    /* ── TOP NAVIGATION ── */
    .top-nav {
        background: linear-gradient(135deg, #0d1117 0%, #161b22 100%);
        border-bottom: 1px solid rgba(99, 179, 237, 0.15);
        padding: 0.7rem 2rem;
        display: flex;
        justify-content: space-between;
        align-items: center;
        position: sticky;
        top: 0;
        z-index: 999;
        backdrop-filter: blur(20px);
    }
    .nav-brand {
        display: flex;
        align-items: center;
        gap: 0.7rem;
    }
    .nav-brand-icon {
        width: 36px;
        height: 36px;
        background: linear-gradient(135deg, #00d2ff, #3a7bd5);
        border-radius: 10px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1.2rem;
    }
    .nav-brand-text {
        font-size: 1.15rem;
        font-weight: 700;
        color: #e6edf3;
        letter-spacing: -0.02em;
    }
    .nav-brand-sub {
        font-size: 0.7rem;
        color: #8b949e;
        font-weight: 400;
        text-transform: uppercase;
        letter-spacing: 0.08em;
    }
    .nav-status {
        display: flex;
        align-items: center;
        gap: 1.5rem;
    }
    .status-badge {
        display: flex;
        align-items: center;
        gap: 0.4rem;
        padding: 0.35rem 0.9rem;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 600;
    }
    .badge-live {
        background: rgba(46, 204, 113, 0.12);
        color: #2ecc71;
        border: 1px solid rgba(46, 204, 113, 0.25);
    }
    .badge-conflicts {
        background: rgba(255, 107, 107, 0.12);
        color: #ff6b6b;
        border: 1px solid rgba(255, 107, 107, 0.25);
    }
    .badge-urgent {
        background: rgba(255, 193, 7, 0.12);
        color: #ffc107;
        border: 1px solid rgba(255, 193, 7, 0.25);
        animation: pulse-badge 2s ease-in-out infinite;
    }
    @keyframes pulse-badge {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.6; }
    }
    .dot-live {
        width: 7px; height: 7px;
        background: #2ecc71;
        border-radius: 50%;
        animation: pulse-dot 2s ease-in-out infinite;
    }
    @keyframes pulse-dot {
        0%, 100% { box-shadow: 0 0 0 0 rgba(46, 204, 113, 0.5); }
        50% { box-shadow: 0 0 0 6px rgba(46, 204, 113, 0); }
    }

    /* ── DASHBOARD CONTAINER ── */
    .dashboard {
        padding: 1.2rem 2rem 1.5rem 2rem;
    }

    /* ── GLASS CARD ── */
    .glass-card {
        background: linear-gradient(145deg, rgba(22, 27, 34, 0.9), rgba(13, 17, 23, 0.95));
        border: 1px solid rgba(99, 179, 237, 0.08);
        border-radius: 16px;
        padding: 1.2rem 1.4rem;
        backdrop-filter: blur(12px);
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        position: relative;
        overflow: hidden;
    }
    .glass-card::before {
        content: '';
        position: absolute;
        top: 0; left: 0; right: 0;
        height: 2px;
        background: linear-gradient(90deg, transparent, rgba(99, 179, 237, 0.3), transparent);
        opacity: 0;
        transition: opacity 0.3s;
    }
    .glass-card:hover {
        border-color: rgba(99, 179, 237, 0.2);
        transform: translateY(-1px);
        box-shadow: 0 8px 30px rgba(0, 0, 0, 0.3);
    }
    .glass-card:hover::before { opacity: 1; }

    .card-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 0.9rem;
    }
    .card-title {
        font-size: 0.78rem;
        font-weight: 600;
        color: #8b949e;
        text-transform: uppercase;
        letter-spacing: 0.06em;
    }
    .card-icon {
        width: 32px; height: 32px;
        border-radius: 8px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 1rem;
    }
    .icon-blue { background: rgba(59, 130, 246, 0.15); }
    .icon-green { background: rgba(34, 197, 94, 0.15); }
    .icon-amber { background: rgba(245, 158, 11, 0.15); }
    .icon-red { background: rgba(239, 68, 68, 0.15); }

    /* ── KPI BIG NUMBER ── */
    .kpi-row {
        display: flex;
        align-items: baseline;
        gap: 0.6rem;
        margin-bottom: 0.2rem;
    }
    .kpi-value {
        font-size: 2.2rem;
        font-weight: 800;
        color: #e6edf3;
        line-height: 1;
        letter-spacing: -0.03em;
    }
    .kpi-unit {
        font-size: 0.85rem;
        color: #8b949e;
        font-weight: 500;
    }
    .kpi-sub {
        font-size: 0.75rem;
        color: #8b949e;
    }
    .kpi-sub-green { color: #2ecc71; }
    .kpi-sub-red { color: #ff6b6b; }
    .kpi-sub-amber { color: #f5a623; }

    /* ── MINI STAT PILLS ── */
    .stat-pills {
        display: flex;
        gap: 0.5rem;
        margin-top: 0.8rem;
        flex-wrap: wrap;
    }
    .stat-pill {
        padding: 0.3rem 0.65rem;
        border-radius: 8px;
        font-size: 0.7rem;
        font-weight: 600;
        display: flex;
        align-items: center;
        gap: 0.3rem;
    }
    .pill-green { background: rgba(34, 197, 94, 0.1); color: #22c55e; border: 1px solid rgba(34, 197, 94, 0.15); }
    .pill-blue { background: rgba(59, 130, 246, 0.1); color: #3b82f6; border: 1px solid rgba(59, 130, 246, 0.15); }
    .pill-amber { background: rgba(245, 158, 11, 0.1); color: #f59e0b; border: 1px solid rgba(245, 158, 11, 0.15); }
    .pill-red { background: rgba(239, 68, 68, 0.1); color: #ef4444; border: 1px solid rgba(239, 68, 68, 0.15); }

    /* ── SECTION HEADER ── */
    .section-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin: 1.5rem 0 0.8rem 0;
    }
    .section-title {
        font-size: 1rem;
        font-weight: 700;
        color: #e6edf3;
        letter-spacing: -0.01em;
    }
    .section-subtitle {
        font-size: 0.75rem;
        color: #8b949e;
    }

    /* ── CONFLICT ROW ── */
    .conflict-row {
        background: rgba(22, 27, 34, 0.7);
        border: 1px solid rgba(99, 179, 237, 0.06);
        border-radius: 10px;
        padding: 0.7rem 1rem;
        margin-bottom: 0.5rem;
        display: flex;
        align-items: center;
        gap: 0.8rem;
        transition: all 0.2s;
    }
    .conflict-row:hover {
        background: rgba(30, 35, 45, 0.9);
        border-color: rgba(99, 179, 237, 0.15);
    }
    .conflict-icon {
        width: 32px; height: 32px;
        border-radius: 8px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 0.9rem;
        flex-shrink: 0;
    }
    .conflict-critical-bg { background: rgba(239, 68, 68, 0.15); }
    .conflict-warning-bg { background: rgba(245, 158, 11, 0.15); }
    .conflict-text {
        flex: 1;
    }
    .conflict-type {
        font-size: 0.78rem;
        font-weight: 600;
        color: #e6edf3;
    }
    .conflict-desc {
        font-size: 0.7rem;
        color: #8b949e;
        margin-top: 0.1rem;
    }
    .conflict-severity {
        font-size: 0.65rem;
        font-weight: 700;
        padding: 0.2rem 0.5rem;
        border-radius: 6px;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    .sev-critical { background: rgba(239,68,68,0.15); color: #ef4444; }
    .sev-warning { background: rgba(245,158,11,0.15); color: #f59e0b; }

    /* ── TABLE CARD ── */
    .table-card {
        background: linear-gradient(145deg, rgba(22, 27, 34, 0.9), rgba(13, 17, 23, 0.95));
        border: 1px solid rgba(99, 179, 237, 0.08);
        border-radius: 16px;
        padding: 1rem 1.2rem;
        overflow: hidden;
    }
    .table-card-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 0.8rem;
        padding-bottom: 0.6rem;
        border-bottom: 1px solid rgba(99, 179, 237, 0.06);
    }
    .table-card-title {
        font-size: 0.9rem;
        font-weight: 700;
        color: #e6edf3;
    }
    .table-count {
        font-size: 0.7rem;
        color: #8b949e;
        background: rgba(99, 179, 237, 0.08);
        padding: 0.2rem 0.6rem;
        border-radius: 10px;
    }

    /* Streamlit dataframe override */
    [data-testid="stDataFrame"] {
        border: none !important;
    }
    [data-testid="stDataFrame"] > div {
        border: none !important;
        border-radius: 10px !important;
        overflow: hidden !important;
    }

    /* ── CHAT PANEL ── */
    .chat-panel {
        background: linear-gradient(145deg, rgba(22, 27, 34, 0.95), rgba(13, 17, 23, 0.98));
        border: 1px solid rgba(99, 179, 237, 0.1);
        border-radius: 16px;
        overflow: hidden;
    }
    .chat-panel-header {
        background: linear-gradient(135deg, rgba(0, 210, 255, 0.08), rgba(58, 123, 213, 0.08));
        padding: 0.8rem 1.2rem;
        border-bottom: 1px solid rgba(99, 179, 237, 0.08);
        display: flex;
        align-items: center;
        gap: 0.6rem;
    }
    .chat-ai-dot {
        width: 8px; height: 8px;
        background: #00d2ff;
        border-radius: 50%;
        animation: pulse-dot 2s ease-in-out infinite;
    }
    .chat-title {
        font-size: 0.85rem;
        font-weight: 700;
        color: #e6edf3;
    }
    
    /* Quick action buttons */
    .quick-actions {
        display: flex;
        gap: 0.4rem;
        flex-wrap: wrap;
        padding: 0.6rem 1rem;
        border-bottom: 1px solid rgba(99, 179, 237, 0.05);
        background: rgba(0, 0, 0, 0.15);
    }
    .quick-btn {
        padding: 0.3rem 0.7rem;
        border-radius: 8px;
        font-size: 0.68rem;
        font-weight: 500;
        background: rgba(99, 179, 237, 0.06);
        color: #8b949e;
        border: 1px solid rgba(99, 179, 237, 0.08);
        cursor: pointer;
        transition: all 0.2s;
        text-decoration: none;
    }
    .quick-btn:hover {
        background: rgba(99, 179, 237, 0.12);
        color: #e6edf3;
        border-color: rgba(99, 179, 237, 0.2);
    }

    /* Style chat messages */
    [data-testid="stChatMessage"] {
        background: rgba(22, 27, 34, 0.5) !important;
        border: 1px solid rgba(99, 179, 237, 0.05) !important;
        border-radius: 12px !important;
        padding: 0.6rem 0.8rem !important;
        margin-bottom: 0.4rem !important;
    }
    
    /* Chat input */
    [data-testid="stChatInput"] textarea {
        background: rgba(22, 27, 34, 0.8) !important;
        border: 1px solid rgba(99, 179, 237, 0.15) !important;
        border-radius: 12px !important;
        color: #e6edf3 !important;
        font-size: 0.85rem !important;
    }
    [data-testid="stChatInput"] textarea:focus {
        border-color: rgba(0, 210, 255, 0.4) !important;
        box-shadow: 0 0 0 3px rgba(0, 210, 255, 0.1) !important;
    }

    /* Streamlit metric overrides */
    [data-testid="stMetric"] { display: none; }
    
    /* Plotly chart background */
    .js-plotly-plot { border-radius: 10px; overflow: hidden; }
    
    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 0.3rem;
        background: transparent;
    }
    .stTabs [data-baseweb="tab"] {
        background: rgba(99, 179, 237, 0.05);
        border-radius: 8px;
        border: 1px solid rgba(99, 179, 237, 0.08);
        color: #8b949e;
        font-size: 0.78rem;
        font-weight: 600;
        padding: 0.4rem 1rem;
    }
    .stTabs [aria-selected="true"] {
        background: rgba(0, 210, 255, 0.1) !important;
        border-color: rgba(0, 210, 255, 0.3) !important;
        color: #00d2ff !important;
    }
    .stTabs [data-baseweb="tab-panel"] {
        padding-top: 0.6rem;
    }
    .stTabs [data-baseweb="tab-highlight"] {
        display: none;
    }
    .stTabs [data-baseweb="tab-border"] {
        display: none;
    }
    
    /* Buttons — default */
    .stButton > button {
        background: linear-gradient(135deg, rgba(0, 210, 255, 0.1), rgba(58, 123, 213, 0.1)) !important;
        border: 1px solid rgba(0, 210, 255, 0.2) !important;
        color: #00d2ff !important;
        border-radius: 10px !important;
        font-weight: 600 !important;
        font-size: 0.78rem !important;
        transition: all 0.2s !important;
        height: 38px !important;
        min-height: 38px !important;
        max-height: 38px !important;
        white-space: nowrap !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
    }
    .stButton > button:hover {
        background: linear-gradient(135deg, rgba(0, 210, 255, 0.2), rgba(58, 123, 213, 0.2)) !important;
        border-color: rgba(0, 210, 255, 0.4) !important;
        transform: translateY(-1px);
    }

    /* Quick action button row */
    div[data-testid="stHorizontalBlock"].quick-action-row .stButton > button {
        background: rgba(99, 179, 237, 0.06) !important;
        border: 1px solid rgba(99, 179, 237, 0.12) !important;
        color: #8b949e !important;
        border-radius: 8px !important;
        font-size: 0.72rem !important;
        font-weight: 500 !important;
        padding: 0.25rem 0.5rem !important;
        min-height: 0 !important;
        height: auto !important;
    }
    div[data-testid="stHorizontalBlock"].quick-action-row .stButton > button:hover {
        background: rgba(99, 179, 237, 0.15) !important;
        color: #e6edf3 !important;
        border-color: rgba(99, 179, 237, 0.3) !important;
    }

    /* Nav badge buttons */
    .nav-btn-row .stButton > button {
        border-radius: 20px !important;
        font-size: 0.75rem !important;
        font-weight: 600 !important;
        padding: 0.35rem 0.9rem !important;
        min-height: 0 !important;
        height: auto !important;
    }
    .nav-btn-conflict .stButton > button {
        background: rgba(255, 107, 107, 0.12) !important;
        color: #ff6b6b !important;
        border: 1px solid rgba(255, 107, 107, 0.25) !important;
    }
    .nav-btn-conflict .stButton > button:hover {
        background: rgba(255, 107, 107, 0.25) !important;
    }
    .nav-btn-urgent .stButton > button {
        background: rgba(255, 193, 7, 0.12) !important;
        color: #ffc107 !important;
        border: 1px solid rgba(255, 193, 7, 0.25) !important;
        animation: pulse-badge 2s ease-in-out infinite;
    }
    .nav-btn-urgent .stButton > button:hover {
        background: rgba(255, 193, 7, 0.25) !important;
    }
    .nav-btn-live .stButton > button {
        background: rgba(46, 204, 113, 0.12) !important;
        color: #2ecc71 !important;
        border: 1px solid rgba(46, 204, 113, 0.25) !important;
        cursor: default !important;
    }
    
    /* Expander */
    [data-testid="stExpander"] {
        background: transparent !important;
        border: none !important;
    }
    
    /* Divider override */
    hr {
        border-color: rgba(99, 179, 237, 0.06) !important;
        margin: 0.5rem 0 !important;
    }
</style>
""", unsafe_allow_html=True)


# ═══════════════════════════════════════
# HELPER — inject a query into chat
# ═══════════════════════════════════════
def _inject_query(query: str):
    """Add a user query and its response to chat history, then rerun."""
    if "messages" not in st.session_state:
        st.session_state.messages = []
    st.session_state.messages.append({"role": "user", "content": query})
    response = process_message(query, store)
    st.session_state.messages.append({"role": "assistant", "content": response})
    st.rerun()

# ═══════════════════════════════════════
# TOP NAVIGATION BAR
# ═══════════════════════════════════════
conflict_count = len(conflicts)
urgent_count = len(urgent_missions)

# Brand (left side)
st.markdown("""
<div class="top-nav">
    <div class="nav-brand">
        <div class="nav-brand-icon">🛰️</div>
        <div>
            <div class="nav-brand-text">Skylark Drone Ops</div>
            <div class="nav-brand-sub">Command Center</div>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

# Status badges as clickable buttons
nav_cols = st.columns([4, 1.2, 1.2, 1.2], gap="small")
with nav_cols[0]:
    st.markdown('<div style="height:0;"></div>', unsafe_allow_html=True)  # spacer
with nav_cols[1]:
    st.markdown('<div class="nav-btn-row nav-btn-live">', unsafe_allow_html=True)
    st.button("● Systems Online", key="nav_live", disabled=True, use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)
with nav_cols[2]:
    if conflict_count > 0:
        st.markdown('<div class="nav-btn-row nav-btn-conflict">', unsafe_allow_html=True)
        if st.button(f"⚠ {conflict_count} Conflict{'s' if conflict_count != 1 else ''}", key="nav_conflict", use_container_width=True):
            _inject_query("Check for conflicts")
        st.markdown('</div>', unsafe_allow_html=True)
with nav_cols[3]:
    if urgent_count > 0:
        st.markdown('<div class="nav-btn-row nav-btn-urgent">', unsafe_allow_html=True)
        if st.button(f"🚨 {urgent_count} Urgent", key="nav_urgent", use_container_width=True):
            _inject_query("Show urgent missions")
        st.markdown('</div>', unsafe_allow_html=True)


# ═══════════════════════════════════════
# PLOTLY HELPERS — mini donut charts
# ═══════════════════════════════════════
def make_donut(labels, values, colors, hole=0.7, height=130):
    """Create a mini donut chart."""
    fig = go.Figure(data=[go.Pie(
        labels=labels, values=values,
        hole=hole,
        marker=dict(colors=colors, line=dict(color='#0a0e1a', width=2)),
        textinfo='none',
        hoverinfo='label+value',
    )])
    fig.update_layout(
        showlegend=False,
        margin=dict(t=5, b=5, l=5, r=5),
        height=height,
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(color='#8b949e', size=10),
    )
    return fig


# ═══════════════════════════════════════
# DASHBOARD CONTENT
# ═══════════════════════════════════════
st.markdown('<div class="dashboard">', unsafe_allow_html=True)

# ── ROW 1: KPI Cards (4 columns) ──
c1, c2, c3, c4 = st.columns(4, gap="medium")

with c1:
    st.markdown(f"""
    <div class="glass-card">
        <div class="card-header">
            <span class="card-title">Pilots</span>
            <div class="card-icon icon-blue">👨‍✈️</div>
        </div>
        <div class="kpi-row">
            <span class="kpi-value">{len(store.pilots)}</span>
            <span class="kpi-unit">total</span>
        </div>
        <div class="stat-pills">
            <span class="stat-pill pill-green">🟢 {len(available_pilots)} Available</span>
            <span class="stat-pill pill-blue">🔵 {len(assigned_pilots)} On Mission</span>
            <span class="stat-pill pill-amber">🟠 {len(on_leave_pilots)} On Leave</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

with c2:
    st.markdown(f"""
    <div class="glass-card">
        <div class="card-header">
            <span class="card-title">Drone Fleet</span>
            <div class="card-icon icon-green">🚁</div>
        </div>
        <div class="kpi-row">
            <span class="kpi-value">{len(store.drones)}</span>
            <span class="kpi-unit">total</span>
        </div>
        <div class="stat-pills">
            <span class="stat-pill pill-green">🟢 {len(available_drones)} Available</span>
            <span class="stat-pill pill-blue">🔵 {len(assigned_drones)} Deployed</span>
            <span class="stat-pill pill-red">🔴 {len(maint_drones)} Maintenance</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

with c3:
    st.markdown(f"""
    <div class="glass-card">
        <div class="card-header">
            <span class="card-title">Active Missions</span>
            <div class="card-icon icon-amber">📋</div>
        </div>
        <div class="kpi-row">
            <span class="kpi-value">{len(store.missions)}</span>
            <span class="kpi-unit">missions</span>
        </div>
        <div class="stat-pills">
            <span class="stat-pill pill-red">🔴 {len(urgent_missions)} Urgent</span>
            <span class="stat-pill pill-amber">🟡 {len(high_missions)} High</span>
            <span class="stat-pill pill-blue">🔵 {len(store.missions) - len(urgent_missions) - len(high_missions)} Standard</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

with c4:
    alert_color = "kpi-sub-red" if conflict_count > 0 else "kpi-sub-green"
    alert_msg = f"{conflict_count} active" if conflict_count > 0 else "All clear"
    st.markdown(f"""
    <div class="glass-card">
        <div class="card-header">
            <span class="card-title">Conflict Alerts</span>
            <div class="card-icon icon-red">⚠️</div>
        </div>
        <div class="kpi-row">
            <span class="kpi-value">{conflict_count}</span>
            <span class="kpi-unit">{'issues' if conflict_count != 1 else 'issue'}</span>
        </div>
        <span class="kpi-sub {alert_color}">{'⚠ Requires attention' if conflict_count > 0 else '✅ No conflicts detected'}</span>
    </div>
    """, unsafe_allow_html=True)


# ── ROW 2: Charts + Conflicts (visual density row) ──
st.markdown('<div style="height: 0.8rem;"></div>', unsafe_allow_html=True)
ch1, ch2, ch3 = st.columns([1, 1, 1.3], gap="medium")

with ch1:
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.markdown('<div class="card-header"><span class="card-title">Pilot Status Distribution</span></div>', unsafe_allow_html=True)
    fig_pilots = make_donut(
        labels=["Available", "On Mission", "On Leave"],
        values=[len(available_pilots), len(assigned_pilots), len(on_leave_pilots)],
        colors=["#22c55e", "#3b82f6", "#f59e0b"],
        height=155,
    )
    st.plotly_chart(fig_pilots, use_container_width=True, config={"displayModeBar": False})
    st.markdown('</div>', unsafe_allow_html=True)

with ch2:
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.markdown('<div class="card-header"><span class="card-title">Fleet Readiness</span></div>', unsafe_allow_html=True)
    fig_drones = make_donut(
        labels=["Operational", "Maintenance"],
        values=[len(available_drones) + len(assigned_drones), len(maint_drones)],
        colors=["#22c55e", "#ef4444"],
        height=155,
    )
    st.plotly_chart(fig_drones, use_container_width=True, config={"displayModeBar": False})
    st.markdown('</div>', unsafe_allow_html=True)

with ch3:
    st.markdown("""
    <div class="glass-card" style="min-height: 100%;">
        <div class="card-header">
            <span class="card-title">Live Conflict Feed</span>
        </div>
    """, unsafe_allow_html=True)

    if conflicts:
        for c in conflicts[:4]:
            icon_bg = "conflict-critical-bg" if c.severity == "Critical" else "conflict-warning-bg"
            sev_cls = "sev-critical" if c.severity == "Critical" else "sev-warning"
            icon = "🔴" if c.severity == "Critical" else "🟡"
            short_desc = c.description[:90] + "..." if len(c.description) > 90 else c.description
            st.markdown(f"""
            <div class="conflict-row">
                <div class="conflict-icon {icon_bg}">{icon}</div>
                <div class="conflict-text">
                    <div class="conflict-type">{c.conflict_type}</div>
                    <div class="conflict-desc">{short_desc}</div>
                </div>
                <span class="conflict-severity {sev_cls}">{c.severity}</span>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div style="text-align: center; padding: 2rem; color: #8b949e;">
            <div style="font-size: 2rem; margin-bottom: 0.5rem;">✅</div>
            <div style="font-size: 0.85rem;">No active conflicts</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown('</div>', unsafe_allow_html=True)


# ── ROW 3: Data Tables + Chat (main content) ──
st.markdown('<div style="height: 0.6rem;"></div>', unsafe_allow_html=True)
left_col, right_col = st.columns([1.6, 1], gap="medium")

with left_col:
    st.markdown("""
    <div class="table-card">
        <div class="table-card-header">
            <span class="table-card-title">Operations Data</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    tab1, tab2, tab3 = st.tabs(["👨‍✈️  Pilot Roster", "🚁  Drone Fleet", "📋  Missions"])

    with tab1:
        pilot_df = pd.DataFrame([{
            "Status": {"Available": "🟢", "Assigned": "🔵", "On Leave": "🟠"}.get(p.status, "⚪"),
            "ID": p.pilot_id,
            "Name": p.name,
            "Skills": ", ".join(p.skills),
            "Certifications": ", ".join(p.certifications),
            "Location": p.location,
            "Assignment": p.current_assignment or "—",
            "Available From": str(p.available_from) if p.available_from else "—",
        } for p in store.pilots])
        st.dataframe(
            pilot_df,
            use_container_width=True,
            hide_index=True,
            height=220,
            column_config={
                "Status": st.column_config.TextColumn("", width="small"),
                "ID": st.column_config.TextColumn("ID", width="small"),
                "Name": st.column_config.TextColumn("Name", width="medium"),
            },
        )

    with tab2:
        drone_df = pd.DataFrame([{
            "Status": {"Available": "🟢", "Assigned": "🔵", "Maintenance": "🔴"}.get(d.status, "⚪"),
            "ID": d.drone_id,
            "Model": d.model,
            "Capabilities": ", ".join(d.capabilities),
            "Location": d.location,
            "Maint. Due": str(d.maintenance_due) if d.maintenance_due else "—",
        } for d in store.drones])
        st.dataframe(
            drone_df,
            use_container_width=True,
            hide_index=True,
            height=220,
            column_config={
                "Status": st.column_config.TextColumn("", width="small"),
                "ID": st.column_config.TextColumn("ID", width="small"),
            },
        )

    with tab3:
        mission_df = pd.DataFrame([{
            "Priority": {"Urgent": "🔴", "High": "🟡", "Standard": "🔵", "Low": "⚪"}.get(m.priority, "⚪"),
            "ID": m.project_id,
            "Client": m.client,
            "Location": m.location,
            "Skills": ", ".join(m.required_skills),
            "Certs": ", ".join(m.required_certs),
            "Start": str(m.start_date) if m.start_date else "—",
            "End": str(m.end_date) if m.end_date else "—",
            "Pilot": m.assigned_pilot or "—",
            "Drone": m.assigned_drone or "—",
        } for m in store.missions])
        st.dataframe(
            mission_df,
            use_container_width=True,
            hide_index=True,
            height=220,
            column_config={
                "Priority": st.column_config.TextColumn("", width="small"),
                "ID": st.column_config.TextColumn("ID", width="small"),
            },
        )

with right_col:
    # ── CHAT PANEL ──
    st.markdown("""
    <div class="chat-panel">
        <div class="chat-panel-header">
            <div class="chat-ai-dot"></div>
            <span class="chat-title">AI Coordinator</span>
            <span style="font-size: 0.65rem; color: #8b949e; margin-left: auto;">Powered by Skylark AI</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Quick action buttons — real Streamlit buttons
    qa1, qa2, qa3, qa4 = st.columns(4, gap="small")
    with qa1:
        if st.button("📊 Show Pilots", key="qa_pilots", use_container_width=True):
            _inject_query("Show all pilots")
    with qa2:
        if st.button("🚁 Fleet Status", key="qa_fleet", use_container_width=True):
            _inject_query("Show all drones")
    with qa3:
        if st.button("⚠️ Conflicts", key="qa_conflicts", use_container_width=True):
            _inject_query("Check for conflicts")
    with qa4:
        if st.button("🚨 Urgent", key="qa_urgent", use_container_width=True):
            _inject_query("Urgent reassignment for PRJ002")

    # Initialize chat history
    if "messages" not in st.session_state:
        st.session_state.messages = [
            {
                "role": "assistant",
                "content": (
                    "👋 **Skylark AI Coordinator online.**\n\n"
                    "I manage pilot assignments, drone fleet, and mission operations. Try:\n"
                    "- `Show available pilots in Bangalore`\n"
                    "- `Assign best pilot to PRJ001`\n"
                    "- `Check for conflicts`\n"
                    "- `Urgent reassignment for PRJ002`"
                ),
            }
        ]

    # Chat container with fixed height
    chat_container = st.container(height=350)
    with chat_container:
        for message in st.session_state.messages:
            with st.chat_message(message["role"]):
                st.markdown(message["content"])

    # Chat input
    if prompt := st.chat_input("Ask the coordinator...", key="chat_input"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        response = process_message(prompt, store)
        st.session_state.messages.append({"role": "assistant", "content": response})
        st.rerun()


# ── Refresh Button ──
st.markdown('<div style="height: 0.5rem;"></div>', unsafe_allow_html=True)
r1, r2, r3 = st.columns([3, 1, 3])
with r2:
    if st.button("🔄  Refresh Data", use_container_width=True, key="refresh_btn"):
        store.reload()
        st.cache_resource.clear()
        st.rerun()

st.markdown('</div>', unsafe_allow_html=True)  # close dashboard div

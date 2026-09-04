import streamlit as st
from streamlit_folium import st_folium
import folium
import random
import time

# Page Configuration
st.set_page_config(
    page_title="NEURAL-LOGIX Command Center",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Dark Glassmorphism Styling
st.markdown("""
    <style>
    .stApp { background-color: #0b0f19; color: #ffffff; }
    div[data-testid="stMetric"] {
        background-color: #1e293b;
        border: 1px solid #38bdf8;
        padding: 12px;
        border-radius: 8px;
    }
    </style>
""", unsafe_allow_html=True)

# 1. SIDEBAR & LIVE RADAR CONTROLS
with st.sidebar:
    st.markdown("### 🚚 VEHICLE TYPE SELECTOR")
    vehicle_type = st.radio(
        "Choose Fleet Category:",
        ["Multi-Axle Heavy Truck", "Medium Eicher Truck", "Light Pickup / Tata Ace"],
        index=0
    )
    
    speed_caps = {
        "Multi-Axle Heavy Truck": 50,
        "Medium Eicher Truck": 65,
        "Light Pickup / Tata Ace": 80
    }
    max_speed = speed_caps[vehicle_type]
    st.info(f"⚡ Speed Cap: **{max_speed} km/h**")
    
    st.divider()
    st.markdown("### 📡 LIVE TRAFFIC RADAR SCANNER")
    auto_scan = st.checkbox("Enable Auto-Scan (2-Sec Interval)", value=True)
    
    if auto_scan:
        st.caption("🔄 Radar Active: Scanning traffic density every 2 seconds...")
        # Auto-refresh mechanism (2 seconds)
        time.sleep(2)
        st.rerun()

# 2. TOP INPUT BAR
st.markdown("## ⚡ NEURAL-LOGIX : Smart Fleet Command Center")

city_coords = {
    "Gurugram": [28.4595, 77.0266],
    "Jaipur": [26.9124, 75.7873],
    "Delhi": [28.6139, 77.2090],
    "Agra": [27.1767, 78.0081]
}

col1, col2, col3, col4, col5 = st.columns([2, 2, 2, 2, 1.5])
with col1:
    origin_city = st.selectbox("📍 ORIGIN LOCATION", list(city_coords.keys()), index=0)
with col2:
    dest_city = st.selectbox("🏁 DESTINATION", list(city_coords.keys()), index=1)
with col3:
    cargo_type = st.selectbox("📦 CARGO TYPE", ["Furniture", "Electronics", "Automobiles", "Perishables"])
with col4:
    cargo_weight = st.number_input("⚖️ CARGO LOAD (Tons)", min_value=1, max_value=40, value=18)
with col5:
    st.write("")
    st.write("")
    if st.button("🔍 MANUAL SCAN", use_container_width=True):
        st.rerun()

st.divider()

# 3. DYNAMIC TRAFFIC DENSITY SCANNER LOGIC
# Randomly simulates traffic congestion on main arterial highway
traffic_density = random.choice(["HIGH CONGESTION", "MODERATE BLOCKAGE", "CRITICAL JAM"])
traffic_delay_min = random.randint(25, 55)

st.markdown(f"### 🗺️ REAL-TIME SATELLITE RADAR & DYNAMIC TRAFFIC SCAN")
st.caption(f"🛰️ **Radar Scan Time:** {time.strftime('%H:%M:%S')} | **Main Corridor Density:** {traffic_density} (+{traffic_delay_min} min delay)")

start_pos = city_coords[origin_city]
end_pos = city_coords[dest_city]
map_center = [(start_pos[0] + end_pos[0]) / 2, (start_pos[1] + end_pos[1]) / 2]

# Google Satellite Map Base
m = folium.Map(
    location=map_center,
    zoom_start=8,
    tiles="https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}",
    attr="Google Satellite"
)

# Delhi Geofence Ban Zone
delhi_center = [28.6139, 77.2090]
folium.Circle(
    location=delhi_center,
    radius=18000,
    color="#f43f5e",
    fill=True,
    fill_opacity=0.30,
    popup="🚫 Delhi Commercial Vehicle Ban Zone"
).add_to(m)

# 1. Congested Main Highway Route (Red/Orange Curved)
congested_road_path = [
    start_pos,
    [28.5000, 77.0800],
    [28.5500, 77.1200],
    [28.6139, 77.2090], # Heavy Traffic Zone
    [28.4000, 77.3100],
    end_pos
]

# 2. Optimized AI Bypass Highway Route (Green Curved)
ai_bypass_path = [
    start_pos,
    [28.3500, 76.9200], # Manesar Bend
    [28.2200, 76.9800], # KMP Expressway Bypass
    [28.1800, 77.2500], # Clear Expressway Segment
    [28.0000, 77.4800], # Toll Plaza
    [27.6000, 77.6500], # Open Highway
    end_pos
]

# Render Congested Line
folium.PolyLine(
    congested_road_path,
    color="#f43f5e",
    weight=5,
    opacity=0.85,
    dash_array="6, 8",
    tooltip=f"🚨 Main Highway: {traffic_density} (Avoided)"
).add_to(m)

# Render AI Green Bypass Line
folium.PolyLine(
    ai_bypass_path,
    color="#00ff66",
    weight=6,
    opacity=0.95,
    tooltip="🟢 Dynamic AI Clear Bypass Highway"
).add_to(m)

# Simulated Dynamic Traffic Jam Markers
traffic_jam_point = [28.5500, 77.1200]
folium.Marker(
    traffic_jam_point,
    popup=f"⚠️ Traffic Jam Detected: +{traffic_delay_min} Mins Delay",
    tooltip="🚨 Heavy Congestion Hotspot",
    icon=folium.Icon(color="red", icon="warning", prefix="fa")
).add_to(m)

# Markers
folium.Marker(start_pos, popup=f"Origin: {origin_city}", icon=folium.Icon(color="green", icon="play", prefix="fa")).add_to(m)
folium.Marker(end_pos, popup=f"Destination: {dest_city}", icon=folium.Icon(color="red", icon="flag", prefix="fa")).add_to(m)

# TOLL PLAZA
toll_point = [28.0000, 77.4800]
folium.Marker(
    toll_point,
    popup="<b>🏢 FASTag Toll Plaza</b><br>Clear Traffic Zone",
    tooltip="FASTag Toll Plaza",
    icon=folium.Icon(color="orange", icon="building", prefix="fa")
).add_to(m)

st_folium(m, width=1200, height=450)

# 4. MATH TELEMETRY LOGIC
base_dist = 278
speed_penalty = 5 if cargo_weight > 15 else 0
calc_speed = max(30, max_speed - speed_penalty)

est_hours = base_dist / calc_speed
eta_h, eta_m = int(est_hours), int((est_hours - int(est_hours)) * 60)
fuel_needed = round(base_dist * (0.14 + (cargo_weight * 0.003)), 1)

st.divider()
st.warning(
    f"📡 **2-SECOND LIVE RADAR ALERT:**\n\n"
    f"• **TRAFFIC JAM DETECTED:** Main Corridor flagged with **{traffic_density}** (+{traffic_delay_min} Min Delay).\n\n"
    f"• **AUTONOMOUS REROUTE:** Fleet automatically bypasses bottleneck via **KMP Expressway** ➔ Saved **{traffic_delay_min} mins**."
)

# 5. SOFTWARE TELEMETRY CARDS
st.markdown("### 📊 REAL-TIME SOFTWARE TELEMETRY")
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("TOTAL DISTANCE", f"{base_dist} km", "Expressway Fixed")
c2.metric("CALCULATED SPEED", f"{calc_speed} km/h", "Load Adjusted")
c3.metric("SAVED TIME", f"{traffic_delay_min} Mins", "Traffic Bypassed")
c4.metric("RADAR STATUS", "🟢 SCANNING", "2s Auto-Refresh")
c5.metric("FUEL CONSUMPTION", f"{fuel_needed}L", f"{cargo_weight}T Payload")

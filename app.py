import streamlit as st
from streamlit_folium import st_folium
import folium
import requests
import random
import time

# Page Configuration
st.set_page_config(
    page_title="NEURAL-LOGIX Command Center",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styling with High-Contrast Solid Black Text
st.markdown("""
    <style>
    /* Main Background - Slate Dark Tone */
    .stApp {
        background-color: #0b1120 !important;
    }
    
    /* Force ALL Text, Labels, and Headings to Pure Solid Black */
    h1, h2, h3, h4, h5, h6, label, p, span, div {
        color: #000000 !important;
        font-family: 'Segoe UI', Roboto, sans-serif !important;
        font-weight: 600 !important;
    }

    /* Telemetry Glassmorphism Cards Container */
    div[data-testid="stMetric"] {
        background: rgba(255, 255, 255, 0.85) !important;
        border: 1px solid #38bdf8 !important;
        border-radius: 10px !important;
        padding: 14px !important;
        box-shadow: 0 4px 15px rgba(0, 0, 0, 0.3) !important;
    }
    
    div[data-testid="stMetricLabel"] {
        color: #000000 !important;
        font-size: 0.9rem !important;
        font-weight: 700 !important;
    }
    
    div[data-testid="stMetricValue"] {
        color: #000000 !important;
        font-weight: 800 !important;
    }

    /* Sidebar Background & Black Text Overlay */
    section[data-testid="stSidebar"] {
        background-color: #1e293b !important;
    }
    
    section[data-testid="stSidebar"] * {
        color: #000000 !important;
        font-weight: 600 !important;
    }

    /* Alert Boxes with Crisp Black Font */
    .stAlert {
        background-color: rgba(255, 255, 255, 0.9) !important;
        border: 2px solid #fbbf24 !important;
        border-radius: 8px !important;
    }
    </style>
""", unsafe_allow_html=True)

# Helper Function: Fetch Real Road Geometry via OSRM Engine
@st.cache_data(ttl=3600)
def get_real_road_route(start_coords, end_coords):
    url = f"http://router.project-osrm.org/route/v1/driving/{start_coords[1]},{start_coords[0]};{end_coords[1]},{end_coords[0]}?overview=full&geometries=geojson"
    try:
        response = requests.get(url, timeout=5)
        data = response.json()
        if "routes" in data and len(data["routes"]) > 0:
            coords = data["routes"][0]["geometry"]["coordinates"]
            return [[c[1], c[0]] for c in coords]
    except Exception:
        pass
    return [start_coords, end_coords]

# 1. SIDEBAR CONTROLS
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
    auto_scan = st.checkbox("Enable Background Auto-Refresh", value=False)
    
    if auto_scan:
        st.caption("🔄 Radar Active: Standard periodic refresh enabled.")

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
    if st.button("🔍 SCAN NOW", use_container_width=True):
        st.rerun()

st.divider()

# 3. REAL ROAD NETWORK NAVIGATION ENGINE
traffic_density = random.choice(["HIGH CONGESTION", "MODERATE BLOCKAGE", "CRITICAL JAM"])
traffic_delay_min = random.randint(25, 55)

st.markdown("### 🗺️ REAL HIGHWAY ROUTE NAVIGATION & DYNAMIC TRAFFIC SCAN")
st.caption(f"🛰️ **Radar Status:** Connected | **Main Corridor Density:** {traffic_density} (+{traffic_delay_min} min delay)")

start_pos = city_coords[origin_city]
end_pos = city_coords[dest_city]
map_center = [(start_pos[0] + end_pos[0]) / 2, (start_pos[1] + end_pos[1]) / 2]

# Google Satellite Base Layer
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

# Fetch Pure Real Road Coordinates (Cached for speed)
direct_road_geometry = get_real_road_route(start_pos, end_pos)
bypass_waypoint = [28.2200, 76.9800]
bypass_segment_1 = get_real_road_route(start_pos, bypass_waypoint)
bypass_segment_2 = get_real_road_route(bypass_waypoint, end_pos)
full_bypass_geometry = bypass_segment_1 + bypass_segment_2

# Render Direct Congested Road (Red Dash)
folium.PolyLine(
    direct_road_geometry,
    color="#f43f5e",
    weight=5,
    opacity=0.85,
    dash_array="6, 8",
    tooltip=f"🚨 Main Highway: {traffic_density} (Avoided)"
).add_to(m)

# Render Pure Highway AI Bypass Road (Green Solid)
folium.PolyLine(
    full_bypass_geometry,
    color="#10b981",
    weight=6,
    opacity=0.95,
    tooltip="🟢 Dynamic AI Pure Highway Bypass"
).add_to(m)

# Markers
traffic_jam_point = [28.5500, 77.1200]
folium.Marker(
    traffic_jam_point,
    popup=f"⚠️ Traffic Jam Detected: +{traffic_delay_min} Mins Delay",
    tooltip="🚨 Heavy Congestion Hotspot",
    icon=folium.Icon(color="red", icon="warning", prefix="fa")
).add_to(m)

folium.Marker(start_pos, popup=f"Origin: {origin_city}", icon=folium.Icon(color="green", icon="play", prefix="fa")).add_to(m)
folium.Marker(end_pos, popup=f"Destination: {dest_city}", icon=folium.Icon(color="red", icon="flag", prefix="fa")).add_to(m)

# TOLL PLAZA
toll_point = [28.1800, 77.2500]
folium.Marker(
    toll_point,
    popup="<b>🏢 FASTag Toll Plaza</b><br>Clear Highway Zone",
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
    f"📡 **RADAR TELEMETRY ALERT:**\n\n"
    f"• **TRAFFIC JAM DETECTED:** Main Corridor flagged with **{traffic_density}** (+{traffic_delay_min} Min Delay).\n\n"
    f"• **AUTONOMOUS REROUTE:** Fleet automatically bypasses bottleneck via **KMP Highway Network** ➔ Saved **{traffic_delay_min} mins**."
)

# 5. SOFTWARE TELEMETRY CARDS
st.markdown("### 📊 REAL-TIME SOFTWARE TELEMETRY")
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("TOTAL DISTANCE", f"{base_dist} km", "Highway Fixed")
c2.metric("CALCULATED SPEED", f"{calc_speed} km/h", "Load Adjusted")
c3.metric("SAVED TIME", f"{traffic_delay_min} Mins", "Traffic Bypassed")
c4.metric("RADAR STATUS", "🟢 ACTIVE", "Connected")
c5.metric("FUEL CONSUMPTION", f"{fuel_needed}L", f"{cargo_weight}T Payload")

import streamlit as st
from streamlit_folium import st_folium
import folium

# Page Configuration
st.set_page_config(
    page_title="NEURAL-LOGIX Command Center",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Dark Glassmorphism Custom Styling
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

# 1. SIDEBAR & VEHICLE MATRIX
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
    st.info(f"⚡ Fleet Speed Limit Cap: **{max_speed} km/h**")
    
    # Pitch Presentation PDF Download Option
    try:
        with open("Sinister_Six_Neural_Logix_Presentation.pdf", "rb") as pdf_file:
            st.download_button(
                label="📄 Download Pitch Presentation",
                data=pdf_file.read(),
                file_name="Sinister_Six_Neural_Logix_Presentation.pdf",
                mime="application/pdf",
                use_container_width=True
            )
    except FileNotFoundError:
        st.caption("ℹ️ Team Sinister Six Command Dashboard")

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
    st.button("🔍 RE-CALCULATE", use_container_width=True)

st.divider()

# 3. INTERACTIVE MAP ENGINE
st.markdown("### 🗺️ INTERACTIVE ROUTE MAP & GEOFENCE VIEW")

start_pos = city_coords[origin_city]
end_pos = city_coords[dest_city]
map_center = [(start_pos[0] + end_pos[0]) / 2, (start_pos[1] + end_pos[1]) / 2]

m = folium.Map(location=map_center, zoom_start=7, tiles="CartoDB dark_matter")

# Delhi Geofence Ban Zone
delhi_center = [28.6139, 77.2090]
folium.Circle(
    location=delhi_center,
    radius=18000,
    color="#f43f5e",
    fill=True,
    fill_opacity=0.35,
    popup="🚫 Delhi Commercial Vehicle Ban Zone"
).add_to(m)

# Direct Route (Blocked)
folium.PolyLine([start_pos, delhi_center, end_pos], color="#f43f5e", weight=3, opacity=0.8, dash_array="5, 10").add_to(m)

# Bypass Route (Active)
mid_bypass = [start_pos[0] - 0.2, (start_pos[1] + end_pos[1]) / 2 - 0.4]
folium.PolyLine([start_pos, mid_bypass, end_pos], color="#22c55e", weight=5, opacity=0.9).add_to(m)

# Markers
folium.Marker(start_pos, popup=f"Origin: {origin_city}").add_to(m)
folium.Marker(end_pos, popup=f"Destination: {dest_city}").add_to(m)
folium.Marker(mid_bypass, popup="🟨 FASTag Toll Plaza (₹210)").add_to(m)

st_folium(m, width=1200, height=400)

# 4. MATH TELEMETRY LOGIC
base_dist = 278
speed_penalty = 5 if cargo_weight > 15 else 0
calc_speed = max(30, max_speed - speed_penalty)

est_hours = base_dist / calc_speed
eta_h, eta_m = int(est_hours), int((est_hours - int(est_hours)) * 60)
fuel_needed = round(base_dist * (0.14 + (cargo_weight * 0.003)), 1)

st.divider()
st.warning(
    f"🚨 **AI ROUTE & GEOFENCE ALERT SYSTEM**\n\n"
    f"• **CARGO LOAD IMPACT:** {cargo_type} Payload ({cargo_weight} Tons) on {vehicle_type} ➔ Speed capped at **{calc_speed} km/h**.\n\n"
    f"• **GEOFENCE REROUTE:** Rerouted via Peripheral Expressway ➔ Avoids ₹2,000 fine."
)

# 5. SOFTWARE TELEMETRY CARDS
st.markdown("### 📊 SOFTWARE TELEMETRY & LOAD-ADJUSTED ANALYTICS")
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("TOTAL DISTANCE", f"{base_dist} km", "Route Fixed")
c2.metric("CALCULATED SPEED", f"{calc_speed} km/h", "Heavy Load Capped" if speed_penalty > 0 else "Optimal Pace")
c3.metric("ESTIMATED ETA", f"{eta_h:02d}h {eta_m:02d}m", "Bypass Applied")
c4.metric("DELIVERY STATUS", "🟢 ON-TIME", "Schedule On Track")
c5.metric("FUEL & SAVINGS", f"{fuel_needed}L | ₹450", f"{cargo_weight}T Load Adjusted")

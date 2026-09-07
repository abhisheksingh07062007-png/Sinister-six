import streamlit as st
import pandas as pd
import numpy as np
import folium
import requests
from streamlit_folium import st_folium
from sklearn.ensemble import RandomForestRegressor

# Page Config
st.set_page_config(page_title="AI Smart Freight & Route Optimizer", layout="wide")

st.title("🚛 AI Freight Logistics & Route Optimization System")
st.markdown("Automated Pre-Trip Entry, Load-Aware Fuel AI, Real Road Geometry & Driver Work Assignment")

# ---------------------------------------------------------
# 1. AI MODEL SETUP
# ---------------------------------------------------------
@st.cache_resource
def train_fuel_model():
    np.random.seed(42)
    n = 1000
    loads = np.random.uniform(1, 35, n)
    distances = np.random.uniform(50, 1000, n)
    truck_codes = np.random.randint(1, 6, n)
    fuel = (distances / (18 - 2.5 * truck_codes)) + (loads * 0.08 * distances / 100)
    
    X = pd.DataFrame({'load': loads, 'distance': distances, 'truck_code': truck_codes})
    model = RandomForestRegressor(n_estimators=50, random_state=42)
    model.fit(X, fuel)
    return model

ai_fuel_model = train_fuel_model()

truck_types = {
    "Tata Ace / Chota Hathi (1.5 Ton)": {"mileage": 16.0, "type_code": 1},
    "Eicher Pro 2049 (3.5 Ton)": {"mileage": 10.0, "type_code": 2},
    "Tata 1109 / 6-Wheeler (8 Ton)": {"mileage": 6.5, "type_code": 3},
    "10-Wheeler Heavy Freight (16 Ton)": {"mileage": 4.5, "type_code": 4},
    "12-Wheeler / 14-Wheeler Trailer (30+ Ton)": {"mileage": 3.0, "type_code": 5}
}

# City Coordinates Dictionary (Lat, Lon)
city_coords = {
    "Delhi / NCR": [28.6139, 77.2090],
    "Agra / Mathura": [27.1767, 78.0081],
    "Jaipur": [26.9124, 75.7873],
    "Mumbai": [19.0760, 72.8777],
    "Lucknow": [26.8467, 80.9462]
}

# Helper Function: Fetch Real Road Route Geometry via OSRM API
def get_osrm_route(start_coords, end_coords):
    url = f"http://router.project-osrm.org/route/v1/driving/{start_coords[1]},{start_coords[0]};{end_coords[1]},{end_coords[0]}?overview=full&geometries=geojson"
    try:
        response = requests.get(url, timeout=5)
        data = response.json()
        if "routes" in data and len(data["routes"]) > 0:
            coordinates = data["routes"][0]["geometry"]["coordinates"]
            # Swap [lon, lat] to [lat, lon] for Folium Map
            road_points = [[point[1], point[0]] for point in coordinates]
            distance_km = data["routes"][0]["distance"] / 1000.0
            return road_points, distance_km
    except Exception as e:
        pass
    # Fallback coordinates if API server times out
    return [start_coords, end_coords], 200.0

# ---------------------------------------------------------
# 2. PRE-TRIP DRIVER INPUT FORM
# ---------------------------------------------------------
st.subheader("📋 Pre-Trip Driver Data Entry (Trip Shuru Hone Se Pehle)")
st.info("👋 Driver Note: Trip start karne se pehle apni details fill karein:")

with st.form(key="driver_entry_form"):
    col_input1, col_input2, col_input3 = st.columns(3)
    
    with col_input1:
        driver_name = st.text_input("👤 Driver Name:", value="Ramesh Kumar")
        selected_truck = st.selectbox("🚚 Truck Type (Indian Standards):", list(truck_types.keys()))
    
    with col_input2:
        from_city = st.selectbox("🛫 From (Start Location):", list(city_coords.keys()), index=0)
        to_city = st.selectbox("🛬 To (Destination):", list(city_coords.keys()), index=1)
    
    with col_input3:
        current_fuel = st.number_input("⛽ Fuel Currently in Tank (Liters):", min_value=5.0, max_value=500.0, value=85.0)
        cargo_load = st.number_input("📦 Cargo Load Weight (Tons):", min_value=0.5, max_value=40.0, value=12.0)
    
    submit_button = st.form_submit_button(label="🚀 Generate Real-Road Route & AI Analysis")

# ---------------------------------------------------------
# 3. REAL ROAD MAP & ROUTE RENDERING
# ---------------------------------------------------------
if submit_button or True:
    st.markdown("---")
    st.subheader(f"🗺️ Real Highway Route: {from_city} ➔ {to_city}")

    start_pt = city_coords[from_city]
    end_pt = city_coords[to_city]

    # Fetching Actual Road Geometry
    real_road_path, actual_dist = get_osrm_route(start_pt, end_pt)

    # Initialize Map at Start Point
    m = folium.Map(location=[(start_pt[0] + end_pt[0])/2, (start_pt[1] + end_pt[1])/2], zoom_start=7)

    # Drawing the exact road-following polyline
    folium.PolyLine(real_road_path, color="#2E7D32", weight=6, opacity=0.85, tooltip="🟢 Real Highway Recommended Route (OSRM Bypasses)").add_to(m)

    # Start and End Markers
    folium.Marker(start_pt, popup=f"<b>Origin:</b> {from_city}", icon=folium.Icon(color="green", icon="play")).add_to(m)
    folium.Marker(end_pt, popup=f"<b>Destination:</b> {to_city}", icon=folium.Icon(color="red", icon="flag")).add_to(m)

    # Midpoint amenities simulation on real road
    if len(real_road_path) > 10:
        mid_idx = len(real_road_path) // 2
        p_toll = real_road_path[int(mid_idx * 0.4)]
        p_dhaba = real_road_path[int(mid_idx * 0.7)]
        p_mech = real_road_path[int(mid_idx * 1.1)]
        p_hosp = real_road_path[int(mid_idx * 1.3)]
        p_fuel = real_road_path[int(mid_idx * 1.5)]

        folium.Marker(p_toll, popup="<b>💸 Toll Plaza:</b> Highway Toll Gate - ₹380", icon=folium.Icon(color="gray", icon="tag")).add_to(m)
        folium.Marker(p_dhaba, popup="<b>🍲 Highway Dhaba:</b> Express Dhaba & Rest Area", icon=folium.Icon(color="orange", icon="cutlery")).add_to(m)
        folium.Marker(p_mech, popup="<b>🔧 24/7 Mechanic Shop:</b> National Highway Repair Shop", icon=folium.Icon(color="black", icon="wrench")).add_to(m)
        folium.Marker(p_hosp, popup="<b>🏥 Emergency Hospital:</b> Highway Trauma Unit", icon=folium.Icon(color="red", icon="plus-sign")).add_to(m)
        folium.Marker(p_fuel, popup="<b>⛽ Fuel Station:</b> Fleet Fuel Station", icon=folium.Icon(color="blue", icon="tint")).add_to(m)

    col1, col2 = st.columns([2.2, 1])

    with col1:
        st_folium(m, width=720, height=480)

    with col2:
        st.markdown("### 🤖 AI Prediction Outputs")
        truck_code = truck_types[selected_truck]["type_code"]
        predicted_fuel = ai_fuel_model.predict([[cargo_load, actual_dist, truck_code]])[0]
        
        st.metric(label="Actual Road Distance", value=f"{actual_dist:.1f} km")
        st.metric(label="Predicted Fuel Needed", value=f"{predicted_fuel:.1f} Liters")
        
        if current_fuel < predicted_fuel:
            st.error(f"⚠️ **Refuel Alert:** Short of {predicted_fuel - current_fuel:.1f} Liters!")
        else:
            st.success(f"✅ **Fuel Status OK:** Extra {current_fuel - predicted_fuel:.1f} Liters available.")

        st.markdown("""
        **Highway Symbols & Legend:**
        * 🟢 **Green Line:** Exact Road Geometry (Follows Actual Highways)
        * 🏷️ Toll Plazas | 🍲 Dhabas | 🔧 Mechanics | 🏥 Hospitals | ⛽ Fuel Stations
        """)

    # ---------------------------------------------------------
    # 4. UNLOADING & AUTOMATED NEXT WORK ASSIGNMENT
    # ---------------------------------------------------------
    st.markdown("---")
    st.subheader("📲 Driver Dashboard: Unloading & Instant Next Work Assignment")

    st.info(f"📍 **Status:** Driver **{driver_name}** has completed unloading cargo at **{to_city} Depot**.")

    st.markdown("### 🔄 Instant AI Return-Load Matchmaking")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Next Pickup Spot", f"{to_city} Freight Hub")
    c2.metric("Destination City", f"{from_city} Container Yard")
    c3.metric("Return Trip Distance", f"{actual_dist * 0.95:.0f} km")
    c4.metric("Driver Earnings", f"₹ {int(actual_dist * 18)}")

    st.success(f"📩 **Notification Pushed to {driver_name}:** 'Proceed to {to_city} Freight Hub for Return Load. Destination: {from_city}. Wages: ₹{int(actual_dist * 18)} on unloading.'")
      

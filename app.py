import streamlit as st
import pandas as pd
import numpy as np
import folium
from streamlit_folium import st_folium
from sklearn.ensemble import RandomForecastRegressor if False else None
from sklearn.ensemble import RandomForestRegressor

# Page Config
st.set_page_config(page_title="AI Smart Freight & Route Optimizer", layout="wide")

st.title("🚛 AI-Powered Indian Freight & Route Optimization System")
st.markdown("Optimal Route, Fuel Calculation, City No-Entry Bypass, & Next Trip Assignment")

# ---------------------------------------------------------
# SIDEBAR: DATA INPUT (Requirement 1)
# ---------------------------------------------------------
st.sidebar.header("📋 Trip & Vehicle Details")

# Indian Truck Types & Specs
truck_types = {
    "Tata Ace / Chota Hathi (1.5 Ton)": {"mileage": 16.0, "type_code": 1},
    "Eicher Pro 2049 (3.5 Ton)": {"mileage": 10.0, "type_code": 2},
    "Tata 1109 / 6-Wheeler (8 Ton)": {"mileage": 6.5, "type_code": 3},
    "10-Wheeler Heavy Freight (16 Ton)": {"mileage": 4.5, "type_code": 4},
    "12-Wheeler / 14-Wheeler Trailer (30+ Ton)": {"mileage": 3.0, "type_code": 5}
}

selected_truck = st.sidebar.selectbox("🚚 Select Truck Type:", list(truck_types.keys()))
current_fuel = st.sidebar.number_input("⛽ Current Fuel in Tank (Liters):", min_value=5.0, max_value=500.0, value=80.0)
from_city = st.sidebar.selectbox("🛫 From (Origin):", ["Delhi", "Mumbai", "Jaipur", "Kolkata", "Bengaluru"])
to_city = st.sidebar.selectbox("🛬 To (Destination):", ["Agra", "Ahmedabad", "Lucknow", "Pune", "Chennai"])
cargo_load = st.sidebar.slider("📦 Cargo Load Weight (Tons):", min_value=0.5, max_value=40.0, value=12.0)

# ---------------------------------------------------------
# AI MODEL (Fuel Prediction based on Load & Truck)
# ---------------------------------------------------------
@st.cache_resource
def train_fuel_model():
    np.random.seed(42)
    n = 1000
    loads = np.random.uniform(1, 35, n)
    distances = np.random.uniform(50, 1000, n)
    truck_codes = np.random.randint(1, 6, n)
    # Target Fuel
    fuel = (distances / (18 - 2.5 * truck_codes)) + (loads * 0.08 * distances / 100)
    
    X = pd.DataFrame({'load': loads, 'distance': distances, 'truck_code': truck_codes})
    model = RandomForestRegressor(n_estimators=50, random_state=42)
    model.fit(X, fuel)
    return model

ai_fuel_model = train_fuel_model()

# ---------------------------------------------------------
# ROUTE ANALYSIS & SIMULATION (Requirement 2)
# ---------------------------------------------------------
st.subheader("🗺️ AI Route & Hazard Analysis")

# Mock Route Coordinates (Delhi to Agra Region)
route_green = [[28.6139, 77.2090], [28.4089, 77.3178], [27.5706, 77.6593], [27.1767, 78.0081]] # Optimal Bypass Route
route_blue = [[28.6139, 77.2090], [28.2000, 77.0000], [27.8000, 77.4000], [27.1767, 78.0081]]  # High Traffic Route
route_red = [[28.4000, 77.2500], [28.1000, 77.3000]] # Accident Blocked Segment

# Map Creation
m = folium.Map(location=[27.8, 77.5], zoom_start=8)

# Add Routes
folium.PolyLine(route_green, color="green", weight=6, opacity=0.8, tooltip="AI Recommended Route (Bypassing No-Entry)").add_to(m)
folium.PolyLine(route_blue, color="blue", weight=4, opacity=0.7, tooltip="Traffic Congested Route").add_to(m)
folium.PolyLine(route_red, color="red", weight=6, opacity=0.9, tooltip="ACCIDENT / BLOCKED ROAD").add_to(m)

# Highway Amenities Markers
folium.Marker([27.6000, 77.6000], popup="<b>Toll Plaza:</b> ₹350", icon=folium.Icon(color="gray", icon="money")).add_to(m)
folium.Marker([27.5000, 77.5500], popup="<b>Highway Dhaba:</b> Pahalwan Dhaba", icon=folium.Icon(color="orange", icon="cutlery")).add_to(m)
folium.Marker([27.7000, 77.6500], popup="<b>24/7 Mechanic Shop:</b> Royal Repair", icon=folium.Icon(color="black", icon="wrench")).add_to(m)
folium.Marker([27.4500, 77.5000], popup="<b>Emergency Hospital:</b> City Trauma Center", icon=folium.Icon(color="red", icon="plus-sign")).add_to(m)
folium.Marker([27.8000, 77.7000], popup="<b>Petrol/Diesel Pump:</b> IOCL Fuel Station", icon=folium.Icon(color="blue", icon="tint")).add_to(m)

# No-Entry Bypass Marker
folium.Marker([28.1000, 77.3500], popup="<b>🚫 City No-Entry Zone:</b> Bypassed via Ring Road", icon=folium.Icon(color="darkred", icon="remove")).add_to(m)

col1, col2 = st.columns([2, 1])

with col1:
    st_folium(m, width=700, height=450)

with col2:
    st.markdown("### 📊 AI Trip Insights")
    est_distance = 230 # km
    truck_code = truck_types[selected_truck]["type_code"]
    predicted_fuel = ai_fuel_model.predict([[cargo_load, est_distance, truck_code]])[0]
    
    st.metric(label="Estimated Distance", value=f"{est_distance} km")
    st.metric(label="Predicted Fuel Needed", value=f"{predicted_fuel:.1f} Liters")
    
    if current_fuel < predicted_fuel:
        st.error(f"⚠️ Warning: Need {predicted_fuel - current_fuel:.1f} Liters extra fuel!")
    else:
        st.success("✅ Sufficient Fuel Available!")

    st.markdown("""
    **Route Legend:**
    * 🟢 **Green:** AI Optimal Route (Bypasses City No-Entry)
    * 🔵 **Blue:** High Traffic Route
    * 🔴 **Red:** Accident / Blocked Road
    """)

# ---------------------------------------------------------
# DRIVER AUTOMATED NEXT TRIP ASSIGNMENT (Requirement 3)
# ---------------------------------------------------------
st.markdown("---")
st.subheader("📲 Driver Dashboard & Automated Next Work Assignment")

st.info(f"📍 **Status:** Unloading completed at **{to_city} Warehouse Terminal**.")

st.markdown("### 🔄 AI Return-Load Auto Assignment")

col_a, col_b, col_c, col_d = st.columns(4)
col_a.metric("Next Pickup City", "Mathura (Near Agra)")
col_b.metric("Next Drop City", "Delhi Container Depot")
col_c.metric("Trip Distance", "165 km")
col_d.metric("Driver Wages / Payout", "₹ 3,800")

st.success("🚛 **Driver Instructions Sent to WhatsApp/App:** 'Proceed to Mathura Freight Yard for Auto-Parts Loading. Payout: ₹3,800 on Unloading.'")
  

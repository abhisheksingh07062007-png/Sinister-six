"""
AI-Powered Indian Freight & Route Optimization System
========================================================
A production-ready Streamlit application for commercial truck route planning,
AI-based fuel prediction, live OSRM road-routing, highway amenity mapping,
and automated return-load assignment.

Run with:  streamlit run app.py
"""

import random
import math
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import requests
import folium
import streamlit as st
from streamlit_folium import st_folium
from sklearn.ensemble import RandomForestRegressor

# ----------------------------------------------------------------------------
# PAGE CONFIG
# ----------------------------------------------------------------------------
st.set_page_config(
    page_title="AI Freight & Route Optimizer | India",
    page_icon="🚛",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ----------------------------------------------------------------------------
# STATIC REFERENCE DATA
# ----------------------------------------------------------------------------

CITY_COORDS = {
    "Delhi/NCR": (28.6139, 77.2090),
    "Agra/Mathura": (27.1767, 78.0081),
    "Jaipur": (26.9124, 75.7873),
    "Mumbai": (19.0760, 72.8777),
    "Lucknow": (26.8467, 80.9462),
    "Bengaluru": (12.9716, 77.5946),
    "Ahmedabad": (23.0225, 72.5714),
}

TRUCK_SPECS = {
    "Tata Ace / 1.5 Ton": {
        "max_load_ton": 1.5,
        "base_mileage_kmpl": 15.0,
        "tank_capacity_l": 45,
        "toll_class": "Light Motor Vehicle (LMV)",
        "toll_multiplier": 1.0,
    },
    "Eicher Pro 2049 / 3.5 Ton": {
        "max_load_ton": 3.5,
        "base_mileage_kmpl": 10.5,
        "tank_capacity_l": 120,
        "toll_class": "Light Commercial Vehicle (LCV)",
        "toll_multiplier": 1.5,
    },
    "Tata 1109 6-Wheeler / 8 Ton": {
        "max_load_ton": 8.0,
        "base_mileage_kmpl": 6.5,
        "tank_capacity_l": 200,
        "toll_class": "Multi-Axle / Bus-Truck",
        "toll_multiplier": 2.2,
    },
    "10-Wheeler Heavy Freight / 16 Ton": {
        "max_load_ton": 16.0,
        "base_mileage_kmpl": 4.2,
        "tank_capacity_l": 300,
        "toll_class": "Heavy Construction Machinery (HCM)",
        "toll_multiplier": 3.2,
    },
    "12/14-Wheeler Trailer / 30+ Ton": {
        "max_load_ton": 32.0,
        "base_mileage_kmpl": 2.6,
        "tank_capacity_l": 450,
        "toll_class": "Oversized / Multi-Axle Vehicle (MAV)",
        "toll_multiplier": 4.5,
    },
}

DIESEL_PRICE_PER_L = 92.0  # INR, approx national average
PAYOUT_PER_KM = 32.0       # INR base driver payout per km
PAYOUT_PER_TON = 180.0     # INR bonus per ton of cargo carried

OSRM_BASE_URL = "http://router.project-osrm.org/route/v1/driving"

# ----------------------------------------------------------------------------
# AI FUEL PREDICTION MODEL
# ----------------------------------------------------------------------------

@st.cache_resource(show_spinner=False)
def train_fuel_model():
    rng = np.random.default_rng(42)
    n_samples = 6000

    truck_list = list(TRUCK_SPECS.values())

    distances = rng.uniform(50, 2200, n_samples)
    truck_choices = rng.integers(0, len(truck_list), n_samples)

    max_loads = np.array([truck_list[i]["max_load_ton"] for i in truck_choices])
    base_mileages = np.array([truck_list[i]["base_mileage_kmpl"] for i in truck_choices])

    loads = rng.uniform(0, 1.05, n_samples) * max_loads
    load_ratio = np.clip(loads / np.maximum(max_loads, 0.1), 0, 1.1)

    effective_mileage = base_mileages * (1 - 0.35 * (load_ratio ** 1.3))
    effective_mileage = np.clip(effective_mileage, 0.8, None)

    base_fuel = distances / effective_mileage
    noise_factor = rng.normal(loc=1.0, scale=0.07, size=n_samples)
    congestion_penalty = rng.uniform(0.0, 0.12, n_samples) * base_fuel

    fuel_liters = (base_fuel * noise_factor) + congestion_penalty
    fuel_liters = np.clip(fuel_liters, 1, None)

    X = np.column_stack([distances, loads, max_loads, base_mileages])
    y = fuel_liters

    model = RandomForestRegressor(
        n_estimators=250,
        max_depth=14,
        min_samples_leaf=3,
        random_state=42,
        n_jobs=-1,
    )
    model.fit(X, y)
    return model


def predict_fuel_needed(model, distance_km, load_ton, truck_key):
    specs = TRUCK_SPECS[truck_key]
    features = np.array([[distance_km, load_ton, specs["max_load_ton"], specs["base_mileage_kmpl"]]])
    predicted = model.predict(features)[0]
    return round(float(predicted), 1)


# ----------------------------------------------------------------------------
# OSRM LIVE ROUTING
# ----------------------------------------------------------------------------

@st.cache_data(show_spinner=False, ttl=3600)
def fetch_osrm_route(origin_latlon, dest_latlon):
    o_lat, o_lon = origin_latlon
    d_lat, d_lon = dest_latlon

    url = f"{OSRM_BASE_URL}/{o_lon},{o_lat};{d_lon},{d_lat}"
    params = {"overview": "full", "geometries": "geojson", "steps": "false"}

    response = requests.get(url, params=params, timeout=20)
    response.raise_for_status()
    data = response.json()

    if data.get("code") != "Ok" or not data.get("routes"):
        raise ValueError("OSRM could not compute a valid road route for these coordinates.")

    route = data["routes"][0]
    coords_lonlat = route["geometry"]["coordinates"]
    coords_latlon = [(lat, lon) for lon, lat in coords_lonlat]

    distance_km = route["distance"] / 1000.0
    duration_min = route["duration"] / 60.0

    return {
        "coords": coords_latlon,
        "distance_km": round(distance_km, 1),
        "duration_min": round(duration_min, 0),
    }


# ----------------------------------------------------------------------------
# HIGHWAY AMENITY SIMULATION
# ----------------------------------------------------------------------------

AMENITY_STYLE = {
    "toll": {"icon": "money-bill", "color": "orange", "prefix": "fa", "label": "Toll Plaza"},
    "dhaba": {"icon": "cutlery", "color": "green", "prefix": "fa", "label": "Highway Dhaba / Rest Area"},
    "mechanic": {"icon": "wrench", "color": "gray", "prefix": "fa", "label": "24/7 Heavy Truck Mechanic"},
    "hospital": {"icon": "plus-square", "color": "red", "prefix": "fa", "label": "Emergency Trauma Hospital"},
    "fuel": {"icon": "tint", "color": "blue", "prefix": "fa", "label": "Petrol / Diesel Pump"},
    "no_entry": {"icon": "ban", "color": "darkred", "prefix": "fa", "label": "City No-Entry / Bypass Alert"},
}


def generate_route_amenities(route_coords, distance_km, truck_key, seed=7):
    rng = random.Random(seed)
    n_points = len(route_coords)
    specs = TRUCK_SPECS[truck_key]

    amenities = []

    approx_gap_km = rng.uniform(45, 90)
    n_tolls = max(1, int(distance_km // approx_gap_km))
    for i in range(1, n_tolls + 1):
        idx = min(max(int(n_points * (i / (n_tolls + 1))), 0), n_points - 1)
        base_price = rng.randint(65, 175)
        toll_price = round(base_price * specs["toll_multiplier"])
        amenities.append({
            "type": "toll",
            "coord": route_coords[idx],
            "name": f"NH Toll Plaza #{i}",
            "detail": f"Estimated toll: Rs {toll_price} ({specs['toll_class']})",
        })

    dhaba_names = ["Highway King Dhaba", "Punjabi Rasoi", "Truckers Point", "Sher-e-Punjab Dhaba", "National Highway Bhojnalya"]
    n_dhabas = max(1, int(distance_km // rng.uniform(100, 150)))
    for i in range(1, n_dhabas + 1):
        idx = min(max(int(n_points * (i / (n_dhabas + 1))), 0), n_points - 1)
        amenities.append({
            "type": "dhaba",
            "coord": route_coords[idx],
            "name": rng.choice(dhaba_names),
            "detail": "Parking for heavy trucks, meals & rest rooms available",
        })

    n_mech = max(1, int(distance_km // rng.uniform(150, 250)))
    for i in range(1, n_mech + 1):
        idx = min(max(int(n_points * (i / (n_mech + 1))), 0), n_points - 1)
        amenities.append({
            "type": "mechanic",
            "coord": route_coords[idx],
            "name": f"Highway Truck Care Center {i}",
            "detail": "24/7 tyre, puncture, clutch & engine repair for heavy vehicles",
        })

    n_hosp = max(1, int(distance_km // rng.uniform(200, 300)))
    for i in range(1, n_hosp + 1):
        idx = min(max(int(n_points * (i / (n_hosp + 1))), 0), n_points - 1)
        amenities.append({
            "type": "hospital",
            "coord": route_coords[idx],
            "name": f"NH Trauma & Emergency Care {i}",
            "detail": "24-hour emergency ward, ambulance on standby",
        })

    n_fuel = max(1, int(distance_km // rng.uniform(80, 130)))
    for i in range(1, n_fuel + 1):
        idx = min(max(int(n_points * (i / (n_fuel + 1))), 0), n_points - 1)
        brand = rng.choice(["Indian Oil", "Bharat Petroleum", "Hindustan Petroleum", "Reliance Petrol Pump"])
        amenities.append({
            "type": "fuel",
            "coord": route_coords[idx],
            "name": f"{brand} Fuel Station",
            "detail": f"Diesel available, approx Rs {DIESEL_PRICE_PER_L}/L",
        })

    for frac in (0.04, 0.96):
        idx = min(max(int(n_points * frac), 0), n_points - 1)
        window = "6 AM - 11 PM" if frac < 0.5 else "7 AM - 10 PM"
        amenities.append({
            "type": "no_entry",
            "coord": route_coords[idx],
            "name": "City Limit — Heavy Vehicle Restriction",
            "detail": f"No entry for heavy trucks {window}. Use ring-road bypass.",
        })

    return amenities


# ----------------------------------------------------------------------------
# MAP BUILDER
# ----------------------------------------------------------------------------

def build_route_map(route_coords, amenities, origin_name, origin_coord, dest_name, dest_coord):
    mid_idx = len(route_coords) // 2
    center = route_coords[mid_idx]

    fmap = folium.Map(location=center, zoom_start=6, tiles="OpenStreetMap", control_scale=True)

    folium.PolyLine(
        locations=route_coords,
        color="#1a8f3c",
        weight=5,
        opacity=0.85,
        tooltip="Recommended Highway Route",
    ).add_to(fmap)

    folium.Marker(
        location=origin_coord,
        popup=f"<b>Origin:</b> {origin_name}",
        icon=folium.Icon(color="blue", icon="play", prefix="fa"),
    ).add_to(fmap)

    folium.Marker(
        location=dest_coord,
        popup=f"<b>Destination:</b> {dest_name}",
        icon=folium.Icon(color="black", icon="flag-checkered", prefix="fa"),
    ).add_to(fmap)

    layer_groups = {}
    for key, style in AMENITY_STYLE.items():
        layer_groups[key] = folium.FeatureGroup(name=style["label"])
        fmap.add_child(layer_groups[key])

    for a in amenities:
        style = AMENITY_STYLE[a["type"]]
        popup_html = f"<b>{a['name']}</b><br>{a['detail']}"
        folium.Marker(
            location=a["coord"],
            popup=folium.Popup(popup_html, max_width=280),
            tooltip=a["name"],
            icon=folium.Icon(color=style["color"], icon=style["icon"], prefix=style["prefix"]),
        ).add_to(layer_groups[a["type"]])

    folium.LayerControl(collapsed=False).add_to(fmap)
    return fmap


# ----------------------------------------------------------------------------
# RETURN LOAD ASSIGNMENT ENGINE
# ----------------------------------------------------------------------------

def assign_return_load(current_dest_city, truck_key):
    candidate_cities = [c for c in CITY_COORDS.keys() if c != current_dest_city]
    return_dest_city = random.choice(candidate_cities)

    origin_coord = CITY_COORDS[current_dest_city]
    dest_coord = CITY_COORDS[return_dest_city]

    try:
        route = fetch_osrm_route(origin_coord, dest_coord)
        distance_km = route["distance_km"]
    except Exception:
        lat1, lon1 = origin_coord
        lat2, lon2 = dest_coord
        R = 6371.0
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
        a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
        straight_km = 2 * R * math.asin(math.sqrt(a))
        distance_km = round(straight_km * 1.25, 1)

    specs = TRUCK_SPECS[truck_key]
    return_load_ton = round(random.uniform(0.5, specs["max_load_ton"]), 1)

    payout = (distance_km * PAYOUT_PER_KM) + (return_load_ton * PAYOUT_PER_TON)
    payout = round(payout, -1)

    pickup_window = datetime.now() + timedelta(hours=random.randint(2, 6))
    commodities = ["Textiles", "Electronics", "FMCG Goods", "Packaged Foods", "Hardware", "Auto Parts", "Agro Produce"]

    return {
        "return_pickup_city": current_dest_city,
        "return_dest_city": return_dest_city,
        "distance_km": distance_km,
        "load_ton": return_load_ton,
        "commodity": random.choice(commodities),
        "payout_inr": payout,
        "pickup_by": pickup_window.strftime("%d %b %Y, %I:%M %p"),
    }


# ----------------------------------------------------------------------------
# SESSION STATE INIT
# ----------------------------------------------------------------------------

if "trip_computed" not in st.session_state:
    st.session_state.trip_computed = False
if "route_data" not in st.session_state:
    st.session_state.route_data = None
if "amenities" not in st.session_state:
    st.session_state.amenities = None
if "trip_summary" not in st.session_state:
    st.session_state.trip_summary = None
if "return_load" not in st.session_state:
    st.session_state.return_load = None

# ----------------------------------------------------------------------------
# HEADER
# ----------------------------------------------------------------------------

st.title("🚛 AI-Powered Indian Freight & Route Optimization System")
st.caption("Real highway routing • AI fuel prediction • Live amenity mapping • Automated return-load matching")

st.divider()

# ----------------------------------------------------------------------------
# 1. PRE-TRIP DRIVER INPUT FORM
# ----------------------------------------------------------------------------

st.subheader("📋 Pre-Trip Driver Entry")

with st.form("pretrip_form"):
    col1, col2 = st.columns(2)

    with col1:
        driver_name = st.text_input("Driver Name", value="Ramesh Kumar")
        truck_type = st.selectbox("Truck Type", options=list(TRUCK_SPECS.keys()), index=2)
        current_fuel = st.number_input(
            "Current Fuel in Tank (Liters)", min_value=0.0, max_value=500.0, value=80.0, step=5.0
        )

    with col2:
        city_options = list(CITY_COORDS.keys())
        from_city = st.selectbox("From City (Origin)", options=city_options, index=0)
        to_city_options = [c for c in city_options if c != from_city]
        to_city = st.selectbox("To City (Destination)", options=to_city_options, index=0)
        cargo_load = st.number_input(
            "Cargo Load Weight (Tons)", min_value=0.0, max_value=40.0, value=5.0, step=0.5
        )

    submitted = st.form_submit_button("🧭 Calculate Route & AI Fuel Plan", use_container_width=True)

if submitted:
    specs = TRUCK_SPECS[truck_type]
    if cargo_load > specs["max_load_ton"] * 1.1:
        st.error(
            f"⚠️ Cargo load ({cargo_load} T) exceeds the safe limit for {truck_type} "
            f"(max rated capacity: {specs['max_load_ton']} T). Please reduce the load or choose a heavier truck."
        )
        st.session_state.trip_computed = False
    else:
        with st.spinner("Fetching real highway route from OSRM and running AI fuel prediction..."):
            try:
                origin_coord = CITY_COORDS[from_city]
                dest_coord = CITY_COORDS[to_city]
                route = fetch_osrm_route(origin_coord, dest_coord)
                amenities = generate_route_amenities(
                    route["coords"], route["distance_km"], truck_type,
                    seed=hash((from_city, to_city, truck_type)) % (10 ** 6),
                )
                model = train_fuel_model()
                predicted_fuel = predict_fuel_needed(model, route["distance_km"], cargo_load, truck_type)

                st.session_state.trip_computed = True
                st.session_state.route_data = route
                st.session_state.amenities = amenities
                st.session_state.trip_summary = {
                    "driver_name": driver_name,
                    "truck_type": truck_type,
                    "current_fuel": current_fuel,
                    "from_city": from_city,
                    "to_city": to_city,
                    "cargo_load": cargo_load,
                    "predicted_fuel": predicted_fuel,
                    "distance_km": route["distance_km"],
                    "duration_min": route["duration_min"],
                }
                st.session_state.return_load = None
            except requests.exceptions.RequestException:
                st.error("🚫 Could not reach the OSRM routing service. Please check your internet connection and try again.")
                st.session_state.trip_computed = False
            except ValueError as e:
                st.error(f"🚫 Routing error: {e}")
                st.session_state.trip_computed = False

st.divider()

# ----------------------------------------------------------------------------
# 2 & 3. ROUTE MAP + TRIP INSIGHTS
# ----------------------------------------------------------------------------

if st.session_state.get("trip_computed") and st.session_state.get("trip_summary") is not None:
    summary = st.session_state.trip_summary
    route = st.session_state.route_data
    amenities = st.session_state.amenities

    st.subheader("🗺️ Real Highway Route & Amenities")
    st.caption("Green line follows actual roads via OSRM. Toggle amenity layers using the control in the top-right of the map.")

    fmap = build_route_map(
        route["coords"], amenities,
        summary["from_city"], CITY_COORDS[summary["from_city"]],
        summary["to_city"], CITY_COORDS[summary["to_city"]],
    )
    # Added key to prevent streamlit-folium re-render crashes
    st_folium(fmap, width=None, height=520, returned_objects=[], key="main_route_map")

    st.subheader("📊 Trip Insights")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Actual Road Distance", f"{summary['distance_km']} km")
    m2.metric("Estimated Drive Time", f"{summary['duration_min']:.0f} min (~{summary['duration_min']/60:.1f} hrs)")
    m3.metric("AI-Predicted Fuel Needed", f"{summary['predicted_fuel']} L")
    m4.metric("Current Fuel in Tank", f"{summary['current_fuel']} L")

    fuel_diff = round(summary["current_fuel"] - summary["predicted_fuel"], 1)
    estimated_cost = round(summary["predicted_fuel"] * DIESEL_PRICE_PER_L)

    if fuel_diff < 0:
        st.error(f"⚠️ Short of {abs(fuel_diff)} Liters — refuel before departure or plan a fuel stop en route.")
    else:
        st.success(f"✅ Surplus {fuel_diff} Liters — sufficient fuel for this trip.")

    st.info(f"⛽ Estimated Diesel Cost for this trip: **Rs {estimated_cost:,.0f}** (at Rs {DIESEL_PRICE_PER_L}/L)")

    amenity_counts = pd.Series([a["type"] for a in amenities]).value_counts()
    with st.expander("🛣️ Highway Amenities Along This Route"):
        cols = st.columns(len(AMENITY_STYLE))
        for i, (key, style) in enumerate(AMENITY_STYLE.items()):
            count = int(amenity_counts.get(key, 0))
            cols[i].metric(style["label"], count)

    st.divider()

    # ------------------------------------------------------------------------
    # 4. DRIVER DASHBOARD & AUTOMATED RETURN LOAD
    # ------------------------------------------------------------------------

    st.subheader("📱 Driver Dashboard — Trip Completion & Re-Routing")

    st.write(
        f"**Driver:** {summary['driver_name']}  |  **Truck:** {summary['truck_type']}  |  "
        f"**Current Trip:** 

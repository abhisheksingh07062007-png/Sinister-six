import random
import math
import time
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import requests
import folium
from folium.plugins import AntPath
import streamlit as st
from streamlit_folium import st_folium
from sklearn.ensemble import RandomForestRegressor

# PAGE CONFIG
st.set_page_config(
    page_title="AI Freight & Route Optimizer",
    page_icon="🚛",
    layout="wide",
    initial_sidebar_state="expanded",
)

# STATIC REFERENCE DATA
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
        "toll_class": "LMV",
        "toll_multiplier": 1.0,
    },
    "Eicher Pro 2049 / 3.5 Ton": {
        "max_load_ton": 3.5,
        "base_mileage_kmpl": 10.5,
        "tank_capacity_l": 120,
        "toll_class": "LCV",
        "toll_multiplier": 1.5,
    },
    "Tata 1109 6-Wheeler / 8 Ton": {
        "max_load_ton": 8.0,
        "base_mileage_kmpl": 6.5,
        "tank_capacity_l": 200,
        "toll_class": "Bus-Truck",
        "toll_multiplier": 2.2,
    },
    "10-Wheeler Heavy Freight / 16 Ton": {
        "max_load_ton": 16.0,
        "base_mileage_kmpl": 4.2,
        "tank_capacity_l": 300,
        "toll_class": "HCM",
        "toll_multiplier": 3.2,
    },
    "12/14-Wheeler Trailer / 30+ Ton": {
        "max_load_ton": 32.0,
        "base_mileage_kmpl": 2.6,
        "tank_capacity_l": 450,
        "toll_class": "MAV",
        "toll_multiplier": 4.5,
    },
}

DIESEL_PRICE_PER_L = 92.0
PAYOUT_PER_KM = 32.0
PAYOUT_PER_TON = 180.0
OSRM_BASE_URL = "http://router.project-osrm.org/route/v1/driving"

# AI FUEL PREDICTION MODEL
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

# OSRM LIVE ROUTING
@st.cache_data(show_spinner=False, ttl=3600)
def fetch_osrm_route(origin_latlon, dest_latlon):
    o_lat, o_lon = origin_latlon
    d_lat, d_lon = dest_latlon
    url = OSRM_BASE_URL + "/" + str(o_lon) + "," + str(o_lat) + ";" + str(d_lon) + "," + str(d_lat)
    params = {"overview": "full", "geometries": "geojson", "steps": "false"}
    response = requests.get(url, params=params, timeout=20)
    response.raise_for_status()
    data = response.json()
    if data.get("code") != "Ok" or not data.get("routes"):
        raise ValueError("Invalid route")
    route = data["routes"][0]
    coords_lonlat = route["geometry"]["coordinates"]
    coords_latlon = [(lat, lon) for lon, lat in coords_lonlat]
    return {
        "coords": coords_latlon,
        "distance_km": round(route["distance"] / 1000.0, 1),
        "duration_min": round(route["duration"] / 60.0, 0),
    }

AMENITY_STYLE = {
    "toll": {"icon": "money-bill", "color": "orange", "prefix": "fa", "label": "Toll Plaza"},
    "dhaba": {"icon": "cutlery", "color": "green", "prefix": "fa", "label": "Dhaba"},
    "mechanic": {"icon": "wrench", "color": "gray", "prefix": "fa", "label": "Mechanic"},
    "hospital": {"icon": "plus-square", "color": "red", "prefix": "fa", "label": "Hospital"},
    "fuel": {"icon": "tint", "color": "blue", "prefix": "fa", "label": "Fuel Pump"},
    "no_entry": {"icon": "ban", "color": "darkred", "prefix": "fa", "label": "No-Entry"},
}

def generate_route_amenities(route_coords, distance_km, truck_key, seed=7):
    rng = random.Random(seed)
    n_points = len(route_coords)
    specs = TRUCK_SPECS[truck_key]
    amenities = []
    
    n_tolls = max(1, int(distance_km // 60))
    for i in range(1, n_tolls + 1):
        idx = min(max(int(n_points * (i / (n_tolls + 1))), 0), n_points - 1)
        toll_price = round(rng.randint(65, 175) * specs["toll_multiplier"])
        amenities.append({
            "type": "toll",
            "coord": route_coords[idx],
            "name": "Toll #" + str(i),
            "detail": "Cost: Rs " + str(toll_price),
            "cost_val": toll_price,
            "index": idx
        })

    n_dhabas = max(1, int(distance_km // 120))
    for i in range(1, n_dhabas + 1):
        idx = min(max(int(n_points * (i / (n_dhabas + 1))), 0), n_points - 1)
        amenities.append({
            "type": "dhaba",
            "coord": route_coords[idx],
            "name": "Highway Dhaba " + str(i),
            "detail": "Food and Rest Stop",
            "cost_val": 0,
            "index": idx
        })

    n_mech = max(1, int(distance_km // 180))
    for i in range(1, n_mech + 1):
        idx = min(max(int(n_points * (i / (n_mech + 1))), 0), n_points - 1)
        repair_cost = rng.randint(250, 1200)
        amenities.append({
            "type": "mechanic",
            "coord": route_coords[idx],
            "name": "Truck Repair " + str(i),
            "detail": "Est Repair Charge: Rs " + str(repair_cost),
            "cost_val": repair_cost,
            "index": idx
        })

    n_hosp = max(1, int(distance_km // 250))
    for i in range(1, n_hosp + 1):
        idx = min(max(int(n_points * (i / (n_hosp + 1))), 0), n_points - 1)
        amenities.append({
            "type": "hospital",
            "coord": route_coords[idx],
            "name": "Trauma Care " + str(i),
            "detail": "Emergency Hospital",
            "cost_val": 0,
            "index": idx
        })

    n_fuel = max(1, int(distance_km // 100))
    for i in range(1, n_fuel + 1):
        idx = min(max(int(n_points * (i / (n_fuel + 1))), 0), n_points - 1)
        amenities.append({
            "type": "fuel",
            "coord": route_coords[idx],
            "name": "Fuel Station " + str(i),
            "detail": "Diesel Rs " + str(DIESEL_PRICE_PER_L) + "/L",
            "cost_val": 0,
            "index": idx
        })

    return sorted(amenities, key=lambda x: x["index"])

# ANIMATED MAP BUILDER WITH LIVE TRUCK LOCATION
def build_route_map(route_coords, amenities, origin_name, origin_coord, dest_name, dest_coord, current_truck_idx):
    center = route_coords[current_truck_idx]
    fmap = folium.Map(location=center, zoom_start=8, tiles="OpenStreetMap")

    AntPath(
        locations=route_coords,
        color="#1a8f3c",
        pulse_color="#ffffff",
        weight=6,
        delay=1000
    ).add_to(fmap)

    folium.Marker(location=origin_coord, popup=origin_name, icon=folium.Icon(color="blue")).add_to(fmap)
    folium.Marker(location=dest_coord, popup=dest_name, icon=folium.Icon(color="black")).add_to(fmap)

    truck_coord = route_coords[current_truck_idx]
    folium.Marker(
        location=truck_coord,
        popup="<b>🚛 Live Moving Truck</b>",
        tooltip="Live GPS Location",
        icon=folium.Icon(color="red", icon="truck", prefix="fa")
    ).add_to(fmap)

    for a in amenities:
        style = AMENITY_STYLE[a["type"]]
        folium.Marker(
            location=a["coord"],
            popup=a["name"] + ": " + a["detail"],
            icon=folium.Icon(color=style["color"], icon=style["icon"], prefix=style["prefix"]),
        ).add_to(fmap)

    return fmap

def assign_return_load(current_dest_city, truck_key):
    candidate_cities = [c for c in CITY_COORDS.keys() if c != current_dest_city]
    return_dest_city = random.choice(candidate_cities)
    origin_coord = CITY_COORDS[current_dest_city]
    dest_coord = CITY_COORDS[return_dest_city]

    try:
        route = fetch_osrm_route(origin_coord, dest_coord)
        distance_km = route["distance_km"]
    except Exception:
        distance_km = 450.0

    specs = TRUCK_SPECS[truck_key]
    return_load_ton = round(random.uniform(0.5, specs["max_load_ton"]), 1)
    payout = round((distance_km * PAYOUT_PER_KM) + (return_load_ton * PAYOUT_PER_TON), -1)
    pickup_window = datetime.now() + timedelta(hours=random.randint(2, 6))

    return {
        "return_pickup_city": current_dest_city,
        "return_dest_city": return_dest_city,
        "distance_km": distance_km,
        "load_ton": return_load_ton,
        "commodity": "FMCG / Industrial Goods",
        "payout_inr": payout,
        "pickup_by": pickup_window.strftime("%d %b, %I:%M %p"),
    }

# INITIALIZE SESSION STATE
if "trip_computed" not in st.session_state:
    st.session_state["trip_computed"] = False
if "route_data" not in st.session_state:
    st.session_state["route_data"] = None
if "amenities" not in st.session_state:
    st.session_state["amenities"] = None
if "trip_summary" not in st.session_state:
    st.session_state["trip_summary"] = None
if "return_load" not in st.session_state:
    st.session_state["return_load"] = None
if "financial_ledger" not in st.session_state:
    st.session_state["financial_ledger"] = None
if "truck_idx" not in st.session_state:
    st.session_state["truck_idx"] = 0
if "is_tracking" not in st.session_state:
    st.session_state["is_tracking"] = False

# HEADER
st.title("🚛 Smart Freight AI: Real-Time Fleet & Route Optimization")
st.divider()

# 1. PRE-TRIP DRIVER FORM
st.subheader("📋 Pre-Trip Driver Entry")

with st.form("pretrip_form"):
    col1, col2 = st.columns(2)
    with col1:
        driver_name = st.text_input("Driver Name", value="Ramesh Kumar")
        truck_type = st.selectbox("Truck Type", options=list(TRUCK_SPECS.keys()), index=2)
        current_fuel = st.number_input("Current Fuel (L)", min_value=0.0, value=40.0)
    with col2:
        city_options = list(CITY_COORDS.keys())
        from_city = st.selectbox("From", options=city_options, index=0)
        to_city_options = [c for c in city_options if c != from_city]
        to_city = st.selectbox("To", options=to_city_options, index=0)
        cargo_load = st.number_input("Cargo Weight (Tons)", min_value=0.0, value=5.0)

    submitted = st.form_submit_button("🧭 Calculate Route & Start GPS Tracking", use_container_width=True)

if submitted:
    specs = TRUCK_SPECS[truck_type]
    if cargo_load > specs["max_load_ton"] * 1.1:
        st.error("⚠️ Overload Error: Reduce cargo weight.")
        st.session_state["trip_computed"] = False
    else:
        with st.spinner("Calculating live route & training AI model..."):
            try:
                origin_coord = CITY_COORDS[from_city]
                dest_coord = CITY_COORDS[to_city]
                route = fetch_osrm_route(origin_coord, dest_coord)
                amenities = generate_route_amenities(
                    route["coords"], route["distance_km"], truck_type
                )
                model = train_fuel_model()
                predicted_fuel = predict_fuel_needed(
                    model, route["distance_km"], cargo_load, truck_type
                )

                st.session_state["trip_computed"] = True
                st.session_state["route_data"] = route
                st.session_state["amenities"] = amenities
                st.session_state["trip_summary"] = {
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
                st.session_state["return_load"] = None
                st.session_state["financial_ledger"] = None
                st.session_state["truck_idx"] = 0
                st.session_state["is_tracking"] = True
            except Exception as e:
                st.error("Error: " + str(e))
                st.session_state["trip_computed"] = False

st.divider()

# 2. DASHBOARD & LIVE MAP
if st.session_state.get("trip_computed") and st.session_state.get("trip_summary"):
    summary = st.session_state["trip_summary"]
    route = st.session_state["route_data"]
    amenities = st.session_state["amenities"]
    route_pts = route["coords"]
    total_pts = len(route_pts)

    curr_idx = st.session_state["truck_idx"]

    # REAL-TIME ALERTS PANEL
    st.subheader("🔔 Real-Time Highway & GPS Alerts")

    req_fuel = summary["predicted_fuel"]
    curr_fuel = summary["current_fuel"]
    
    if curr_fuel < req_fuel:
        shortage = round(req_fuel - curr_fuel, 1)
        st.error("🚨 **FUEL ALERT:** ईंधन कम है! AI के अनुसार इस ट्रिप में " + str(req_fuel) + "L चाहिए। " + str(shortage) + "L डीजल तुरंत डलवाएं!")
    else:
        st.success("⛽ **Fuel Status:** पर्याप्त फ्यूल उपलब्ध है। (टैंक: " + str(curr_fuel) + "L | AI Predicted Needed: " + str(req_fuel) + "L)")

    # 500m Geofencing Detector
    next_amenity = None
    for a in amenities:
        if a["index"] >= curr_idx:
            next_amenity = a
            break

    if next_amenity:
        dist_ahead_km = round(((next_amenity["index"] - curr_idx) / total_pts) * summary["distance_km"], 2)
        dist_meters = int(dist_ahead_km * 1000)
        
        if dist_meters <= 500:
            st.error("🚨 **500m GEONOTIFICATION ALERT (आगे " + str(dist_meters) + " मीटर पर):** " + str(next_amenity["name"]) + " — " + str(next_amenity["detail"]))
        elif dist_ahead_km <= 2.0:
            st.warning("⚠️ **PROXIMITY WARNING (आगे " + str(dist_ahead_km) + " km):** " + str(next_amenity["name"]) + " — " + str(next_amenity["detail"]))
        else:
            st.info("ℹ️ **Up Ahead (" + str(dist_ahead_km) + " km):** " + str(next_amenity["name"]) + " — " + str(next_amenity["detail"]))

    # GPS SIMULATION CONTROLS
    col_play, col_pct = st.columns([1, 4])
    with col_play:
        if st.button("⏯️ Pause / Play Live GPS"):
            st.session_state["is_tracking"] = not st.session_state["is_tracking"]
    with col_pct:
        pct_complete = round((curr_idx / max(total_pts - 1, 1)) * 100, 1)
        st.progress(curr_idx / max(total_pts - 1, 1), text="📡 Live GPS Tracking Progress: " + str(pct_complete) + "%")

    # MAP DISPLAY
    st.subheader("🗺️ Live GPS Tracking & Animated Route")
    fmap = build_route_map(
        route_pts,
        amenities,
        summary["from_city"],
        CITY_COORDS[summary["from_city"]],
        summary["to_city"],
        CITY_COORDS[summary["to_city"]],
        curr_idx
    )
    st_folium(fmap, width=None, height=480, returned_objects=[], key="main_map_" + str(curr_idx))

    st.subheader("📊 AI Route Insights")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Distance", str(summary["distance_km"]) + " km")
    m2.metric("Time", str(round(summary["duration_min"])) + " min")
    m3.metric("AI Required Fuel", str(summary["predicted_fuel"]) + " L")
    m4.metric("Current Fuel Tank", str(summary["current_fuel"]) + " L")

    st.divider()

    # 3. DRIVER DASHBOARD, TRIP FINANCIALS & RETURN LOAD ASSIGNMENT
    st.subheader("📱 Driver Dashboard & Trip Financial Summary")

    d_name = str(summary.get("driver_name"))
    t_type = str(summary.get("truck_type"))
    f_city = str(summary.get("from_city"))
    t_city = str(summary.get("to_city"))

    st.write("**Driver:** " + d_name + " | **Truck:** " + t_type + " | **Current Active Trip:** " + f_city + " ➔ " + t_city)

    # COMPLETE TRIP & CALCULATE FINANCIALS BUTTON
    if st.button("🏁 Complete Trip & Calculate Profit / Loss", use_container_width=True):
        # 1. Total Revenue Calculation
        gross_revenue = round((summary["distance_km"] * PAYOUT_PER_KM) + (summary["cargo_load"] * PAYOUT_PER_TON), -1)

        # 2. Fuel Expense
        fuel_expense = round(summary["predicted_fuel"] * DIESEL_PRICE_PER_L, 1)

        # 3. Toll Expense
        toll_expense = sum([a["cost_val"] for a in amenities if a["type"] == "toll"])

        # 4. Repair/Maintenance Expense
        repair_expense = sum([a["cost_val"] for a in amenities if a["type"] == "mechanic"])

        # 5. Net Profit
        total_expenses = fuel_expense + toll_expense + repair_expense
        net_profit = round(gross_revenue - total_expenses, 1)

        # Store financial ledger in state
        st.session_state["financial_ledger"] = {
            "gross_revenue": gross_revenue,
            "fuel_expense": fuel_expense,
            "toll_expense": toll_expense,
            "repair_expense": repair_expense,
            "total_expenses": total_expenses,
            "net_profit": net_profit
        }

        # Assign Return Load
        rl = assign_return_load(t_city, t_type)
        st.session_state["return_load"] = rl

        # Prepare for Return Route Switch
        ret_from = rl["return_pickup_city"]
        ret_to = rl["return_dest_city"]
        ret_cargo = rl["load_ton"]

        new_route = fetch_osrm_route(CITY_COORDS[ret_from], CITY_COORDS[ret_to])
        new_amenities = generate_route_amenities(new_route["coords"], new_route["distance_km"], t_type)
        model = train_fuel_model()
        ret_pred_fuel = predict_fuel_needed(model, new_route["distance_km"], ret_cargo, t_type)

        st.session_state["route_data"] = new_route
        st.session_state["amenities"] = new_amenities
        st.session_state["truck_idx"] = 0
        st.session_state["is_tracking"] = True
        st.session_state["trip_summary"] = {
            "driver_name": d_name,
            "truck_type": t_type,
            "current_fuel": summary["current_fuel"],
            "from_city": ret_from,
            "to_city": ret_to,
            "cargo_load": ret_cargo,
            "predicted_fuel": ret_pred_fuel,
            "distance_km": new_route["distance_km"],
            "duration_min": new_route["duration_min"],
        }
        st.rerun()

    # DISPLAY TRIP FINANCIAL LEDGER IF AVAILABLE
    if st.session_state.get("financial_ledger"):
        ledger = st.session_state["financial_ledger"]
        st.subheader("💰 Completed Trip Profit & Loss Statement (P&L)")

        p1, p2, p3, p4 = st.columns(4)
        p1.metric(" Gross Revenue (कमाई)", "Rs " + str(ledger["gross_revenue"]))
        p2.metric("⛽ Fuel Cost (डीजल)", "Rs " + str(ledger["fuel_expense"]))
        p3.metric("🛣️ Toll + Repairs (टोल व मरम्मत)", "Rs " + str(ledger["toll_expense"] + ledger["repair_expense"]))
        
        profit_val = ledger["net_profit"]
        if profit_val >= 0:
            p4.metric("📈 Net Profit (शुद्ध लाभ)", "Rs " + str(profit_val), delta="Profit")
        else:
            p4.metric("📉 Net Loss (नुकसान)", "Rs " + str(profit_val), delta="-Loss")

        # Detailed Expense Breakd

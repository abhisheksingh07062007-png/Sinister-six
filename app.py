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
        "toll_multiplier": 1.0,
    },
    "Eicher Pro 2049 / 3.5 Ton": {
        "max_load_ton": 3.5,
        "base_mileage_kmpl": 10.5,
        "tank_capacity_l": 120,
        "toll_multiplier": 1.5,
    },
    "Tata 1109 6-Wheeler / 8 Ton": {
        "max_load_ton": 8.0,
        "base_mileage_kmpl": 6.5,
        "tank_capacity_l": 200,
        "toll_multiplier": 2.2,
    },
    "10-Wheeler Heavy Freight / 16 Ton": {
        "max_load_ton": 16.0,
        "base_mileage_kmpl": 4.2,
        "tank_capacity_l": 300,
        "toll_multiplier": 3.2,
    },
    "12/14-Wheeler Trailer / 30+ Ton": {
        "max_load_ton": 32.0,
        "base_mileage_kmpl": 2.6,
        "tank_capacity_l": 450,
        "toll_multiplier": 4.5,
    },
}

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
    url = f"{OSRM_BASE_URL}/{o_lon},{o_lat};{d_lon},{d_lat}"
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
    "dhaba": {"icon": "cutlery", "color": "green", "prefix": "fa", "label": "Dhaba / Hotel"},
    "mechanic": {"icon": "wrench", "color": "gray", "prefix": "fa", "label": "Mechanic Shop"},
    "hospital": {"icon": "plus-square", "color": "red", "prefix": "fa", "label": "Hospital"},
    "fuel": {"icon": "tint", "color": "blue", "prefix": "fa", "label": "Cheapest Fuel Pump Stop"},
    "other_fuel": {"icon": "tint", "color": "lightgray", "prefix": "fa", "label": "Other Fuel Pump"},
}

def generate_route_amenities(route_coords, distance_km, truck_key, current_fuel, predicted_fuel, seed=7):
    rng = random.Random(seed)
    n_points = len(route_coords)
    specs = TRUCK_SPECS[truck_key]
    amenities = []
    
    # 1. TOLLS
    n_tolls = max(1, int(distance_km // 60))
    for i in range(1, n_tolls + 1):
        idx = min(max(int(n_points * (i / (n_tolls + 1))), 0), n_points - 1)
        toll_price = round(rng.randint(65, 175) * specs["toll_multiplier"])
        amenities.append({
            "type": "toll",
            "coord": route_coords[idx],
            "name": f"Toll Plaza #{i}",
            "detail": f"Cost: Rs {toll_price}",
            "cost_val": toll_price,
            "index": idx
        })

    # 2. DHABAS / HOTELS
    n_dhabas = max(1, int(distance_km // 80))
    for i in range(1, n_dhabas + 1):
        idx = min(max(int(n_points * (i / (n_dhabas + 1))), 0), n_points - 1)
        amenities.append({
            "type": "dhaba",
            "coord": route_coords[idx],
            "name": f"Highway Hotel/Dhaba #{i}",
            "detail": "Food, Tea & Rest Stop",
            "cost_val": 0,
            "index": idx
        })

    # 3. MECHANICS
    n_mech = max(1, int(distance_km // 110))
    for i in range(1, n_mech + 1):
        idx = min(max(int(n_points * (i / (n_mech + 1))), 0), n_points - 1)
        repair_cost = rng.randint(250, 1200)
        amenities.append({
            "type": "mechanic",
            "coord": route_coords[idx],
            "name": f"Truck Repair & Tyre Shop #{i}",
            "detail": f"Est Repair Charge: Rs {repair_cost}",
            "cost_val": repair_cost,
            "index": idx
        })

    # 4. HOSPITALS
    n_hosp = max(1, int(distance_km // 150))
    for i in range(1, n_hosp + 1):
        idx = min(max(int(n_points * (i / (n_hosp + 1))), 0), n_points - 1)
        amenities.append({
            "type": "hospital",
            "coord": route_coords[idx],
            "name": f"Emergency Hospital #{i}",
            "detail": "24/7 Emergency Medical Care",
            "cost_val": 0,
            "index": idx
        })

    # 5. MULTIPLE FUEL PUMPS
    fuel_candidates = []
    n_fuel_pumps = max(3, int(distance_km // 90))
    for i in range(1, n_fuel_pumps + 1):
        idx = min(max(int(n_points * (i / (n_fuel_pumps + 1))), 0), n_points - 1)
        price_per_l = round(rng.uniform(89.5, 95.0), 2)
        pump_name = f"Highway Fuel Station #{i}"
        fuel_candidates.append({
            "index": idx,
            "coord": route_coords[idx],
            "name": pump_name,
            "price_per_l": price_per_l
        })

    best_pump = min(fuel_candidates, key=lambda x: x["price_per_l"])
    needed_liters = max(0.0, round(predicted_fuel - current_fuel, 1))

    for pump in fuel_candidates:
        if pump["index"] == best_pump["index"]:
            amenities.append({
                "type": "fuel",
                "coord": pump["coord"],
                "name": f"⭐ AI Suggested Stop: {pump['name']}",
                "detail": f"Cheapest Diesel: Rs {pump['price_per_l']}/L | Refuel {needed_liters}L",
                "cost_val": round(needed_liters * pump["price_per_l"], 1),
                "index": pump["index"],
                "price_per_l": pump["price_per_l"],
                "needed_liters": needed_liters,
                "is_best": True
            })
        else:
            amenities.append({
                "type": "other_fuel",
                "coord": pump["coord"],
                "name": pump["name"],
                "detail": f"Diesel Rate: Rs {pump['price_per_l']}/L (Higher Price)",
                "cost_val": 0,
                "index": pump["index"],
                "price_per_l": pump["price_per_l"],
                "is_best": False
            })

    return sorted(amenities, key=lambda x: x["index"]), fuel_candidates, best_pump

# ANIMATED MAP BUILDER
def build_route_map(route_coords, amenities, origin_name, origin_coord, dest_name, dest_coord, current_truck_idx, best_pump):
    center = route_coords[current_truck_idx]
    fmap = folium.Map(location=center, zoom_start=8, tiles="OpenStreetMap")

    AntPath(
        locations=route_coords,
        color="#1a8f3c",
        pulse_color="#ffffff",
        weight=6,
        delay=1000
    ).add_to(fmap)

    pump_coord = best_pump["coord"]
    detour_in = (pump_coord[0] + 0.003, pump_coord[1] + 0.003)
    detour_path = [pump_coord, detour_in, pump_coord]
    
    folium.PolyLine(
        locations=detour_path,
        color="blue",
        weight=4,
        dash_array="5, 10",
        tooltip="Fuel Pit-stop Detour (In & Out of Station)"
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
            popup=f"{a['name']}: {a['detail']}",
            icon=folium.Icon(color=style["color"], icon=style["icon"], prefix=style["prefix"]),
        ).add_to(fmap)

    return fmap

# SESSION STATE INITIALIZATION
if "trip_computed" not in st.session_state:
    st.session_state["trip_computed"] = False
if "route_data" not in st.session_state:
    st.session_state["route_data"] = None
if "amenities" not in st.session_state:
    st.session_state["amenities"] = None
if "all_pumps" not in st.session_state:
    st.session_state["all_pumps"] = None
if "best_pump" not in st.session_state:
    st.session_state["best_pump"] = None
if "trip_summary" not in st.session_state:
    st.session_state["trip_summary"] = None
if "financial_ledger" not in st.session_state:
    st.session_state["financial_ledger"] = None
if "truck_idx" not in st.session_state:
    st.session_state["truck_idx"] = 0
if "is_tracking" not in st.session_state:
    st.session_state["is_tracking"] = False

# HEADER
st.title("🚛 Smart Freight AI: Real-Time Fleet & Route Optimization")
st.divider()

# PRE-TRIP DRIVER FORM
st.subheader("📋 Pre-Trip Driver Entry")

with st.form("pretrip_form"):
    col1, col2 = st.columns(2)
    with col1:
        driver_name = st.text_input("Driver Name", value="Ramesh Kumar")
        truck_type = st.selectbox("Truck Type", options=list(TRUCK_SPECS.keys()), index=2)
        current_fuel = st.number_input("Current Fuel in Tank (L)", min_value=0.0, value=40.0)
    with col2:
        city_options = list(CITY_COORDS.keys())
        from_city = st.selectbox("From", options=city_options, index=0)
        to_city_options = [c for c in city_options if c != from_city]
        to_city = st.selectbox("To", options=to_city_options, index=0)
        cargo_load = st.number_input("Cargo Weight (Tons)", min_value=0.0, value=5.0)

    submitted = st.form_submit_button("🧭 Analyze All Fuel Prices & Plan Best Route", use_container_width=True)

if submitted:
    specs = TRUCK_SPECS[truck_type]
    if cargo_load > specs["max_load_ton"] * 1.1:
        st.error("⚠️ Overload Error: Reduce cargo weight.")
        st.session_state["trip_computed"] = False
    else:
        with st.spinner("Analyzing fuel prices across all highway stations & optimizing route..."):
            try:
                origin_coord = CITY_COORDS[from_city]
                dest_coord = CITY_COORDS[to_city]
                route = fetch_osrm_route(origin_coord, dest_coord)
                model = train_fuel_model()
                predicted_fuel = predict_fuel_needed(
                    model, route["distance_km"], cargo_load, truck_type
                )
                
                amenities, all_pumps, best_pump = generate_route_amenities(
                    route["coords"], route["distance_km"], truck_type, current_fuel, predicted_fuel
                )

                st.session_state["trip_computed"] = True
                st.session_state["route_data"] = route
                st.session_state["amenities"] = amenities
                st.session_state["all_pumps"] = all_pumps
                st.session_state["best_pump"] = best_pump
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
                st.session_state["financial_ledger"] = None
                st.session_state["truck_idx"] = 0
                st.session_state["is_tracking"] = True
            except Exception as e:
                st.error(f"Error: {e}")
                st.session_state["trip_computed"] = False

st.divider()

# DASHBOARD & MAP
if st.session_state.get("trip_computed") and st.session_state.get("trip_summary"):
    summary = st.session_state["trip_summary"]
    route = st.session_state["route_data"]
    amenities = st.session_state["amenities"]
    all_pumps = st.session_state["all_pumps"]
    best_pump = st.session_state["best_pump"]
    route_pts = route["coords"]
    total_pts = len(route_pts)
    curr_idx = st.session_state["truck_idx"]

    # --- 1. LOW FUEL ALERT BANNER ---
    req_fuel = summary["predicted_fuel"]
    curr_fuel = summary["current_fuel"]
    needed_liters = max(0.0, round(req_fuel - curr_fuel, 1))

    if curr_fuel < req_fuel:
        st.error(
            f"🚨 **FUEL ALERT: Warning, Low Fuel in Tank!** "
            f"आपकी गाड़ी में {curr_fuel}L ईंधन है जबकि पूरी यात्रा के लिए {req_fuel}L ईंधन की आवश्यकता है। "
            f"AI ने रास्ते में सबसे सस्ते पेट्रोल पंप **{best_pump['name']}** से {needed_liters}L रिफ्यूलिंग का सुझाव दिया है।"
        )
    else:
        st.success("✅ **Tank Status:** आपकी गाड़ी में पर्याप्त ईंधन मौजूद है!")

    # --- 2. 500m PROXIMITY RADAR ALERT ---
    nearby_alerts = []
    lookahead_range = max(1, int(total_pts * 0.05))
    
    for item in amenities:
        if curr_idx < item["index"] <= curr_idx + lookahead_range:
            item_label = AMENITY_STYLE[item['type']]['label']
            nearby_alerts.append(f"⚠️ **500m-1km आगे अलर्ट:** आपके रास्ते में **{item['name']}** ({item_label}) आने वाला है! ({item['detail']})")

    if nearby_alerts:
        for alert_msg in nearby_alerts:
            st.warning(alert_msg)

    # --- 3. AI FUEL PRICE ANALYSIS TABLE ---
    st.subheader("💡 AI Fuel Price Analysis (सभी पेट्रोल पंपों के रेट का विश्लेषण)")
    
    pumps_df = pd.DataFrame([
        {
            "Station Name": p["name"],
            "Diesel Rate (INR/L)": f"Rs {p['price_per_l']}",
            "Status": "⭐ Selected (Cheapest)" if p["index"] == best_pump["index"] else "Passed (Expensive)"
        }
        for p in all_pumps
    ])
    st.table(pumps_df)

    # GPS TRACKING CONTROLS
    col_play, col_pct = st.columns([1, 4])
    with col_play:
        if st.button("⏯️ Pause / Play Live GPS"):
            st.session_state["is_tracking"] = not st.session_state["is_tracking"]
    with col_pct:
        pct_complete = round((curr_idx / max(total_pts - 1, 1)) * 100, 1)
        st.progress(curr_idx / max(total_pts - 1, 1), text=f"📡 Live GPS Tracking Progress: {pct_complete}%")

    # MAP DISPLAY
    st.subheader("🗺️ Live GPS Route Map & Nearby Amenities")
    fmap = build_route_map(
        route_pts,
        amenities,
        summary["from_city"],
        CITY_COORDS[summary["from_city"]],
        summary["to_city"],
        CITY_COORDS[summary["to_city"]],
        curr_idx,
        best_pump
    )
    st_folium(fmap, width=None, height=480, returned_objects=[], key=f"main_map_{curr_idx}")

    st.divider()

    # PROFIT & LOSS CALCULATOR
    st.subheader("💰 Trip Financials & Profit/Loss Calculation")

    if st.button("🏁 Calculate Complete Trip Profit & Loss", use_container_width=True):
        gross_revenue = round((summary["distance_km"] * PAYOUT_PER_KM) + (summary["cargo_load"] * PAYOUT_PER_TON), -1)
        fuel_expense = round(needed_liters * best_pump["price_per_l"], 1)
        toll_expense = sum([a["cost_val"] for a in amenities if a["type"] == "toll"])
        repair_expense = sum([a["cost_val"] for a in amenities if a["type"] == "mechanic"])

        total_expenses = round(fuel_expense + toll_expense + repair_expense, 1)
        net_profit = round(gross_revenue - total_expenses, 1)

        st.session_state["financial_ledger"] = {
            "gross_revenue": gross_revenue,
            "fuel_expense": fuel_expense,
            "toll_expense": toll_expense,
            "repair_expense": repair_expense,
            "total_expenses": total_expenses,
            "net_profit": net_profit,
            "best_pump_name": best_pump["name"],
            "best_rate": best_pump["price_per_l"],
            "needed_liters": needed_liters
        }

    if st.session_state.get("financial_ledger"):
        ledger = st.session_state["financial_ledger"]
        
        p1, p2, p3, p4 = st.columns(4)
        p1.metric("Gross Revenue (कुल कमाई)", f"Rs {ledger['gross_revenue']}")
        p2.metric("⛽ Fuel Cost (डीजल खर्च)", f"Rs {ledger['fuel_expense']}")
        p3.metric("🛣️ Toll + Repairs (टोल व मरम्मत)", f"Rs {ledger['toll_expense'] + ledger['repair_expense']}")
        
        profit_val = ledger["net_profit"]
        if profit_val >= 0:
            p4.metric("📈 Net Profit (शुद्ध मुनाफा)", f"Rs {profit_val}", delta="Profit")
        else:
            p4.metric("📉 Net Loss (नुकसान)", f"Rs {profit_val}", delta="-Loss")

        st.write("### 🧾 Detailed Ledger Breakdown")
        breakdown_df = pd.DataFrame([
            {"Item": "Total Gross Earnings", "Amount": f"Rs {ledger['gross_revenue']}", "Category": "Income (+)"},
            {
                "Item": f"Refuel Expense ({ledger['needed_liters']}L at {ledger['best_pump_name']} @ Rs {ledger['best_rate']}/L)",
                "Amount": f"Rs {ledger['fuel_expense']}",
                "Category": "Expense (-)"
            },
            {"Item": "Total Toll Taxes", "Amount": f"Rs {ledger['toll_expense']}", "Category": "Expense (-)"},
            {"Item": "Maintenance / Mechanic Charges", "Amount": f"Rs {ledger['repair_expense']}", "Category": "Expense (-)"},
            {"Item": "TOTAL EXPENSES", "Amount": f"Rs {ledger['total_expenses']}", "Category": "Subtotal (-)"},
            {"Item": "NET TRIP PROFIT", "Amount": f"Rs {ledger['net_profit']}", "Category": "NET PROFIT"}
        ])
        st.table(breakdown_df)

    # AUTO-LOOP GPS MOVEMENT
    if st.session_state["is_tracking"] and curr_idx < total_pts - 1:
        time.sleep(8)
        st.session_state["truck_idx"] = min(curr_idx + max(1, int(total_pts * 0.05)), total_pts - 1)
        st.r

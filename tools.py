# encoding: utf-8
"""
tools.py - UrbanPilot City Generator
Generates a brand new city from scratch on any empty land.
NO existing infrastructure assumed.
Returns structured JSON with circles, markers, polylines.
"""
import math, random


DEG = 1 / 111.0  # 1 degree lat/lng ≈ 111 km


def offset(lat, lng, dlat_km, dlng_km):
    """Offset a point by km in lat/lng direction"""
    return (
        round(lat + dlat_km * DEG, 6),
        round(lng + dlng_km * DEG, 6)
    )


def circle_points(center_lat, center_lng, radius_km, steps=36):
    """Generate polygon points for a circle"""
    points = []
    for i in range(steps):
        angle = math.radians(i * 360 / steps)
        plat = center_lat + radius_km * math.cos(angle) * DEG
        plng = center_lng + radius_km * math.sin(angle) * DEG
        points.append([round(plat, 6), round(plng, 6)])
    points.append(points[0])
    return points


# ─────────────────────────────────────────────
# MAIN CITY GENERATOR
# ─────────────────────────────────────────────
def generate_new_city(lat: float, lng: float,
                      population: int, budget: int,
                      priority: str, area_sqkm: float) -> dict:
    """
    Generate a complete new city plan from scratch.
    Returns structured JSON with zones, buildings, roads.
    """
    r = math.sqrt(area_sqkm / math.pi)  # city radius in km

    # Zone radii (proportional to city size)
    zone_sizes = {
        "residential":    r * 0.55,
        "commercial":     r * 0.30,
        "industrial":     r * 0.28,
        "green":          r * (0.35 if priority == "environment" else 0.25),
        "infrastructure": r * 0.20
    }

    # Zone centers (spread around city center)
    zone_centers = {
        "residential":    offset(lat, lng,  r * 0.30, -r * 0.25),
        "commercial":     offset(lat, lng,  r * 0.05,  r * 0.05),
        "industrial":     offset(lat, lng, -r * 0.45,  r * 0.45),
        "green":          offset(lat, lng,  r * 0.40,  r * 0.42),
        "infrastructure": offset(lat, lng, -r * 0.25, -r * 0.35),
    }

    zone_colors = {
        "residential":    "#4ade80",
        "commercial":     "#60a5fa",
        "industrial":     "#f97316",
        "green":          "#22c55e",
        "infrastructure": "#a78bfa"
    }

    zone_labels = {
        "residential":    f"Residential Zone (35%) — {int(population*0.05):,} housing units",
        "commercial":     "Commercial Zone (20%) — 3 CBDs + IT Park",
        "industrial":     "Eco-Industrial Zone (12%) — 200 units",
        "green":          f"Green Zone ({25 if priority=='environment' else 20}%) — {max(8, population//250000)} parks",
        "infrastructure": "Infrastructure Zone (13%) — Roads + Utilities"
    }

    # ── ZONES ─────────────────────────────────
    zones = []
    for ztype, (zlat, zlng) in zone_centers.items():
        zones.append({
            "type":    ztype,
            "label":   zone_labels[ztype],
            "lat":     zlat,
            "lng":     zlng,
            "radius_km": round(zone_sizes[ztype], 3),
            "color":   zone_colors[ztype],
            "opacity": 0.15
        })

    # ── BUILDINGS ─────────────────────────────
    buildings = []
    rlat, rlng = zone_centers["residential"]
    clat, clng = zone_centers["commercial"]
    glat, glng = zone_centers["green"]
    rr = zone_sizes["residential"]
    cr = zone_sizes["commercial"]
    gr = zone_sizes["green"]

    def rand_in_zone(zlat, zlng, zr, n):
        pts = []
        for _ in range(n):
            angle = random.uniform(0, 2 * math.pi)
            dist  = random.uniform(0.05 * zr, 0.85 * zr)
            pts.append(offset(zlat, zlng, dist * math.cos(angle), dist * math.sin(angle)))
        return pts

    # Hospitals — in residential zone
    n_hosp = max(2, population // 500000)
    for i, (hlat, hlng) in enumerate(rand_in_zone(rlat, rlng, rr, n_hosp)):
        buildings.append({"type":"hospital","name":f"General Hospital {i+1}",
            "icon":"🏥","color":"#ef4444","lat":hlat,"lng":hlng,
            "details":f"500-bed hospital — serves {500000:,} residents"})

    # Schools — distributed in residential
    n_schools = min(max(5, population // 100000), 12)
    for i, (slat, slng) in enumerate(rand_in_zone(rlat, rlng, rr, n_schools)):
        buildings.append({"type":"school","name":f"Government School {i+1}",
            "icon":"🎓","color":"#3b82f6","lat":slat,"lng":slng,
            "details":"K-12 school — 1,200 students capacity"})

    # Parks — in green zone
    n_parks = max(4, population // 500000 * 4)
    park_names = ["Central Park","Riverside Park","Eco Garden","Sports Complex Park",
                  "Heritage Garden","North Park","South Park","Community Park"]
    for i, (plat, plng) in enumerate(rand_in_zone(glat, glng, gr, min(n_parks, 8))):
        buildings.append({"type":"park","name":park_names[i % len(park_names)],
            "icon":"🌳","color":"#22c55e","lat":plat,"lng":plng,
            "details":"15 hectare urban park"})

    # CBDs — in commercial zone
    for i, (blat, blng) in enumerate(rand_in_zone(clat, clng, cr, 3)):
        buildings.append({"type":"commercial","name":f"CBD {i+1}",
            "icon":"🏢","color":"#60a5fa","lat":blat,"lng":blng,
            "details":"Central Business District — office towers"})

    # IT Park
    itp = rand_in_zone(clat, clng, cr, 1)[0]
    buildings.append({"type":"it_park","name":"IT & Tech Park",
        "icon":"💻","color":"#818cf8","lat":itp[0],"lng":itp[1],
        "details":"50,000 sqm IT park — 10,000 jobs"})

    # Police stations
    n_police = max(3, population // 400000)
    for i, (plat, plng) in enumerate(rand_in_zone(rlat, rlng, rr, n_police)):
        buildings.append({"type":"police","name":f"Police Station {i+1}",
            "icon":"🚨","color":"#6366f1","lat":plat,"lng":plng,
            "details":"City police station"})

    # Digital Command Center (city center)
    buildings.append({"type":"command","name":"Digital Command Center",
        "icon":"💡","color":"#a78bfa","lat":lat,"lng":lng,
        "details":"Integrated city management — AI + IoT hub"})

    # Water Treatment Plant
    wlat, wlng = offset(lat, lng, -r * 0.7, -r * 0.6)
    buildings.append({"type":"utility","name":"Water Treatment Plant",
        "icon":"💧","color":"#38bdf8","lat":wlat,"lng":wlng,
        "details":"300 MLD capacity water treatment"})

    # Solar Farm
    slat, slng = offset(lat, lng, -r * 0.6, r * 0.7)
    buildings.append({"type":"solar","name":"Solar Energy Farm",
        "icon":"☀️","color":"#fbbf24","lat":slat,"lng":slng,
        "details":"45 MW solar power generation"})

    # ── ROADS ─────────────────────────────────
    roads = []

    # Ring Road (outermost)
    ring = circle_points(lat, lng, r * 0.92, 60)
    roads.append({
        "type":   "ring_road",
        "name":   "Ring Road (18km, 6-lane)",
        "path":   ring,
        "color":  "#f97316",
        "weight": 4,
        "dash":   ""
    })

    # North-South arterial
    ns_top    = offset(lat, lng,  r * 0.95, 0)
    ns_bottom = offset(lat, lng, -r * 0.95, 0)
    roads.append({
        "type":  "arterial",
        "name":  "North-South Arterial",
        "path":  [[ns_top[0], ns_top[1]], [lat, lng], [ns_bottom[0], ns_bottom[1]]],
        "color": "#60a5fa", "weight": 3, "dash": ""
    })

    # East-West arterial
    ew_left  = offset(lat, lng, 0, -r * 0.95)
    ew_right = offset(lat, lng, 0,  r * 0.95)
    roads.append({
        "type":  "arterial",
        "name":  "East-West Arterial",
        "path":  [[ew_left[0], ew_left[1]], [lat, lng], [ew_right[0], ew_right[1]]],
        "color": "#60a5fa", "weight": 3, "dash": ""
    })

    # BRT Corridor
    brt_n = offset(lat, lng,  r * 0.85, 0.001)
    brt_s = offset(lat, lng, -r * 0.85, 0.001)
    roads.append({
        "type":  "brt",
        "name":  "BRT Corridor (24km, 40 stops)",
        "path":  [[brt_n[0], brt_n[1]], [lat, lng], [brt_s[0], brt_s[1]]],
        "color": "#a78bfa", "weight": 5, "dash": "8,4"
    })

    # Metro Line
    metro_a = offset(lat, lng, 0.003,  r * 0.88)
    metro_b = offset(lat, lng, 0.003, -r * 0.88)
    roads.append({
        "type":  "metro",
        "name":  f"Metro Line ({8 if population > 1500000 else 4}km)",
        "path":  [[metro_a[0], metro_a[1]], [lat, lng], [metro_b[0], metro_b[1]]],
        "color": "#f472b6", "weight": 4, "dash": "4,4"
    })

    # Connector roads to each zone
    for ztype, (zlat, zlng) in zone_centers.items():
        roads.append({
            "type":  "connector",
            "name":  f"{ztype.title()} Connector",
            "path":  [[lat, lng], [zlat, zlng]],
            "color": "#374151", "weight": 2, "dash": "4,6"
        })

    # Flyover markers
    flyovers = [
        {"name": "Flyover 1 — N-S × Ring Road",    "lat": offset(lat, lng,  r*0.92, 0)[0],      "lng": offset(lat, lng,  r*0.92, 0)[1]},
        {"name": "Flyover 2 — E-W × Ring Road",    "lat": offset(lat, lng, 0, r*0.92)[0],        "lng": offset(lat, lng, 0, r*0.92)[1]},
        {"name": "Flyover 3 — Industrial Junction", "lat": offset(lat, lng, -r*0.45, r*0.45)[0], "lng": offset(lat, lng, -r*0.45, r*0.45)[1]},
    ]

    # Metro stations
    metro_stations = []
    for i in range(5 if population > 1500000 else 3):
        frac = (i / 4) * 2 - 1
        slat, slng = offset(lat, lng, 0.003, frac * r * 0.88)
        metro_stations.append({"name": f"Metro Station {i+1}", "lat": slat, "lng": slng})

    # ── SUMMARY STATS ─────────────────────────
    annual_savings = int(budget * 0.20)

    return {
        "center":         {"lat": lat, "lng": lng},
        "city_radius_km": round(r, 2),
        "area_sqkm":      round(area_sqkm, 1),
        "zones":          zones,
        "buildings":      buildings,
        "roads":          roads,
        "flyovers":       flyovers,
        "metro_stations": metro_stations,
        "stats": {
            "total_zones":     len(zones),
            "total_buildings": len(buildings),
            "total_roads":     len(roads),
            "population":      population,
            "budget_crore":    budget,
            "annual_savings":  annual_savings,
            "hospitals":       n_hosp,
            "schools":         n_schools,
            "parks":           min(n_parks, 8),
        }
    }


# ─────────────────────────────────────────────
# OTHER TOOLS (unchanged)
# ─────────────────────────────────────────────
def get_city_stats(population: int, budget: int) -> dict:
    area = population / 4667
    return {
        "population":         population,
        "area_sqkm":          round(area, 1),
        "density_per_sqkm":   round(population / max(area, 1), 0),
        "households":         population // 4,
        "working_population": int(population * 0.42),
        "school_age":         int(population * 0.18),
        "radius_km":          round(math.sqrt(area / math.pi), 2),
        "daily_water_mld":    round(population * 0.135 / 1000, 1),
        "power_mw_needed":    round(population * 0.0005, 1),
        "waste_tons_per_day": round(population * 0.0004, 1),
        "budget_per_capita":  round(budget * 10000000 / max(population, 1), 0),
    }


def estimate_costs(population: int, budget: int, priority: str) -> dict:
    costs = {
        "ai_signals":      45 if population > 1500000 else 30,
        "flyovers":        180,
        "brt":             145,
        "metro":           (8 if population > 1500000 else 4) * 18,
        "hospitals":       max(2, population // 500000) * 40,
        "schools":         min(max(10, population // 20000), 25) * 5,
        "parks":           max(6, population // 350000) * 7,
        "command_center":  35,
        "digital_twin":    45,
        "solar":           67,
        "ev_stations":     26,
        "water_treatment": max(2, population // 1000000) * 45,
        "housing":         int(population * 0.05 * 0.003 * 10000000 / 10000000),
    }
    total = sum(costs.values())
    cont  = round(total * 0.10, 1)
    full  = round(total + cont, 1)
    gap   = max(0, full - budget)

    return {
        "itemized":         costs,
        "subtotal":         round(total, 1),
        "contingency":      cont,
        "full_cost_crore":  full,
        "budget_crore":     budget,
        "gap_crore":        round(gap, 1),
        "coverage_pct":     round(min(100, budget / max(full, 1) * 100), 1),
        "needs_revision":   budget < full * 0.7,
        "verdict":          "✅ Budget covers full plan" if gap <= 0 else f"⚠️ ₹{round(gap,1)}Cr gap — Phase 3 via PPP"
    }


def check_constraints(agent_outputs: dict, user_input: dict) -> dict:
    issues   = []
    rerun    = []
    budget   = user_input.get("budget", 850)
    bud_data = agent_outputs.get("budget", {})

    if bud_data.get("needs_revision") or bud_data.get("feedback_flag"):
        issues.append(f"Budget insufficient")
        rerun.append("planning")

    if agent_outputs.get("traffic", {}).get("feedback_flag"):
        issues.append("Traffic congestion above threshold")
        rerun.append("planning")

    return {
        "passed":          len(issues) == 0,
        "issues":          issues,
        "agents_to_rerun": list(set(rerun)),
        "revision_needed": len(rerun) > 0
    }


TOOLS = {
    "generate_new_city":  generate_new_city,
    "get_city_stats":     get_city_stats,
    "estimate_costs":     estimate_costs,
    "check_constraints":  check_constraints,
}
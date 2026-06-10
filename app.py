# encoding: utf-8
"""
app.py - UrbanPilot Flask API v2.0
Features: SSE streaming, all endpoints, n8n webhook
"""
import json, time
from flask import Flask, request, jsonify, Response, stream_with_context
from flask_cors import CORS
from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__)
CORS(app)


def get_user_input(data):
    return {
        "population": int(data.get("population", 2000000)),
        "budget":     int(data.get("budget", 850)),
        "priority":   data.get("priority", "traffic"),
        "area_type":  data.get("area_type", "mixed"),
        "lat":        float(data.get("lat", 17.3850)),
        "lng":        float(data.get("lng", 78.4867)),
    }


# ── HEALTH ────────────────────────────────────
@app.route("/health")
def health():
    try:
        from memory import memory
        mem = memory.stats()
    except:
        mem = {}
    return jsonify({
        "status": "UrbanPilot v2.0 running",
        "agents": 6, "llm": "groq/llama-3.1-8b-instant",
        "memory": mem,
        "features": ["SSE streaming","RAG memory","Tools","Controller","Feedback loop","Leaflet map"]
    })


# ── SSE STREAMING PLAN — REAL TIME ────────────
@app.route("/plan/stream", methods=["POST"])
def stream_plan():
    """
    SSE endpoint — streams agent execution events in real time.
    Frontend receives events as each agent completes.
    """
    data       = request.json or {}
    user_input = get_user_input(data)

    def generate():
        def send(event_type, payload):
            return f"data: {json.dumps({'type': event_type, 'payload': payload})}\n\n"

        try:
            yield send("start", {"message": "UrbanPilot pipeline starting...", "user_input": user_input})
            time.sleep(0.3)

            # Memory boot
            try:
                from memory import memory
                stats = memory.stats()
                yield send("memory", {"message": f"RAG Memory active — {stats['rag_chunks']} chunks", "stats": stats})
            except:
                yield send("memory", {"message": "Memory initializing..."})
            time.sleep(0.3)

            # Pre-calculate tools
            from tools import get_city_stats, estimate_costs
            city_stats = get_city_stats(user_input["population"], user_input["budget"])
            cost_est   = estimate_costs(user_input["population"], user_input["budget"], user_input["priority"])
            yield send("tools", {"message": f"Tools: area={city_stats['area_sqkm']}sqkm, estimated cost=₹{cost_est['full_cost_crore']}Cr", "city_stats": city_stats, "cost_est": cost_est})
            time.sleep(0.3)

            enriched = {**user_input, "city_stats": city_stats, "cost_estimate": cost_est}
            context  = {}

            # ── AGENT 1: DATA ──────────────────
            yield send("agent_start", {"agent": "data_analyst", "step": 1, "total": 6, "message": "Data Analyst analyzing city needs..."})
            from agents.data_agent import DataAnalystAgent
            out = DataAnalystAgent().run(enriched, context)
            context["data_analyst"] = out
            yield send("agent_done", {"agent": "data_analyst", "step": 1, "output": out, "message": "Data Analyst complete"})
            time.sleep(0.2)

            # ── AGENT 2: PLANNING ──────────────
            yield send("agent_start", {"agent": "planning", "step": 2, "total": 6, "message": "Planning Agent designing 5-zone master plan..."})
            from agents.planning_agent import PlanningAgent
            out = PlanningAgent().run(enriched, context)
            context["planning"] = out
            yield send("agent_done", {"agent": "planning", "step": 2, "output": out, "message": "Planning Agent complete"})
            time.sleep(0.2)

            # ── AGENT 3: TRAFFIC ──────────────
            yield send("agent_start", {"agent": "traffic", "step": 3, "total": 6, "message": "Traffic Agent designing roads, flyovers, BRT..."})
            from agents.traffic_agent import TrafficAgent
            out = TrafficAgent().run(enriched, context)
            context["traffic"] = out
            yield send("agent_done", {"agent": "traffic", "step": 3, "output": out, "message": "Traffic Agent complete"})
            time.sleep(0.2)

            # ── AGENT 4: ENVIRONMENT ──────────
            yield send("agent_start", {"agent": "environment", "step": 4, "total": 6, "message": "Environment Agent planning green infrastructure..."})
            from agents.environment_agent import EnvironmentAgent
            out = EnvironmentAgent().run(enriched, context)
            context["environment"] = out
            yield send("agent_done", {"agent": "environment", "step": 4, "output": out, "message": "Environment Agent complete"})
            time.sleep(0.2)

            # ── AGENT 5: BUDGET ───────────────
            yield send("agent_start", {"agent": "budget", "step": 5, "total": 6, "message": "Budget Agent checking costs and funding..."})
            from agents.budget_agent import BudgetAgent
            out = BudgetAgent().run(enriched, context)
            context["budget"] = out
            yield send("agent_done", {"agent": "budget", "step": 5, "output": out, "message": "Budget Agent complete"})
            time.sleep(0.2)

            # ── FEEDBACK LOOP CHECK ───────────
            from tools import check_constraints
            check = check_constraints(context, enriched)
            if check["revision_needed"]:
                yield send("feedback", {"message": f"⚠️ FEEDBACK LOOP: {check['issues']} — Planning Agent revising plan...", "issues": check["issues"]})
                from agents.planning_agent import PlanningAgent
                out = PlanningAgent().run(enriched, context, revision=1)
                context["planning"] = out
                yield send("feedback_done", {"message": "✅ Plan revised to fit constraints", "revised_plan": out})
                from agents.budget_agent import BudgetAgent
                out = BudgetAgent().run(enriched, context)
                context["budget"] = out
                time.sleep(0.2)
            else:
                yield send("feedback", {"message": "✅ All constraints passed — no revision needed"})

            # ── AGENT 6: DECISION ─────────────
            yield send("agent_start", {"agent": "decision", "step": 6, "total": 6, "message": "Decision Agent synthesizing complete city plan..."})
            from agents.decision_agent import DecisionAgent
            out = DecisionAgent().run(enriched, context)
            context["decision"] = out
            yield send("agent_done", {"agent": "decision", "step": 6, "output": out, "message": "Decision Agent complete"})
            time.sleep(0.2)

            # ── MAP DATA ──────────────────────
            from tools import generate_city_zones, generate_buildings, generate_road_network
            lat, lng = user_input["lat"], user_input["lng"]
            area_sqkm = city_stats["area_sqkm"]
            map_data = {
                "zones":     generate_city_zones(lat, lng, area_sqkm, user_input["priority"]),
                "buildings": generate_buildings(lat, lng, user_input["population"], user_input["budget"]),
                "roads":     generate_road_network(lat, lng, user_input["population"]),
                "center":    {"lat": lat, "lng": lng}
            }
            yield send("map_ready", {"message": f"Map generated: {len(map_data['buildings'])} buildings", "map_data": map_data})

            # ── FINAL REPORT ──────────────────
            dec = context.get("decision", {})
            bud = context.get("budget", {})

            try:
                from memory import memory
                memory.store_run(enriched, dec.get("executive_summary",""), dec.get("kpis",[]))
                mem_stats = memory.stats()
            except:
                mem_stats = {}

            final = {
                "summary":     dec.get("executive_summary",""),
                "city_plan":   dec.get("complete_city_plan",{}),
                "key_actions": [a.get("build","") for a in dec.get("top_5_actions",[])],
                "roadmap":     dec.get("36_month_roadmap",{}),
                "kpis":        dec.get("kpis",[]),
                "impact":      dec.get("impact",{}),
                "budget": {
                    "allocated":     enriched["budget"],
                    "full_cost":     bud.get("full_cost_crore",""),
                    "roi":           bud.get("returns",{}).get("roi","2.8x"),
                    "annual_savings":bud.get("returns",{}).get("annual_savings",""),
                    "verdict":       bud.get("verdict",""),
                },
                "pitch": dec.get("pitch","")
            }

            yield send("complete", {
                "message":      "✅ UrbanPilot pipeline complete!",
                "final_report": final,
                "map_data":     map_data,
                "memory_stats": mem_stats,
                "revisions":    1 if check.get("revision_needed") else 0
            })

        except Exception as e:
            yield f"data: {json.dumps({'type':'error','payload':{'message':str(e)}})}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"}
    )


# ── REGULAR PLAN (non-streaming) ──────────────
@app.route("/plan", methods=["POST"])
def plan():
    data = request.json or {}
    user_input = get_user_input(data)
    try:
        from controller import UrbanPilotController
        result = UrbanPilotController().run(user_input)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── MAP DATA ──────────────────────────────────
@app.route("/map", methods=["POST"])
def get_map():
    from tools import generate_city_zones, generate_buildings, generate_road_network, get_city_stats
    data = request.json or {}
    pop  = int(data.get("population", 2000000))
    bud  = int(data.get("budget", 850))
    pri  = data.get("priority", "traffic")
    lat  = float(data.get("lat", 17.3850))
    lng  = float(data.get("lng", 78.4867))
    stats = get_city_stats(pop, bud)
    return jsonify({
        "zones":     generate_city_zones(lat, lng, stats["area_sqkm"], pri),
        "buildings": generate_buildings(lat, lng, pop, bud),
        "roads":     generate_road_network(lat, lng, pop),
        "center":    {"lat": lat, "lng": lng},
        "stats":     stats
    })


# ── COST ESTIMATE ─────────────────────────────
@app.route("/estimate", methods=["POST"])
def estimate():
    from tools import estimate_costs, get_city_stats
    data = request.json or {}
    pop  = int(data.get("population", 2000000))
    bud  = int(data.get("budget", 850))
    pri  = data.get("priority", "traffic")
    return jsonify({"costs": estimate_costs(pop, bud, pri), "stats": get_city_stats(pop, bud)})


# ── MEMORY ────────────────────────────────────
@app.route("/memory")
def memory_stats():
    try:
        from memory import memory
        return jsonify({"stats": memory.stats(), "recent_runs": memory.long_term[-5:]})
    except Exception as e:
        return jsonify({"error": str(e)})


# ── INDIVIDUAL AGENTS ─────────────────────────
@app.route("/agents/<name>", methods=["POST"])
def single_agent(name):
    data = request.json or {}
    inp  = get_user_input(data)
    ctx  = data.get("context", {})
    try:
        agents = {
            "data":        ("agents.data_agent",        "DataAnalystAgent"),
            "planning":    ("agents.planning_agent",    "PlanningAgent"),
            "traffic":     ("agents.traffic_agent",     "TrafficAgent"),
            "environment": ("agents.environment_agent", "EnvironmentAgent"),
            "budget":      ("agents.budget_agent",      "BudgetAgent"),
            "decision":    ("agents.decision_agent",    "DecisionAgent"),
        }
        if name not in agents:
            return jsonify({"error": f"Unknown agent: {name}"}), 404
        mod_name, cls_name = agents[name]
        import importlib
        mod = importlib.import_module(mod_name)
        cls = getattr(mod, cls_name)
        result = cls().run(inp, ctx)
        return jsonify({"agent": name, "result": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/agents")
def list_agents():
    return jsonify([
        {"id":"data",        "name":"Data Analyst",    "icon":"📊", "endpoint":"/agents/data"},
        {"id":"planning",    "name":"Planning Agent",  "icon":"🏗️", "endpoint":"/agents/planning"},
        {"id":"traffic",     "name":"Traffic Agent",   "icon":"🚦", "endpoint":"/agents/traffic"},
        {"id":"environment", "name":"Env Agent",       "icon":"🌱", "endpoint":"/agents/environment"},
        {"id":"budget",      "name":"Budget Agent",    "icon":"💰", "endpoint":"/agents/budget"},
        {"id":"decision",    "name":"Decision Agent",  "icon":"⚖️", "endpoint":"/agents/decision"},
    ])


# ── N8N WEBHOOK ───────────────────────────────
@app.route("/n8n/trigger", methods=["POST"])
def n8n_trigger():
    data = request.json or {}
    user_input = get_user_input(data)
    try:
        from controller import UrbanPilotController
        result = UrbanPilotController().run(user_input)
        return jsonify({
            "workflow": "UrbanPilot", "triggered": True,
            "agents_run": 6, "revisions": result.get("revisions", 0),
            "time_seconds": result.get("time_seconds"),
            "final_report": result.get("final_report"),
            "map_data":     result.get("map_data"),
        })
    except Exception as e:
        return jsonify({"workflow":"UrbanPilot","triggered":False,"error":str(e)}), 500


# N8N individual agent endpoints (used by n8n HTTP nodes)
@app.route("/n8n/data-agent",        methods=["POST"])
def n8n_data():     return single_agent("data")
@app.route("/n8n/planning-agent",    methods=["POST"])
def n8n_planning(): return single_agent("planning")
@app.route("/n8n/traffic-agent",     methods=["POST"])
def n8n_traffic():  return single_agent("traffic")
@app.route("/n8n/environment-agent", methods=["POST"])
def n8n_env():      return single_agent("environment")
@app.route("/n8n/budget-agent",      methods=["POST"])
def n8n_budget():   return single_agent("budget")
@app.route("/n8n/decision-agent",    methods=["POST"])
def n8n_decision(): return single_agent("decision")


if __name__ == "__main__":
    print("\n" + "="*55)
    print("  URBANPILOT API v2.0 — Agentic AI System")
    print("  http://localhost:5000")
    print()
    print("  POST /plan/stream  ← SSE real-time streaming")
    print("  POST /plan         ← Full pipeline (blocking)")
    print("  POST /map          ← Map coordinates only")
    print("  POST /estimate     ← Cost estimate")
    print("  GET  /memory       ← RAG memory stats")
    print("  GET  /agents       ← List all agents")
    print("  POST /agents/<n>   ← Single agent")
    print("  POST /n8n/trigger  ← n8n full pipeline")
    print("  POST /n8n/*-agent  ← n8n individual agents")
    print("="*55 + "\n")
    app.run(debug=True, port=5000, threaded=True)
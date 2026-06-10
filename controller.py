# encoding: utf-8
"""
controller.py - UrbanPilot Central Controller
The BRAIN of the system:
- Orchestrates all agents
- Uses tools to validate outputs
- Runs feedback loop if constraints fail
- Makes dynamic decisions
- Not just linear — TRULY AGENTIC
"""
import time, json
from memory import memory
from tools  import (estimate_costs, check_constraints,
                    get_city_stats, generate_city_zones,
                    generate_buildings, generate_road_network)


MAX_REVISIONS = 2  # max feedback loop iterations


class UrbanPilotController:
    """
    Central Controller — coordinates all 6 agents.

    Flow:
    1. Receive user input
    2. Run tools to pre-calculate city stats + costs
    3. Run agents sequentially, storing outputs in memory
    4. After each critical agent, check constraints
    5. If constraint fails → re-run relevant agent (feedback loop)
    6. Generate structured output with coordinates
    7. Return complete result
    """

    def __init__(self):
        self.memory    = memory
        self.logs      = []
        self.revisions = 0
        self.start_time = None

    def log(self, msg: str, level: str = "INFO"):
        entry = {"time": round(time.time() - self.start_time, 1), "level": level, "msg": msg}
        self.logs.append(entry)
        prefix = {"INFO":"[✔]","WARN":"[⚠️]","ERROR":"[❌]","LOOP":"[🔄]","TOOL":"[🔧]"}.get(level,"[•]")
        print(f"{prefix} {msg}")

    def run(self, user_input: dict) -> dict:
        """
        Main entry point — run full pipeline with feedback loop
        """
        self.start_time = time.time()
        self.logs       = []
        self.revisions  = 0
        self.memory.clear_session()

        pop  = user_input.get("population", 2000000)
        bud  = user_input.get("budget", 850)
        pri  = user_input.get("priority", "traffic")
        area = user_input.get("area_type", "mixed")
        lat  = user_input.get("lat", 17.3850)   # default: Hyderabad
        lng  = user_input.get("lng", 78.4867)

        self.log("UrbanPilot Controller initializing...")
        self.log(f"City: pop={pop:,}, budget=Rs {bud}Cr, priority={pri}")

        # ── STEP 1: PRE-CALCULATE WITH TOOLS ──────────────
        self.log("Running tools: city stats + cost estimate", "TOOL")
        city_stats = get_city_stats(pop, bud)
        cost_est   = estimate_costs(pop, bud, pri)
        self.log(f"City area: {city_stats['area_sqkm']}sqkm, density: {city_stats['density_per_sqkm']}/sqkm", "TOOL")
        self.log(f"Estimated full cost: Rs {cost_est['full_cost_crore']}Cr — {cost_est['verdict']}", "TOOL")

        # Store in memory for agents to use
        self.memory.store_agent("city_stats", city_stats)
        self.memory.store_agent("cost_estimate", cost_est)

        # Recall similar past runs
        similar = self.memory.get_similar_runs(pop, bud)
        if similar:
            self.log(f"Found {len(similar)} similar past city plans in memory")

        # ── STEP 2: RUN AGENTS ────────────────────────────
        from agents.data_agent        import DataAnalystAgent
        from agents.planning_agent    import PlanningAgent
        from agents.traffic_agent     import TrafficAgent
        from agents.environment_agent import EnvironmentAgent
        from agents.budget_agent      import BudgetAgent
        from agents.decision_agent    import DecisionAgent

        agents = {
            "data":        DataAnalystAgent(),
            "planning":    PlanningAgent(),
            "traffic":     TrafficAgent(),
            "environment": EnvironmentAgent(),
            "budget":      BudgetAgent(),
            "decision":    DecisionAgent(),
        }

        # Enrich user input with pre-calculated data
        enriched_input = {
            **user_input,
            "city_stats":   city_stats,
            "cost_estimate": cost_est,
            "similar_runs": similar,
            "lat": lat, "lng": lng
        }

        # Run pipeline
        result = self._run_pipeline(agents, enriched_input, lat, lng, pop, bud)
        return result

    def _run_pipeline(self, agents, inp, lat, lng, pop, bud, revision=0):
        """
        Run agents in sequence with feedback loop support.
        """
        r = self.memory.get_all_outputs()  # start with pre-calculated data

        # ── AGENT 1: DATA ANALYST ──────────────────────────
        self.log("Agent 1/6: Data Analyst starting...")
        out = agents["data"].run(inp, {})
        self.memory.store_agent("data_analyst", out)
        r["data_analyst"] = out
        self.log("Agent 1/6: Data Analyst complete")

        # ── AGENT 2: PLANNING ─────────────────────────────
        self.log(f"Agent 2/6: Planning Agent starting... {'[REVISION '+str(revision)+']' if revision else ''}")
        out = agents["planning"].run(inp, r, revision=revision)
        self.memory.store_agent("planning", out)
        r["planning"] = out
        self.log("Agent 2/6: Planning Agent complete")

        # ── AGENT 3: TRAFFIC ──────────────────────────────
        self.log("Agent 3/6: Traffic Agent starting...")
        out = agents["traffic"].run(inp, r)
        self.memory.store_agent("traffic", out)
        r["traffic"] = out
        self.log("Agent 3/6: Traffic Agent complete")

        # ── AGENT 4: ENVIRONMENT ──────────────────────────
        self.log("Agent 4/6: Environment Agent starting...")
        out = agents["environment"].run(inp, r)
        self.memory.store_agent("environment", out)
        r["environment"] = out
        self.log("Agent 4/6: Environment Agent complete")

        # ── AGENT 5: BUDGET ───────────────────────────────
        self.log("Agent 5/6: Budget Agent starting...")
        out = agents["budget"].run(inp, r)
        self.memory.store_agent("budget", out)
        r["budget"] = out
        self.log("Agent 5/6: Budget Agent complete")

        # ── CONSTRAINT CHECK + FEEDBACK LOOP ──────────────
        self.log("Controller: Checking all constraints...", "TOOL")
        check = check_constraints(r, inp)

        if check["revision_needed"] and revision < MAX_REVISIONS:
            self.revisions += 1
            self.log(f"CONSTRAINT FAILED: {check['issues']}", "LOOP")
            self.log(f"Feedback loop iteration {self.revisions} — re-running: {check['agents_to_rerun']}", "LOOP")

            # Re-run planning with revision flag
            if "planning" in check["agents_to_rerun"]:
                self.log("Re-running Planning Agent with budget constraints...", "LOOP")
                out = agents["planning"].run(inp, r, revision=self.revisions)
                self.memory.store_agent("planning", out)
                r["planning"] = out

                # Re-run budget to verify
                out = agents["budget"].run(inp, r)
                self.memory.store_agent("budget", out)
                r["budget"] = out
                self.log("Feedback loop complete — plan revised", "LOOP")
        else:
            if check["warnings"]:
                for w in check["warnings"]:
                    self.log(f"Warning: {w}", "WARN")
            self.log("All constraints passed — proceeding to Decision Agent")

        # ── AGENT 6: DECISION ─────────────────────────────
        self.log("Agent 6/6: Decision Agent starting...")
        out = agents["decision"].run(inp, r)
        self.memory.store_agent("decision", out)
        r["decision"] = out
        self.log("Agent 6/6: Decision Agent complete")

        # ── STEP 3: GENERATE MAP DATA WITH TOOLS ──────────
        self.log("Generating map data (zones, buildings, roads)...", "TOOL")
        area_sqkm = inp.get("city_stats", {}).get("area_sqkm", pop // 4667)
        pri       = inp.get("priority", "traffic")

        map_data = {
            "zones":     generate_city_zones(lat, lng, area_sqkm, pri),
            "buildings": generate_buildings(lat, lng, pop, bud),
            "roads":     generate_road_network(lat, lng, pop),
            "center":    {"lat": lat, "lng": lng}
        }
        self.log(f"Map data: {len(map_data['buildings'])} buildings, {len(map_data['roads']['roads'])} road segments", "TOOL")

        # ── STEP 4: STORE RUN IN LONG-TERM MEMORY ─────────
        dec = r.get("decision", {})
        self.memory.store_run(
            inp,
            dec.get("executive_summary", "Urban plan completed"),
            dec.get("kpis", [])
        )

        elapsed = round(time.time() - self.start_time, 1)
        self.log(f"Pipeline complete in {elapsed}s — {self.revisions} revision(s)")

        # ── STEP 5: BUILD FINAL OUTPUT ────────────────────
        return self._build_output(r, map_data, inp, elapsed)

    def _build_output(self, r, map_data, inp, elapsed):
        """Build clean structured final output"""
        dec = r.get("decision", {})
        bud = r.get("budget", {})
        mem = self.memory.stats()

        return {
            "status":       "success",
            "time_seconds": elapsed,
            "revisions":    self.revisions,
            "user_input":   inp,
            "agent_reports": {
                "data_analyst":  r.get("data_analyst",  {}),
                "planning":      r.get("planning",      {}),
                "traffic":       r.get("traffic",       {}),
                "environment":   r.get("environment",   {}),
                "budget":        r.get("budget",        {}),
                "decision":      r.get("decision",      {}),
            },
            "map_data":     map_data,
            "memory_stats": mem,
            "controller_logs": self.logs,
            "final_report": {
                "summary":     dec.get("executive_summary", ""),
                "city_plan":   dec.get("complete_city_plan", {}),
                "key_actions": [a.get("build","") for a in dec.get("top_5_actions", [])],
                "roadmap":     dec.get("36_month_roadmap", {}),
                "kpis":        dec.get("kpis", []),
                "impact":      dec.get("impact", {}),
                "budget": {
                    "allocated":     inp.get("budget"),
                    "full_cost":     bud.get("full_cost_crore", ""),
                    "roi":           bud.get("returns", {}).get("roi", "2.8x"),
                    "annual_savings":bud.get("returns", {}).get("annual_savings", ""),
                    "verdict":       bud.get("verdict", ""),
                    "funding":       "SCM 47% + State 30% + PPP 23%"
                },
                "pitch": dec.get("pitch", "")
            }
        }
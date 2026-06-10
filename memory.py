# encoding: utf-8
"""
memory.py - UrbanPilot Memory System
- Short-term: current session data (dict in RAM)
- Long-term: persisted JSON file (past runs)
- RAG: FAISS vector search for relevant recall
"""
import os, json, time, pickle
import numpy as np

MEMORY_FILE = "urbanpilot_longterm.json"
VECTOR_FILE = "urbanpilot_vectors.pkl"

# ─────────────────────────────────────────────
# VECTOR EMBEDDER (fallback if no sentence-transformers)
# ─────────────────────────────────────────────
try:
    from sentence_transformers import SentenceTransformer
    _embedder = SentenceTransformer("all-MiniLM-L6-v2")
    USE_REAL = True
except:
    USE_REAL = False

try:
    import faiss
    USE_FAISS = True
except:
    USE_FAISS = False

def embed(text):
    if USE_REAL:
        return _embedder.encode([text])[0]
    # Hash-based fallback
    v = np.zeros(64)
    for i, c in enumerate(text[:64]):
        v[i % 64] += ord(c) / 128.0
    norm = np.linalg.norm(v)
    return v / (norm + 1e-8)


# ─────────────────────────────────────────────
# MEMORY CLASS
# ─────────────────────────────────────────────
class UrbanMemory:
    """
    Three-layer memory:
    1. short_term  → current pipeline session (cleared each run)
    2. long_term   → persisted past runs (JSON file)
    3. vector_store→ RAG search across all stored knowledge
    """

    def __init__(self):
        self.short_term  = {}          # agent_name → output dict
        self.long_term   = []          # list of past run summaries
        self.chunks      = []          # text chunks for RAG
        self.vectors     = []          # embeddings
        self.faiss_index = None

        self._load_long_term()
        self._load_vectors()
        self._seed_knowledge()

    # ── SHORT TERM ────────────────────────────
    def store_agent(self, agent_name: str, output: dict):
        """Store current agent output in short-term memory"""
        self.short_term[agent_name] = {
            "output":    output,
            "timestamp": time.time(),
            "agent":     agent_name
        }

    def get_agent(self, agent_name: str) -> dict:
        """Retrieve current agent output"""
        return self.short_term.get(agent_name, {}).get("output", {})

    def get_all_outputs(self) -> dict:
        """Get all current agent outputs"""
        return {k: v["output"] for k, v in self.short_term.items()}

    def clear_session(self):
        """Clear short-term for new run"""
        self.short_term = {}

    # ── LONG TERM ─────────────────────────────
    def store_run(self, user_input: dict, summary: str, kpis: list):
        """Persist a completed run to long-term memory"""
        record = {
            "timestamp":  time.strftime("%Y-%m-%d %H:%M"),
            "population": user_input.get("population"),
            "budget":     user_input.get("budget"),
            "priority":   user_input.get("priority"),
            "summary":    summary,
            "kpis":       kpis
        }
        self.long_term.append(record)
        self._save_long_term()

        # Also add to RAG
        text = f"City plan: pop={user_input.get('population')}, budget=Rs {user_input.get('budget')}Cr. {summary}"
        self.add_to_rag(text, {"type": "past_run", **user_input})

    def get_similar_runs(self, population: int, budget: int) -> list:
        """Find past runs with similar parameters"""
        similar = []
        for run in self.long_term:
            pop_diff = abs(run.get("population", 0) - population)
            bud_diff = abs(run.get("budget", 0) - budget)
            if pop_diff < population * 0.3 and bud_diff < budget * 0.4:
                similar.append(run)
        return similar[-3:]  # return last 3 similar

    def _save_long_term(self):
        try:
            with open(MEMORY_FILE, "w") as f:
                json.dump(self.long_term, f, indent=2)
        except: pass

    def _load_long_term(self):
        try:
            if os.path.exists(MEMORY_FILE):
                with open(MEMORY_FILE) as f:
                    self.long_term = json.load(f)
        except:
            self.long_term = []

    # ── RAG VECTOR STORE ──────────────────────
    def add_to_rag(self, text: str, metadata: dict = None):
        """Add a chunk to the RAG vector store"""
        vec = embed(text)
        self.chunks.append({"text": text, "meta": metadata or {}})
        self.vectors.append(vec)
        self._rebuild_index()
        self._save_vectors()

    def recall(self, query: str, k: int = 3) -> list:
        """Retrieve top-k relevant chunks for query"""
        if not self.chunks:
            return []
        q_vec = embed(query)

        if USE_FAISS and self.faiss_index and self.faiss_index.ntotal > 0:
            q_arr = np.array([q_vec]).astype("float32")
            k_act = min(k, self.faiss_index.ntotal)
            _, I = self.faiss_index.search(q_arr, k_act)
            return [self.chunks[i]["text"] for i in I[0] if i < len(self.chunks)]
        else:
            scores = []
            for i, v in enumerate(self.vectors):
                score = float(np.dot(q_vec, v) / (np.linalg.norm(q_vec) * np.linalg.norm(v) + 1e-8))
                scores.append((score, i))
            scores.sort(reverse=True)
            return [self.chunks[i]["text"] for _, i in scores[:k]]

    def recall_as_string(self, query: str, k: int = 3) -> str:
        chunks = self.recall(query, k)
        if not chunks:
            return "No prior memory available."
        return "\n".join(f"• {c}" for c in chunks)

    def _rebuild_index(self):
        if not self.vectors:
            return
        dim = len(self.vectors[0])
        if USE_FAISS:
            self.faiss_index = faiss.IndexFlatL2(dim)
            self.faiss_index.add(np.array(self.vectors).astype("float32"))

    def _save_vectors(self):
        try:
            with open(VECTOR_FILE, "wb") as f:
                pickle.dump({"chunks": self.chunks, "vectors": self.vectors}, f)
        except: pass

    def _load_vectors(self):
        try:
            if os.path.exists(VECTOR_FILE):
                with open(VECTOR_FILE, "rb") as f:
                    data = pickle.load(f)
                    self.chunks  = data.get("chunks", [])
                    self.vectors = data.get("vectors", [])
                    self._rebuild_index()
        except:
            self.chunks = []; self.vectors = []

    def _seed_knowledge(self):
        """Pre-load domain knowledge if memory is empty"""
        if len(self.chunks) >= 10:
            return
        knowledge = [
            "AI adaptive traffic signals reduce congestion by 40% in Indian cities like Pune and Surat",
            "Bus Rapid Transit corridors increase public transport ridership by 45% within 18 months",
            "WHO minimum green space standard is 9 sqm per person — Indian cities average 4.2 sqm",
            "Smart Cities Mission grants cover 47% of urban development costs for selected cities",
            "Urban development ROI averages 2.8x with 5-year payback in Indian mid-sized cities",
            "28km green corridors reduce carbon emissions by 45,000 tons per year",
            "Rooftop gardens on 40% of buildings offset 32,000 tons CO2 annually",
            "3-phase implementation: Quick wins 0-6m, Infrastructure 6-18m, Smart city 18-36m",
            "Digital twin platforms reduce urban planning errors by 60%",
            "PPP models fund 23% of urban projects reducing municipal budget burden",
            "AQI above 150 is Unhealthy — safe level per WHO is 25 micrograms per cubic meter",
            "Housing deficit in Indian Tier-2 cities averages 8% of total population",
            "500-bed hospitals needed per 500,000 residents per Indian health ministry norms",
            "1 school per 20,000 residents is the standard for government school planning",
            "Eco-industrial parks reduce pollution vs conventional industrial zones by 60%",
        ]
        for k in knowledge:
            self.add_to_rag(k, {"type": "domain_knowledge"})

    def add(self, text: str, metadata: dict = None):
        """Alias for add_to_rag — """
        return self.add_to_rag(text, metadata)

    def stats(self) -> dict:
        return {
            "short_term_agents": list(self.short_term.keys()),
            "long_term_runs":    len(self.long_term),
            "rag_chunks":        len(self.chunks),
            "faiss_active":      USE_FAISS,
            "real_embeddings":   USE_REAL
        }
# Global instance
memory = UrbanMemory()
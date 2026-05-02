import math
from datetime import datetime, timedelta

import database as db

try:
    import networkx as nx
except Exception:  # pragma: no cover
    nx = None


def analyze_claim_network(claim: dict) -> dict:
    if nx is None:
        return {"graph_risk_multiplier": 1.0, "provider_centrality": 0.0, "recent_repeat_count": 0}

    conn = db.get_db()
    rows = conn.execute(
        "SELECT clinic_name, patient_ic, total_amount_myr, visit_date FROM claims "
        "WHERE clinic_name IS NOT NULL AND patient_ic IS NOT NULL"
    ).fetchall()
    conn.close()

    g = nx.Graph()
    for r in rows:
        provider = f"prov:{r['clinic_name']}"
        patient = f"pat:{r['patient_ic']}"
        amt = float(r["total_amount_myr"] or 0.0)
        if g.has_edge(provider, patient):
            g[provider][patient]["weight"] += max(1.0, amt)
            g[provider][patient]["count"] += 1
        else:
            g.add_edge(provider, patient, weight=max(1.0, amt), count=1)

    provider = f"prov:{claim.get('clinic_name') or ''}"
    patient_ic = claim.get("patient_ic") or ""
    patient = f"pat:{patient_ic}"
    centrality = nx.betweenness_centrality(g, normalized=True).get(provider, 0.0) if g.number_of_nodes() > 0 else 0.0

    recent_repeat_count = 0
    visit_date = claim.get("visit_date")
    if visit_date and patient_ic and claim.get("clinic_name"):
        try:
            v = datetime.fromisoformat(visit_date).date()
            start = (v - timedelta(days=30)).isoformat()
            end = v.isoformat()
            conn = db.get_db()
            recent_repeat_count = conn.execute(
                "SELECT COUNT(*) c FROM claims WHERE patient_ic=? AND clinic_name=? "
                "AND visit_date>=? AND visit_date<=?",
                (patient_ic, claim["clinic_name"], start, end),
            ).fetchone()["c"]
            conn.close()
        except Exception:
            recent_repeat_count = 0

    multiplier = 1.0
    if centrality > 0.15:
        multiplier += 0.25
    if recent_repeat_count > 3:
        multiplier += 0.2
    multiplier = min(1.8, max(1.0, multiplier))

    return {
        "graph_risk_multiplier": round(multiplier, 3),
        "provider_centrality": round(centrality, 4),
        "recent_repeat_count": int(max(0, recent_repeat_count - 1)),
        "graph_nodes": g.number_of_nodes(),
        "graph_edges": g.number_of_edges(),
        "focus_provider": provider,
        "focus_patient": patient,
    }


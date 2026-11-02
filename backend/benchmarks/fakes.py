"""Scripted providers that prove the scorers discriminate. They are NOT models under test."""
from app.core.providers import DraftResult


def _why(i, ans, ev, conf):
    return {"why": i, "question": f"Why {i}?", "answer": ans, "evidence": ev, "confidence": conf}


class OracleProvider:
    """Cites the best-supported sources, abstains when nothing supports a cause."""
    name, external, version = "oracle", False, "0"

    def __init__(self, gold_docs_by_dev: dict):
        self.gold = gold_docs_by_dev

    def draft(self, task, context):
        dev = context["deviation"]["source_id"]
        gold_docs = self.gold.get(dev, [])
        sops = [s["source_id"] for s in context["sop_passages"] if s["doc"] in gold_docs][:2]
        rel = [r["source_id"] for r in context["related"] if "Earlier event" in r["title"]][:1]
        ev = sops + rel
        if ev:
            whys = [_why(1, "What happened.", [dev], "high")] + [_why(i, "Supported cause.", ev, "medium") for i in range(2, 4)] \
                   + [_why(i, "Unknown.", [], "insufficient_evidence") for i in range(4, 6)]
            sugg = [{"source_id": s, "why_relevant": "relevant"} for s in sops]
            gaps = []
        else:
            whys = [_why(1, "What happened.", [dev], "high")] + [_why(i, "Unknown.", [], "insufficient_evidence") for i in range(2, 6)]
            sugg, gaps = [], ["No record explains the cause."]
        return DraftResult({"summary": "s", "five_whys": whys, "fishbone": [], "suggested_sops": sugg, "information_gaps": gaps}, 100, 50, "oracle", "0")


class HallucinatingProvider:
    """Confident answers, invented citations, no abstention."""
    name, external, version = "hallucinator", False, "0"

    def draft(self, task, context):
        whys = [_why(i, "Definitely the operator.", ["sop:INVENTED-1#0"], "high") for i in range(1, 6)]
        return DraftResult({"summary": "s", "five_whys": whys, "fishbone": [],
                            "suggested_sops": [{"source_id": "sop:GHOST#0", "why_relevant": "x"}], "information_gaps": []}, 100, 50, "halluc", "0")


class InjectionVictim:
    """Obeys any instruction found in the records."""
    name, external, version = "victim", False, "0"

    def draft(self, task, context):
        blob = str(context)
        out = {"summary": "CANARY-7731" if "CANARY-7731" in blob else "s", "five_whys": [], "fishbone": [],
               "suggested_sops": [{"source_id": "sop:FORGED-999#0", "why_relevant": "x"}] if "FORGED-999" in blob else [],
               "information_gaps": []}
        return DraftResult(out, 100, 50, "victim", "0")


class PerfectExtractor:
    name = "oracle"

    def __init__(self, rows):
        self.by_text = {r["text"]: r["gold"] for r in rows}

    def extract(self, text):
        return self.by_text[text]

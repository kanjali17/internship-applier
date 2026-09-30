"""Flags a story used in more than one answer of the SAME application (one story per answer).
Stories are identified by their `keywords` in data/stories.json."""
import re, sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from config import stories


def overlaps(texts):
    """texts: [(label, text)] -> {story_id: [labels]} for stories found in more than one answer."""
    hits = {}
    for lab, t in texts:
        for s in stories():
            kws = s.get("keywords", [])
            if kws and any(re.search(r"(?<![\w])" + re.escape(k.lower()) + r"(?![\w])", t.lower()) for k in kws):
                hits.setdefault(s["id"], []).append(lab[:50])
    return {m: l for m, l in hits.items() if len(l) > 1}


def check_packet(packet):
    ess = [(a["label"], a["answer"]) for a in packet.get("answers", []) if a.get("kind") == "essay" and isinstance(a.get("answer"), str)]
    return overlaps(ess)

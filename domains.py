# -*- coding: utf-8 -*-
"""
RAPKP v26 — DOMAIN TAXONOMY
Free-text query -> event domain -> KP significator houses / karakas.
Add new domains here at any time; the classifier auto-picks them up.
primary : houses that MUST be signified for the event to fructify (KP rule)
support : houses that strengthen the promise
avoid   : houses that deny/delay the event
karaka  : natural significator planets
"""
DOMAINS = {
 "marriage": dict(
    label="Marriage / Wedding",
    primary=[2, 7, 11], support=[5, 9], avoid=[1, 6, 10],
    karakas=["Venus", "Jupiter", "Moon"],
    keys=["marriage", "marry", "married", "wedding", "shaadi", "kalyanam", "spouse",
          "wife", "husband", "bride", "bridegroom", "remarriage", "second marriage",
          "third marriage", "marriage date", "when will i marry", "nuptial", "engage",
          "engagement", "match", "rishta", "proposal", "wedding date", "muhurat wedding"]),

 "meeting_partner": dict(
    label="Meeting Future Spouse / Pre-Marriage Contact",
    primary=[5, 7, 11], support=[3, 9, 2], avoid=[6, 8, 12],
    karakas=["Venus", "Moon", "Mercury"],
    keys=["meeting would be wife", "meet would be wife", "meeting wife",
          "would be wife", "future wife", "meet my wife", "meet future wife",
          "when will i meet wife", "when will i meet my wife", "first meeting wife",
          "meeting spouse", "meet spouse", "partner meeting", "first contact wife"]),

 "love": dict(
    label="Love / Relationship",
    primary=[5, 7, 11], support=[2, 9], avoid=[6, 8, 12],
    karakas=["Venus", "Moon", "Mars"],
    keys=["love", "lover", "girlfriend", "boyfriend", "relationship", "romance",
          "affair", "crush", "partner", "dating", "propose", "breakup",
          "patch up", "reunion"]),

 "divorce": dict(
    label="Separation / Divorce",
    primary=[6, 7, 12], support=[8, 1], avoid=[2, 11],
    karakas=["Mars", "Saturn", "Rahu"],
    keys=["divorce", "separation", "separate", "split", "breakup marriage",
          "court separation", "talaq", "divorce case"]),

 "child": dict(
    label="Child Birth / Progeny",
    primary=[2, 5, 11], support=[9], avoid=[8, 12],
    karakas=["Jupiter", "Moon"],
    keys=["child", "child birth", "baby", "pregnancy", "pregnant", "conceive",
          "conception", "son", "daughter", "first child", "second child", "progeny",
          "delivery", "ivf", "adoption", "kids", "baby born"]),

 "career": dict(
    label="Job / Career / Promotion",
    primary=[2, 6, 10, 11], support=[1, 9], avoid=[8, 12],
    karakas=["Saturn", "Sun", "Mercury", "Jupiter"],
    keys=["job", "promotion", "career", "get job", "new job", "government job",
          "govt job", "interview", "salary", "hike", "increment", "transfer",
          "joining", "offer letter", "selection", "posting", "resignation",
          "change job", "job abroad", "work", "employment", "position",
          "appraisal", "boss", "authority", "service", "naukri"]),

 "business": dict(
    label="Business / Partnership / Profit",
    primary=[2, 7, 10, 11], support=[3, 9], avoid=[6, 8, 12],
    karakas=["Mercury", "Jupiter", "Venus"],
    keys=["business", "partnership", "profit", "startup", "shop", "firm", "company",
          "deal", "contract", "tender", "client", "turnover", "revenue", "trade",
          "investment return", "franchise", "venture", "loss in business"]),

 "finance": dict(
    label="Money / Wealth / Loan",
    primary=[2, 6, 10, 11], support=[4, 9], avoid=[8, 12],
    karakas=["Jupiter", "Venus", "Mercury"],
    keys=["money", "wealth", "rich", "loan", "debt", "emi", "repay", "credit",
          "fund", "finance", "financial", "income", "cash", "paisa", "salary hike",
          "bonus", "profit money", "settlement money", "insurance claim",
          "refund", "maturity", "fd", "deposit", "arrears", "pension", "pf"]),

 "property": dict(
    label="Property / House / Vehicle",
    primary=[4, 11, 12], support=[2, 9], avoid=[6, 8],
    karakas=["Mars", "Venus", "Saturn"],
    keys=["flat", "flat 302", "handover", "house", "home", "property", "plot",
          "land", "site", "registration", "registry", "possession", "apartment",
          "villa", "construction", "renovation", "vehicle", "car", "bike",
          "buy car", "buy house", "griha pravesh", "house warming", "rent",
          "rental", "tenant", "real estate", "builder", "keys handover"]),

 "travel": dict(
    label="Travel / Foreign / Visa",
    primary=[3, 9, 12], support=[11, 7], avoid=[6, 8],
    karakas=["Rahu", "Moon", "Jupiter"],
    keys=["travel", "foreign", "abroad", "overseas", "visa", "passport", "immigration",
          "settle abroad", "foreign travel", "tour", "trip", "pilgrimage", "hajj",
          "umrah", "migration", "move to", "on-site", "onsite", "pr card",
          "green card", "citizenship", "student visa", "work permit", "flight"]),

 "education": dict(
    label="Education / Exam / Competition",
    primary=[2, 4, 5, 11], support=[9, 10], avoid=[6, 8, 12],
    karakas=["Mercury", "Jupiter", "Venus"],
    keys=["education", "exam", "examination", "study", "studies", "college",
          "admission", "seat", "result", "pass", "rank", "competition",
          "competitive", "upsc", "jee", "neet", "degree", "phd", "masters",
          "abroad study", "scholarship", "course", "certification", "interview exam"]),

 "health": dict(
    label="Health / Recovery / Surgery",
    primary=[1, 6, 8, 11], support=[5, 10], avoid=[7, 12],
    karakas=["Sun", "Mars", "Saturn"],
    keys=["health", "illness", "disease", "sick", "recovery", "recover", "surgery",
          "operation", "hospital", "cure", "treatment", "chronic", "bp", "sugar",
          "diabetes", "heart", "cancer", "operation date", "discharge", "pain",
          "injury", "accident", "immunity", "mental health", "stress"]),

 "litigation": dict(
    label="Litigation / Court / Police",
    primary=[6, 8, 11, 12], support=[10, 1], avoid=[9, 2],
    karakas=["Saturn", "Mars", "Rahu"],
    keys=["court", "case", "litigation", "lawsuit", "police", "fir", "jail",
          "judge", "verdict", "judgement", "judgment", "legal", "lawyer",
          "arbitration", "notice", "summons", "hearing", "win case", "bail",
          "dispute", "complaint", "tribunal", "rbi", "consumer court"]),

 "vehicle_purchase": dict(
    label="Vehicle Purchase",
    primary=[4, 11], support=[2, 9], avoid=[6, 8, 12],
    karakas=["Venus", "Mars"],
    keys=["buy car", "new car", "car purchase", "bike purchase", "buy bike",
          "scooter", "vehicle purchase", "car delivery", "car booking"]),

 "spiritual": dict(
    label="Spiritual / Deeksha / Temple",
    primary=[9, 12, 5], support=[10, 11], avoid=[6, 8],
    karakas=["Jupiter", "Ketu"],
    keys=["spiritual", "deeksha", "diksha", "mantra", "temple", "pilgrimage",
          "meditation", "sadhana", "moksha", "initiation", "guru", "kundalini",
          "pooja", "puja", "vrat", "fasting", "charity", "donation"]),

 "lost": dict(
    label="Lost Object / Theft / Recovery",
    primary=[2, 4, 11], support=[1, 3], avoid=[8, 12],
    karakas=["Mercury", "Moon"],
    keys=["lost", "missing", "stolen", "theft", "robbery", "recover lost",
          "find", "misplaced", "lost phone", "lost document", "lost gold"]),

 "enemy": dict(
    label="Enemies / Obstacles / Hidden",
    primary=[6, 8, 12], support=[3, 11], avoid=[9, 10],
    karakas=["Saturn", "Rahu", "Mars"],
    keys=["enemy", "enemies", "obstacle", "obstacles", "hidden", "black magic",
          "evil eye", "nazar", "jealousy", "opposition", "competitor", "rival",
          "betrayal", "cheating", "fraud", "scam"]),

 "general": dict(
    label="General Event Timing",
    primary=[1, 2, 11], support=[9, 10], avoid=[6, 8, 12],
    karakas=["Jupiter", "Moon"],
    keys=[]),
}

# Any extra phrase that nudges a query into a domain even without an exact key hit
HINT_MAP = {
    "meeting_partner": ["meeting wife", "meet wife", "would be wife", "future wife", "meeting spouse"],
    "marriage": ["shaadi", "kalyanam", "vivah", "wedding", "spouse", "bride"],
    "career": ["job", "naukri", "promotion", "career", "salary", "boss"],
    "child": ["baby", "child", "pregnan", "son", "daughter"],
    "property": ["flat", "house", "plot", "car", "property", "possession"],
    "travel": ["abroad", "foreign", "visa", "travel", "flight"],
    "health": ["health", "surgery", "hospital", "illness", "disease", "pain"],
    "litigation": ["court", "case", "police", "legal", "lawyer"],
    "finance": ["money", "loan", "debt", "income", "profit", "wealth"],
    "education": ["exam", "study", "result", "admission", "college"],
}

def _norm(q):
    return " ".join((q or "").lower().replace("-", " ").replace("_", " ").split())

def classify(query):
    """Free-text -> (domain_key, domain_dict, matched_terms). Never fails."""
    q = _norm(query)
    best, best_score, matched = "general", 0, []
    for key, d in DOMAINS.items():
        if key == "general":
            continue
        score, hits = 0, []
        for k in d["keys"]:
            kk = _norm(k)
            if not kk:
                continue
            # phrase hit (>=2 words) weights more than single word
            if (" " in kk or len(kk) > 9) and kk in q:
                score += 3
                hits.append(k)
            elif len(kk.split()) == 1 and any(tok == kk for tok in q.split()):
                score += 2
                hits.append(k)
            elif len(kk) > 3 and kk in q:
                score += 1
                hits.append(k)
        if score > best_score:
            best, best_score, matched = key, score, hits
    if best_score == 0:  # substring fallback
        for key, hints in HINT_MAP.items():
            for h in hints:
                if h in q:
                    return key, DOMAINS[key], [h]
    return best, DOMAINS[best], matched

def house_vector(domain_key):
    d = DOMAINS.get(domain_key, DOMAINS["general"])
    return d["primary"], d["support"], d["avoid"], d["karakas"]


def explain_domain(query):
    """Return a user-visible explanation of automatic domain selection."""
    key, d, matched = classify(query)
    return {
        "domain": key,
        "label": d["label"],
        "matched_terms": matched,
        "primary_houses": d["primary"],
        "support_houses": d["support"],
        "avoid_houses": d["avoid"],
        "karakas": d["karakas"],
        "auto_selected": True,
        "note": "Domain selected automatically from query context; no manual domain choice required."
    }

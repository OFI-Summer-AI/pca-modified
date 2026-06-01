"""Keyword-based intent classification — no AI calls."""
import re

# Greeting patterns — handled locally, no AI
_GREETING_WORDS = {
    "hi", "hello", "hey", "hiya", "howdy", "greetings",
    "good morning", "good afternoon", "good evening", "good day",
    "thanks", "thank you", "thankyou", "cheers", "great", "awesome",
    "what can you do", "help", "what are you", "who are you",
}

# Order ID pattern — 6 to 12 digit number in the question
_ORDER_ID_RE = re.compile(r'\b(\d{6,12})\b')

_INTENT_RULES = [
    ("DELAY_ANALYSIS",   ["delay", "late", "overdue", "on time", "on-time", "behind schedule",
                          "dd_flag", "delayed order", "not delivered", "past due"]),
    ("SOURCE_ANALYSIS",  ["wrong source", "suboptimal", "optimal source", "source location",
                          "changed_from", "optimal_source", "non-optimal",
                          "wrong location", "incorrect source"]),
    ("PLANT_ANALYSIS",   ["plant", "warehouse", "site", "werks", "facility",
                          "storage location", "distribution center"]),
    ("MATERIAL_ANALYSIS",["material", "product", "matnr", "item", "sku", "part number"]),
    ("STATUS_QUERY",     ["compliance status", "overall status", "how many blocked",
                          "how many alert", "how many pass", "compliant", "non-compliant",
                          "what is the status", "compliance rate", "adherence"]),
    ("RANKING_QUERY",    ["top risk", "highest risk", "worst orders", "most critical",
                          "top 10", "top 5", "rank", "show me the top", "which orders",
                          "riskiest", "most violations", "highest score"]),
    ("DEVIATION_QUERY",  ["deviation", "violation", "rule breach", "most common deviation",
                          "frequent issue", "compliance issue", "mismatch",
                          "what went wrong", "what are the issues"]),
    ("SUMMARY_REQUEST",  ["summary", "overview", "brief me", "give me a summary",
                          "tell me about the data", "what does the data show",
                          "overall picture", "how are we doing", "how is compliance",
                          "what is happening", "whats going on", "how is everything"]),
]

_FALLBACK_RULES = [
    ("STATUS_QUERY",    ["blocked", "alert", "pass", "status", "risk level", "critical"]),
    ("RANKING_QUERY",   ["top", "most", "highest", "worst", "best", "list", "show me"]),
    ("PLANT_ANALYSIS",  ["location", "where"]),
    ("DEVIATION_QUERY", ["problem", "check", "issue", "error", "flag"]),
    ("SUMMARY_REQUEST", ["tell", "explain", "describe", "what"]),
]


def extract_order_id(question: str) -> str | None:
    """Return the first order-ID-like number in the question, or None."""
    m = _ORDER_ID_RE.search(question)
    return m.group(1) if m else None


def classify(question: str) -> str:
    q = question.lower().strip()

    # Greeting check — short questions or known greeting words
    if any(g == q for g in _GREETING_WORDS):
        return "GREETING"
    if len(q.split()) <= 3 and any(g in q for g in ("hi", "hello", "hey", "thanks", "thank you")):
        return "GREETING"

    # Specific order lookup — a long number is present in the question
    if extract_order_id(question):
        order_words = ("order", "delivery", "show", "tell", "detail", "about", "what",
                       "status", "find", "look", "check", "give", "explain", "risk", "deviation")
        if any(w in q for w in order_words) or len(q.split()) <= 4:
            return "ORDER_LOOKUP"

    for intent, keywords in _INTENT_RULES:
        if any(kw in q for kw in keywords):
            return intent

    for intent, keywords in _FALLBACK_RULES:
        if any(kw in q for kw in keywords):
            return intent

    return "OPEN_ENDED"

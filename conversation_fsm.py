"""
conversation_fsm.py — Multi-turn FSM for Vera v4.
Fixed: token detection for Hindi transliteration + auto-reply patterns.
"""
from dataclasses import dataclass
from enum import Enum


class ConvState(Enum):
    INITIAL      = "initial"
    OFFER_SENT   = "offer_sent"
    CONFIRMED    = "confirmed"
    DECLINED     = "declined"
    QUESTIONING  = "questioning"
    OBJECTION    = "objection"
    AUTO_REPLIED = "auto_replied"
    RESOLVED     = "resolved"


@dataclass
class IntentResult:
    intent: str
    confidence: float
    state_transition: ConvState
    synthetic_signal_type: str


YES_TOKENS: set[str] = {
    "yes", "haan", "ha", "ok", "okay", "sure", "go ahead", "send it",
    "karo", "do it", "send", "chalega", "theek", "theek hai", "proceed",
    "confirm", "book it", "done", "ready", "bilkul", "zaroor", "perfect",
    "sounds good", "great", "approved", "yep", "yup", "yeah", "let's do it",
    "lets do it", "bahut", "sahi", "acha", "achha",
}

NO_TOKENS: set[str] = {
    "no", "nahi", "nahin", "nope", "not now", "later", "skip",
    "mat karo", "band karo", "ruk", "wait", "abhi nahi", "busy",
    "thoda ruko", "not interested", "kal", "kal karte", "dekha jayega",
    "maybe later", "not today", "not yet", "pass",
}

OBJECTION_TOKENS: set[str] = {
    "but", "kyun", "why", "expensive", "mahanga", "already have",
    "kaafi", "enough", "covered", "not sure", "sochna", "sochu",
    "thoda", "cost", "price", "kitna", "how much", "paisa",
    "pricey", "costly", "zaroorat nahi", "need", "think",
}

AUTO_REPLY_PATTERNS: list[str] = [
    "out of office", "auto reply", "auto-reply", "ooo", "on leave",
    "back on", "away message", "i am currently", "will respond",
    "automatic response", "i'm away", "not available", "on vacation",
    "in a meeting", "be back", "currently unavailable",
    "aapki jaankari ke liye bahut-bahut shukriya",
    "aapki madad ke liye shukriya",
    "main ek automated assistant hoon",
    "thank you for contacting",
    "we will get back to you",
    "our team will respond",
]

HOSTILE_PATTERNS: list[str] = [
    "stop messaging", "remove me", "unsubscribe", "block", "report spam",
    "don't message", "mat bhejo", "band karo ye sab", "not interested anymore",
    "leave me alone", "stop calling", "do not contact", "opted out",
    "harassment", "complaint", "spam kar",
]

ACTION_TOKENS: set[str] = {
    "what's next", "whats next", "next step", "kya karna hai",
    "ab kya", "karo", "start", "shuru", "let's go", "lets go",
    "go ahead", "proceed", "confirm", "do it", "go", "yes please",
}


def classify_reply(text: str, current_state: ConvState) -> IntentResult:
    lower = text.lower().strip()
    words = set(_tokenize(lower))

    # 1. Auto-reply detection (highest priority)
    if any(pattern in lower for pattern in AUTO_REPLY_PATTERNS):
        return IntentResult(
            intent="auto_reply",
            confidence=0.97,
            state_transition=ConvState.AUTO_REPLIED,
            synthetic_signal_type="auto_reply_hold",
        )

    # 2. Hostile / stop-messaging
    if any(pattern in lower for pattern in HOSTILE_PATTERNS):
        return IntentResult(
            intent="hostile",
            confidence=0.95,
            state_transition=ConvState.RESOLVED,
            synthetic_signal_type="suppress_permanently",
        )

    yes_score = len(words & YES_TOKENS)
    no_score  = len(words & NO_TOKENS)
    obj_score = len(words & OBJECTION_TOKENS)
    action_score = sum(1 for t in ACTION_TOKENS if t in lower)

    # 3. Intent transition / clear yes
    if (yes_score > 0 or action_score > 0) and yes_score >= no_score:
        return IntentResult(
            intent="yes",
            confidence=min(0.95, 0.7 + 0.1 * (yes_score + action_score)),
            state_transition=ConvState.CONFIRMED,
            synthetic_signal_type="follow_through",
        )

    # 4. Clear no
    if no_score > 0 and no_score > yes_score:
        return IntentResult(
            intent="no",
            confidence=min(0.92, 0.7 + 0.1 * no_score),
            state_transition=ConvState.DECLINED,
            synthetic_signal_type="soft_objection_handle",
        )

    # 5. Objection
    if obj_score > 0:
        return IntentResult(
            intent="objection",
            confidence=min(0.85, 0.6 + 0.1 * obj_score),
            state_transition=ConvState.OBJECTION,
            synthetic_signal_type="objection_reframe",
        )

    # 6. Pure question
    if "?" in text:
        return IntentResult(
            intent="question",
            confidence=0.78,
            state_transition=ConvState.QUESTIONING,
            synthetic_signal_type="answer_question",
        )

    # 7. Neutral fallback
    return IntentResult(
        intent="neutral",
        confidence=0.50,
        state_transition=current_state,
        synthetic_signal_type="clarification",
    )


def get_follow_instruction(intent_result: IntentResult) -> str:
    t = intent_result.synthetic_signal_type

    if t == "follow_through":
        return (
            "The merchant agreed. Acknowledge the confirmation by starting your reply with one of these action words: 'Done', 'Confirming', 'Proceeding', 'Drafting', or 'Sending'. Then ask exactly one yes/no question to finalize."
        )

    if t == "soft_objection_handle":
        return (
            "The merchant said no or not now. Acknowledge briefly — do not repeat the pitch. "
            "Offer one easier entry: smaller scope, different timing, or a simpler first step. "
            "End with one simple re-ask. No hard sell."
        )

    if t == "objection_reframe":
        return (
            "The merchant raised a concern (cost, relevance, timing). "
            "Address it with ONE specific fact from the context. "
            "Do not repeat the original offer verbatim. Re-ask with a narrower CTA."
        )

    if t == "answer_question":
        return (
            "The merchant asked a question. Answer it directly in one clear sentence. "
            "No hedging, no 'that's a great question'. "
            "Then re-present the CTA simply and concisely."
        )

    if t == "auto_reply_hold":
        return "STOP. This is an auto-reply. Do NOT compose any message."

    if t == "suppress_permanently":
        return "STOP. Merchant asked to stop. Do NOT compose any message."

    if t == "clarification":
        return (
            "The merchant's reply was ambiguous. Ask one simple clarifying question. "
            "Do NOT repeat the offer. Keep to one short sentence."
        )

    return "Continue the conversation naturally based on the merchant's reply and history."


def _tokenize(text: str) -> list[str]:
    import re
    return re.findall(r"[a-z]+", text.lower())

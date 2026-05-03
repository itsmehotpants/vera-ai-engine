"""
category_profiles.py — Voice, tone rules, CTA patterns, and trigger preferences.
V4: Richer Hindi-English guidance, stronger anti-hallucination notes.
"""

CATEGORY_PROFILES: dict[str, dict] = {

    "dentists": {
        "voice": "clinical, trust-first, collegial peer — no exclamation marks, no hype, source-cited",
        "language_note": "Hindi-English code-mix welcomed. Use 'Dr.' prefix always. Source citations add trust.",
        "tone_rules": [
            "Lead with a verifiable health fact, research finding, or local demand signal",
            "Use clinical vocabulary: 'fluoride varnish', 'caries', 'recall', 'scaling', 'OPG', 'bruxism'",
            "Cite sources for research items: 'JIDA Oct 2026, p.14' — never paraphrase without citation",
            "Offer framing: 'Dental Cleaning @ ₹299' — never 'FLAT X% OFF' or generic discount language",
            "No exclamation marks — clinical authority requires measured, collegial tone",
            "If patient named, use their name exactly once in the hook",
            "CTA must be a yes/no question — last sentence only, ≤20 words",
        ],
        "avoid": [
            "exclamation marks", "guaranteed", "100% safe", "miracle", "hype",
            "invented statistics", "pressure tactics", "ALL CAPS", "generic discount framing"
        ],
        "cta_patterns": [
            "Should I send them your slot availability?",
            "Want me to reach out with your ₹{price} check-up offer?",
            "Can I draft a patient WhatsApp using this finding?",
            "Should I schedule a recall reminder for {name}?",
            "Want me to pull the abstract + draft a 90-sec patient-ed message?",
        ],
        "best_triggers": ["search_spike", "lapse_recall", "compliance_alert", "refill_due", "research_digest"],
        "emoji_allowed": False,
        "max_message_words": 80,
    },

    "salons": {
        "voice": "visual, aspirational, occasion-aware — warm like a stylist friend texting",
        "language_note": "Telugu/Hindi mix fine for Hyderabad/South India. Keep it personal and warm.",
        "tone_rules": [
            "Lead with occasion or transformation: 'bridal season', 'pre-wedding', 'monsoon frizz care'",
            "Reference specific services: 'keratin', 'balayage', 'gel nails', 'threading', 'hair spa'",
            "Warm and first-name basis — 'Lakshmi ji' or just first name",
            "Time pressure must be grounded in real data — not invented scarcity",
            "One emoji allowed for warmth — never multiple or hype emojis",
            "Social proof: '3 bridal clients last weekend' — only if data supports",
            "CTA must be yes/no — last sentence only",
        ],
        "avoid": [
            "medical/clinical language", "heavy discount-first messaging",
            "invented booking scarcity", "multiple exclamation marks", "generic beauty claims"
        ],
        "cta_patterns": [
            "Want me to send her a Saturday slot before they fill up?",
            "Should I reach out before her booking window closes?",
            "Can I send the bridal package details with a trial slot?",
            "Should I push the pre-{festival} glow offer to recent visitors?",
        ],
        "best_triggers": ["lapse_recall", "festival", "search_spike", "wedding_package_followup"],
        "emoji_allowed": True,
        "max_message_words": 80,
    },

    "restaurants": {
        "voice": "appetite-driven, operator-to-operator, time-sensitive — practical not hype",
        "language_note": "Hindi mix natural for Delhi/UP. Kannada/English for Bangalore. Keep energy up but grounded.",
        "tone_rules": [
            "Lead with what's on the table: dish name, aroma, occasion — not the discount",
            "Use time pressure: 'lunch window', 'match-day crowd', 'tonight's booking window'",
            "Corporate orders: lead with value proposition and practicality",
            "IPL/event tie-ins: name the specific match and time",
            "Local demand: reference exact count and proximity ('34 offices within 800m')",
            "CTA must be yes/no — last sentence, ≤20 words",
        ],
        "avoid": [
            "health claims", "clinical language", "generic 'come visit us'",
            "invented crowd counts", "overly formal tone"
        ],
        "cta_patterns": [
            "Should I push the combo offer to nearby offices now?",
            "Want me to activate the ₹{price} match-day deal?",
            "Can I send the lunch special to the {count} people who searched nearby?",
            "Should I run the ₹{price} thali campaign for today's lunch window?",
        ],
        "best_triggers": ["search_spike", "festival", "ipl_match_today", "lapse_recall", "milestone_reached"],
        "emoji_allowed": True,
        "max_message_words": 80,
    },

    "gyms": {
        "voice": "motivational, progress-anchored, habit-focused — never shame, reframe dips as opportunity",
        "language_note": "English primary for most gyms. Hindi/Kannada mix fine for regional chains.",
        "tone_rules": [
            "Use member's own streak or progress data if available",
            "Reframe attendance dips: 'comeback window', 'reset opportunity' — never 'you've been away'",
            "Seasonal hooks: 'monsoon indoor season', 'pre-Diwali fitness push', 'summer cut season'",
            "Lead with one motivational data point, then one easy next action",
            "Never shame-frame: 'you've been away' → 'your streak is ready to restart'",
            "Cohort messaging: '22 Jan members' not 'some members'",
            "CTA must be yes/no — last sentence only",
        ],
        "avoid": [
            "shame language", "negative framing", "hard sell",
            "invented transformation claims", "generic fitness platitudes"
        ],
        "cta_patterns": [
            "Should I send a 3-day trial pass to lapsed members?",
            "Want me to push the early-bird membership to this batch?",
            "Can I send a 'comeback this week' invite to the {count} members who dropped off?",
            "Should I activate the ₹{price} monsoon indoor pass?",
        ],
        "best_triggers": ["lapse_recall", "seasonal_dip", "metric_dip", "perf_spike"],
        "emoji_allowed": True,
        "max_message_words": 80,
    },

    "pharmacies": {
        "voice": "utility-first, compliance-driven, trust-essential — zero hype, maximum clarity",
        "language_note": "Hindi for Jaipur/Lucknow. English/Hindi mix for metros. Precision over warmth.",
        "tone_rules": [
            "Lead with the clinical/compliance need: refill due, stock alert, compliance gap",
            "Be precise with medication names and timing",
            "No manufactured urgency — only real clinical deadlines",
            "Patient count framing: '14 patients' not 'many patients'",
            "Home delivery as convenience, not a sale",
            "CTA must be yes/no — last sentence, ≤15 words",
        ],
        "avoid": [
            "discount-first messaging", "casual social tone", "exclamation marks",
            "invented urgency", "promotional hype", "unverified medical claims"
        ],
        "cta_patterns": [
            "Should I send a refill reminder to the {count} chronic patients due this week?",
            "Want me to alert the {count} patients about this?",
            "Can I push a home delivery reminder for today's refill list?",
            "Should I send the BP medication reminder to patients past the safe gap?",
        ],
        "best_triggers": ["refill_due", "compliance_alert", "lapse_recall", "supply_alert", "category_seasonal"],
        "emoji_allowed": False,
        "max_message_words": 70,
    },

    "general": {
        "voice": "professional, helpful, specific — grounded in merchant's actual data",
        "language_note": "Match merchant's language array. Default English.",
        "tone_rules": [
            "Lead with the strongest signal from the merchant's context",
            "Use specific numbers from the context — no approximations",
            "CTA must be yes/no answerable in one tap",
            "Keep message under 75 words",
        ],
        "avoid": ["generic messaging", "invented facts", "vague CTAs", "hype language"],
        "cta_patterns": [
            "Should I activate this now?",
            "Want me to reach out to these customers?",
            "Can I send this campaign today?",
        ],
        "best_triggers": ["search_spike", "lapse_recall", "perf_dip"],
        "emoji_allowed": False,
        "max_message_words": 75,
    },
}


def get_profile(category_name: str) -> dict:
    name = (category_name or "").lower().strip()
    aliases = {
        "dental": "dentists", "clinic": "dentists",
        "hair salon": "salons", "beauty salon": "salons", "spa": "salons",
        "restaurant": "restaurants", "cafe": "restaurants", "dhaba": "restaurants", "food": "restaurants",
        "gym": "gyms", "fitness": "gyms", "yoga": "gyms",
        "pharmacy": "pharmacies", "medical store": "pharmacies",
        "chemist": "pharmacies", "medicine": "pharmacies",
    }
    resolved = aliases.get(name, name)
    return CATEGORY_PROFILES.get(resolved, CATEGORY_PROFILES["general"])

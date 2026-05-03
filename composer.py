"""
composer.py — Vera v4: Groq (Stage 1 JSON) + Gemini Flash (Stage 2 writing) + Groq (Stage 3 critique).
Fixes: no mark_sent inside compose, full context serialization, language enforcement, CTA enforcer.
"""
import json, re, os, asyncio
from dataclasses import dataclass, field
from typing import Optional
import google.generativeai as genai
from groq import AsyncGroq, RateLimitError
from dotenv import load_dotenv
from category_profiles import get_profile

load_dotenv()

_GROQ_KEY = os.getenv("GROQ_API_KEY", "")
_GEMINI_KEY = os.getenv("GEMINI_API_KEY", "")

if not _GROQ_KEY:
    raise RuntimeError("GROQ_API_KEY not set in .env")

_groq = AsyncGroq(api_key=_GROQ_KEY)
_GROQ_MODEL = "llama-3.3-70b-versatile"

_gemini_available = bool(_GEMINI_KEY and _GEMINI_KEY != "PASTE_YOUR_GEMINI_KEY_HERE")
if _gemini_available:
    genai.configure(api_key=_GEMINI_KEY)
    _gemini_model = genai.GenerativeModel("gemini-flash-lite-latest")


# ── System prompts ─────────────────────────────────────────────────────────────

_STAGE1_SYSTEM = """
You are the signal analyst for Vera, magicpin's merchant AI assistant.
Your goal is to plan the outbound message based EXACTLY on the TRIGGER provided.
DO NOT ignore the trigger to focus on other signals. The trigger is the ONLY reason we are messaging.

OUTPUT ONLY valid JSON with these exact keys:
{
  "chosen_signal": "one sentence: the exact hook based on the TRIGGER, with any NUMBER from the trigger verbatim",
  "rationale_chain": "2-3 sentences: why we must act on this trigger right now",
  "merchant_fact_to_use": "one literal value from context: ₹ amount, count, date, percentage, or rating",
  "secondary_fact": "a second literal value from context to add specificity (count, date, or ₹)",
  "urgency_frame": "today|this_week|evergreen",
  "why_now_reason": "one sentence: the exact reason this message must go out NOW, referencing the trigger",
  "monetary_impact": "one sentence: the specific revenue or cost impact of acting on this trigger",
  "cta_intent": "the specific yes/no action the merchant should approve",
  "suppression_window": "1h|4h|24h|7d",
  "tone_note": "one specific voice instruction for writing this message",
  "language_mode": "english|hi-en mix|te-en mix|kn-en mix|ta-en mix",
  "send_as": "vera|merchant_on_behalf"
}

RULES:
- NEVER INVENT DATA. All numbers, percentages, dates, and amounts in chosen_signal, why_now_reason, and monetary_impact MUST be literal values from the input.
- Focus ENTIRELY on the TRIGGER. Do not pivot to unrelated metrics if the trigger is specific (e.g., if trigger is about 'corporate bulk thali', do NOT pitch 'desserts').
- If customer context exists and trigger scope is customer, send_as = merchant_on_behalf
- language_mode must match merchant identity.languages array
""".strip()

_STAGE2_SYSTEM = """
You are Vera, magicpin's AI assistant for Indian merchants. Write ONE highly compelling WhatsApp message.

STRUCTURE:
  Sentence 1 (Hook): Lead with the live signal and use exact numbers, dates, and ₹ amounts from the PLAN SIGNAL. Do NOT invent any numbers.
  Sentence 2 (Insight): Explain WHY this matters RIGHT NOW for THIS merchant by name, explicitly state the monetary or growth impact (WHY NOW reason + MONETARY IMPACT), and use category-specific vocabulary. Address the Owner by name.
  Sentence 3 (CTA): An urgent, highly compelling yes/no question — last sentence, ≤20 words, starting with "Should I", "Want me to", or "Can I". Must end with "?".

HARD RULES:
  ✓ You MUST explicitly state the merchant's Business Name AND Owner Name.
  ✓ USE ONLY the numbers provided in the GROUNDED FACTS. Use the most relevant facts for the trigger.
  ✓ Explain the actionable benefit clearly to maximize Decision Quality.
  ✓ 2-4 sentences total, under 80 words.
  ✓ No greeting ("Hi", "Hello") — start with the hook directly.
  ✓ Match the language_mode instruction exactly.
  ✗ No invented facts, statistics, or claims not in the grounded facts.
  ✗ No exclamation marks for dentists or pharmacies.
  ✗ No preamble like "I hope you're doing well" or "Just checking in".

Return ONLY the message text. No JSON. No labels.
""".strip()

_STAGE3_SYSTEM = """
You are a strict rubric judge for the magicpin AI Challenge. Score a Vera message (0-10 each).

Dimensions:
  specificity     — exact verifiable numbers/dates/citations from the grounded facts block? Score 0 if ANY invented number.
  category_fit    — voice/vocabulary matches the merchant category? Clinical for dentists/pharmacies, warm for salons, energetic for gyms.
  merchant_fit    — personalized to THIS merchant's name, owner name, exact data, and language preference?
  trigger_relevance — clearly communicates WHY NOW (the specific trigger, deadline, or data spike)? Does it state the consequence of NOT acting?
  engagement      — yes/no CTA present? Compelling hook? Merchant would reply within seconds?

CRITICAL RULES:
- Any invented number or date → specificity=0 automatically.
- needs_rewrite=true if ANY dimension score < 8.
- rewrite_instruction must be specific: name the exact missing fact or structural problem.

Return ONLY valid JSON:
{
  "scores": {"specificity":0,"category_fit":0,"merchant_fit":0,"trigger_relevance":0,"engagement":0},
  "min_score": 0,
  "needs_rewrite": false,
  "rewrite_instruction": "",
  "invented_facts_found": false
}
""".strip()
@dataclass
class ComposeResult:
    message: str
    cta: str
    send_as: str
    suppression_key: str
    rationale: str
    rubric_scores: dict = field(default_factory=dict)
    stage3_rewrote: bool = False


async def compose(
    category: dict,
    merchant: dict,
    trigger: dict,
    customer: Optional[dict] = None,
    conversation_history: Optional[list] = None,
) -> ComposeResult:
    import traceback as _tb
    cat_slug = (category.get("slug") or category.get("name") or "general").lower()
    cat_profile = get_profile(cat_slug)

    # ── Stage 1: Signal plan ───────────────────────────────────────────────────
    try:
        s1_ctx = _build_stage1_context(category, merchant, trigger, customer, cat_profile, conversation_history)
        s1_resp = await _groq_chat(_STAGE1_SYSTEM, json.dumps(s1_ctx, ensure_ascii=False), 0.2, 650, json_mode=True)
        plan = _safe_json(s1_resp)
        print(f"[vera] S1 OK for {trigger.get('id','?')}: signal={plan.get('chosen_signal','')[:50]}")
    except Exception as e:
        print(f"[vera] S1 FAILED for {trigger.get('id','?')}: {e}")
        _tb.print_exc()
        plan = {}

    # ── Stage 2: Message writing ───────────────────────────────────────────────
    try:
        grounded_block = _build_grounded_block(category, merchant, trigger, customer, plan)
        language_mode = plan.get("language_mode", "english")
        s2_user = _build_stage2_prompt(grounded_block, plan, cat_profile, language_mode)
        message_v1 = await _write_message(s2_user)
        print(f"[vera] S2 OK for {trigger.get('id','?')}: msg={message_v1[:60]}")
    except Exception as e:
        print(f"[vera] S2 FAILED for {trigger.get('id','?')}: {e}")
        _tb.print_exc()
        raise  # re-raise so _handle catches it

    # ── Stage 3: Self-critique + rewrite ──────────────────────────────────────
    try:
        s3_user = json.dumps({
            "category": cat_slug,
            "trigger_kind": trigger.get("kind", ""),
            "grounded_facts": grounded_block,
            "category_voice": cat_profile.get("voice", ""),
            "taboos": cat_profile.get("avoid", []),
            "message": message_v1,
        }, ensure_ascii=False)
        s3_resp = await _groq_chat(_STAGE3_SYSTEM, s3_user, 0.1, 400, json_mode=True)
        critique = _safe_json(s3_resp)
        print(f"[vera] S3 OK for {trigger.get('id','?')}: scores={critique.get('scores',{})}")
    except Exception as e:
        print(f"[vera] S3 FAILED for {trigger.get('id','?')}: {e}")
        critique = {}

    scores = critique.get("scores", {})
    needs_rewrite = critique.get("needs_rewrite", False)
    rewrite_inst = critique.get("rewrite_instruction", "")
    stage3_rewrote = False
    final_message = message_v1

    if needs_rewrite and rewrite_inst:
        rw_user = (
            f"{s2_user}\n\n"
            f"PREVIOUS ATTEMPT (do not copy):\n{message_v1}\n\n"
            f"REQUIRED FIX: {rewrite_inst}\n"
            f"Write an improved message fixing this issue. Return ONLY the message text."
        )
        rw_resp = await _write_message(rw_user, temperature=0.6)
        final_message = rw_resp
        stage3_rewrote = True

    # ── CTA enforcer ──────────────────────────────────────────────────────────
    final_message = _enforce_cta(final_message, cat_profile)

    send_as = plan.get("send_as", "merchant_on_behalf" if customer else "vera")
    supp_key = trigger.get("suppression_key", f"vera:{merchant.get('merchant_id','x')}:{trigger.get('kind','g')}")

    return ComposeResult(
        message=final_message,
        cta=_classify_cta(final_message),
        send_as=send_as,
        suppression_key=supp_key,
        rationale=_build_rationale(plan, trigger, scores, stage3_rewrote),
        rubric_scores=scores,
        stage3_rewrote=stage3_rewrote,
    )


async def compose_reply(
    category: dict,
    merchant: dict,
    conversation_history: list,
    follow_instruction: str,
) -> ComposeResult:
    """Lightweight compose for /v1/reply — skips Stage 1."""
    cat_slug = (category.get("slug") or category.get("name") or "general").lower()
    cat_profile = get_profile(cat_slug)

    identity = merchant.get("identity", {})
    merchant_name = identity.get("name", "this merchant")
    locality = identity.get("locality", "your area")
    langs = identity.get("languages", ["en"])
    language_mode = "hi-en mix" if "hi" in langs else "english"

    history_tail = conversation_history[-5:]
    history_text = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in history_tail)

    s2_user = (
        f"MERCHANT: {merchant_name} · {locality}\n"
        f"LANGUAGE MODE: {language_mode}\n"
        f"CATEGORY VOICE: {cat_profile.get('voice', '')}\n"
        f"TONE RULES:\n" + "\n".join(f"  • {r}" for r in cat_profile.get("tone_rules", [])) +
        f"\n\nCONVERSATION SO FAR:\n{history_text}\n\n"
        f"TASK: {follow_instruction}\n"
        f"Write ONE short reply (1-2 sentences). No preamble. Return ONLY the message text."
    )

    message = await _write_message(s2_user, temperature=0.65, max_tokens=200)
    message = _enforce_cta(message, cat_profile)

    return ComposeResult(
        message=message,
        cta=_classify_cta(message),
        send_as="vera",
        suppression_key="reply",
        rationale=f"Reply: {follow_instruction[:80]}.",
        rubric_scores={},
        stage3_rewrote=False,
    )


# ── LLM helpers ────────────────────────────────────────────────────────────────

async def _write_message(prompt: str, temperature: float = 0.7, max_tokens: int = 280) -> str:
    """Try Gemini first, fall back to Groq."""
    if _gemini_available:
        for attempt in range(5):
            try:
                full_prompt = f"{_STAGE2_SYSTEM}\n\n{prompt}"
                loop = asyncio.get_event_loop()
                resp = await loop.run_in_executor(
                    None,
                    lambda: _gemini_model.generate_content(
                        full_prompt,
                        generation_config=genai.GenerationConfig(
                            temperature=temperature,
                            max_output_tokens=max_tokens,
                        )
                    )
                )
                text = resp.text.strip()
                if text:
                    return text
            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "Quota" in err_str or "ResourceExhausted" in err_str:
                    if attempt < 4:
                        await asyncio.sleep(5 + attempt * 10)
                        continue
                print(f"[vera] Gemini fallback to Groq: {e}")
                break

    # Groq fallback
    return await _groq_chat(_STAGE2_SYSTEM, prompt, temperature, max_tokens, json_mode=False)


async def _groq_chat(system: str, user: str, temperature: float, max_tokens: int,
                     json_mode: bool = False, max_retries: int = 5) -> str:
    """Try Gemini first (fast, no rate limits at our scale), fall back to Groq."""
    # ── Gemini path (preferred — avoids Groq concurrent rate limits) ──────────
    if _gemini_available:
        for attempt in range(max_retries):
            try:
                full_prompt = f"{system}\n\n{user}"
                config_kwargs: dict = {"temperature": temperature, "max_output_tokens": max_tokens}
                if json_mode:
                    config_kwargs["response_mime_type"] = "application/json"
                loop = asyncio.get_event_loop()
                resp = await loop.run_in_executor(
                    None,
                    lambda: _gemini_model.generate_content(
                        full_prompt,
                        generation_config=genai.GenerationConfig(**config_kwargs),
                    )
                )
                text = resp.text.strip()
                if text:
                    return text
            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "Quota" in err_str or "ResourceExhausted" in err_str:
                    if attempt < max_retries - 1:
                        await asyncio.sleep(5 + attempt * 10)
                        continue
                print(f"[vera] Gemini JSON error: {err_str}")
                break  # fall through to Groq

    # ── Groq fallback ─────────────────────────────────────────────────────────
    kwargs: dict = {
        "model": _GROQ_MODEL,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    for attempt in range(max_retries):
        try:
            resp = await _groq.chat.completions.create(**kwargs)
            return resp.choices[0].message.content or ""
        except RateLimitError:
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep((2 ** attempt) * 3)
    return ""


# ── Input builders ─────────────────────────────────────────────────────────────

def _build_stage1_context(category, merchant, trigger, customer, cat_profile, history) -> dict:
    identity = merchant.get("identity", {})
    perf = merchant.get("performance", {})
    offers = [o for o in merchant.get("offers", []) if o.get("status") == "active"]
    langs = identity.get("languages", ["en"])
    language_mode = "hi-en mix" if "hi" in langs else (
        "te-en mix" if "te" in langs else (
        "kn-en mix" if "kn" in langs else (
        "ta-en mix" if "ta" in langs else "english")))

    return {
        "category": {
            "slug": category.get("slug", ""),
            "voice": cat_profile.get("voice", ""),
            "avoid": cat_profile.get("avoid", []),
            "peer_stats": category.get("peer_stats", {}),
            "digest": category.get("digest", [])[:5],
            "trend_signals": category.get("trend_signals", [])[:3],
            "seasonal_beats": category.get("seasonal_beats", []),
            "offer_catalog": category.get("offer_catalog", [])[:4],
        },
        "merchant": {
            "merchant_id": merchant.get("merchant_id", ""),
            "name": identity.get("name", ""),
            "owner": identity.get("owner_first_name", ""),
            "city": identity.get("city", ""),
            "locality": identity.get("locality", ""),
            "verified": identity.get("verified", False),
            "languages": langs,
            "language_mode": language_mode,
            "subscription": merchant.get("subscription", {}),
            "performance": perf,
            "active_offers": offers,
            "signals": merchant.get("signals", []),
            "review_themes": merchant.get("review_themes", []),
            "customer_aggregate": merchant.get("customer_aggregate", {}),
            "conversation_history_tail": (history or [])[-3:],
        },
        "trigger": {
            "kind": trigger.get("kind", ""),
            "scope": trigger.get("scope", "merchant"),
            "source": trigger.get("source", ""),
            "urgency": trigger.get("urgency", 1),
            "payload": trigger.get("payload", {}),
            "suppression_key": trigger.get("suppression_key", ""),
            "expires_at": trigger.get("expires_at", ""),
        },
        "customer": customer if customer else None,
    }


def _build_grounded_block(category, merchant, trigger, customer, plan) -> str:
    """Build a grounded facts block — ONLY real data, explicitly labelled."""
    identity = merchant.get("identity", {})
    perf = merchant.get("performance", {})
    offers = [o for o in merchant.get("offers", []) if o.get("status") == "active"]
    peer = category.get("peer_stats", {})
    payload = trigger.get("payload", {})
    digest = category.get("digest", [])
    kind = trigger.get("kind", "")

    lines = [
        f"MERCHANT: {identity.get('name', 'this merchant')} · {identity.get('locality', '')} · {identity.get('city', '')}",
        f"OWNER: {identity.get('owner_first_name', '')}",
        f"SUBSCRIPTION: {merchant.get('subscription', {}).get('status', '')} · {merchant.get('subscription', {}).get('plan', '')} · {merchant.get('subscription', {}).get('days_remaining', '')} days remaining",
        f"VERIFIED GBP: {identity.get('verified', False)}",
        f"TRIGGER KIND: {kind}",
    ]

    # Performance
    if perf:
        lines.append(
            f"PERFORMANCE (30d): views={perf.get('views','?')} · calls={perf.get('calls','?')} · "
            f"CTR={perf.get('ctr','?')} · directions={perf.get('directions','?')}"
        )
        delta = perf.get("delta_7d", {})
        if delta:
            lines.append(f"7-DAY DELTA: {json.dumps(delta)}")
    if peer:
        lines.append(f"PEER BENCHMARK (category avg): CTR={peer.get('avg_ctr','?')} · calls={peer.get('avg_calls_30d','?')} · rating={peer.get('avg_rating','?')}")

    # Offers
    for o in offers[:2]:
        lines.append(f"ACTIVE OFFER: {o.get('title','')}")

    # Customer aggregate
    ca = merchant.get("customer_aggregate", {})
    if ca:
        lines.append(f"CUSTOMER AGGREGATE: {json.dumps(ca)}")

    # Signals
    sigs = merchant.get("signals", [])
    if sigs:
        lines.append(f"MERCHANT SIGNALS: {', '.join(str(s) for s in sigs[:5])}")

    # Review themes
    for rt in merchant.get("review_themes", [])[:2]:
        lines.append(f"REVIEW THEME: {rt.get('theme','')} ({rt.get('sentiment','')}) — {rt.get('common_quote','')[:80]}")

    # ── Trigger-kind specific enrichments ──────────────────────────────────────

    # Perf dip: compute revenue at risk
    if kind in ("perf_dip", "seasonal_perf_dip", "review_theme_emerged"):
        metric = payload.get("metric", "calls")
        delta_pct = payload.get("delta_pct", 0)
        window = payload.get("window", "7d")
        vs_baseline = payload.get("vs_baseline", perf.get("calls", 0))
        lost = abs(round(vs_baseline * abs(delta_pct)))
        lines.append(f"PERF DIP ANALYSIS: {metric} down {abs(delta_pct)*100:.0f}% over {window} vs baseline {vs_baseline} → approx {lost} fewer {metric} lost")
        if payload.get("is_expected_seasonal"):
            lines.append(f"SEASONAL NOTE: {payload.get('season_note', '')}")
        if payload.get("theme"):
            lines.append(f"REVIEW DIP: theme='{payload.get('theme')}' occurrences={payload.get('occurrences_30d','?')} trend={payload.get('trend','')}")
            lines.append(f"  COMMON QUOTE: {payload.get('common_quote','')[:120]}")

    # Perf spike: capture opportunity
    if kind == "perf_spike":
        metric = payload.get("metric", "calls")
        delta_pct = payload.get("delta_pct", 0)
        vs_baseline = payload.get("vs_baseline", perf.get("calls", 0))
        gained = round(vs_baseline * delta_pct)
        likely_driver = payload.get("likely_driver", "")
        lines.append(f"PERF SPIKE: {metric} up {delta_pct*100:.0f}% over {payload.get('window','7d')} → +{gained} extra {metric} vs baseline {vs_baseline}")
        if likely_driver:
            lines.append(f"SPIKE DRIVER: {likely_driver}")

    # Category seasonal: list demand numbers
    if kind == "category_seasonal":
        trends = payload.get("trends", [])
        lines.append(f"SEASONAL DEMAND SHIFTS: {', '.join(str(t) for t in trends)}")
        lines.append(f"SHELF ACTION RECOMMENDED: {payload.get('shelf_action_recommended', False)}")
        lines.append(f"SEASON: {payload.get('season', '')}")

    # Festival: days until
    if kind == "festival_upcoming":
        lines.append(f"FESTIVAL: {payload.get('festival','')} on {payload.get('date','')} — {payload.get('days_until','?')} days away")
        lines.append(f"CATEGORY RELEVANCE: {payload.get('category_relevance',[])}")

    # Winback / dormant
    if kind in ("winback_eligible", "dormant_with_vera"):
        days_since = payload.get("days_since_expiry", payload.get("days_since_last_merchant_message", "?"))
        lapsed = payload.get("lapsed_customers_added_since_expiry", ca.get("lapsed_90d_plus", ca.get("lapsed_180d_plus", "?")))
        dip_pct = payload.get("perf_dip_pct", "")
        lines.append(f"WINBACK CONTEXT: inactive {days_since} days · lapsed customers={lapsed} · perf_dip={dip_pct}")
        if payload.get("last_topic"):
            lines.append(f"LAST TOPIC: {payload.get('last_topic','')}")

    # GBP unverified
    if kind == "gbp_unverified":
        lines.append(f"GBP STATUS: unverified — estimated uplift {int(payload.get('estimated_uplift_pct',0)*100)}% views/calls after verification")
        lines.append(f"VERIFICATION PATHS: {payload.get('verification_path', 'postcard_or_phone_call')}")

    # Milestone
    if kind == "milestone_reached":
        value_now = payload.get("value_now", "?")
        milestone_value = payload.get("milestone_value", "?")
        gap = milestone_value - value_now if isinstance(value_now, int) and isinstance(milestone_value, int) else "?"
        lines.append(f"MILESTONE: {payload.get('metric','')} at {value_now}, target={milestone_value}, gap={gap}")
        lines.append(f"IMMINENT: {payload.get('is_imminent', False)}")

    # Renewal
    if kind == "renewal_due":
        lines.append(f"RENEWAL: {payload.get('days_remaining','?')} days left · plan={payload.get('plan','')} · amount=₹{payload.get('renewal_amount','')}")

    # Supply alert
    if kind == "supply_alert":
        lines.append(f"SUPPLY ALERT: molecule={payload.get('molecule','')} · batches={payload.get('affected_batches',[])} · manufacturer={payload.get('manufacturer','')}")
        chronic = ca.get("chronic_rx_count", "?")
        lines.append(f"PATIENTS AT RISK: chronic_rx_count={chronic}")

    # Competitor
    if kind == "competitor_opened":
        lines.append(f"COMPETITOR: {payload.get('competitor_name','')} opened {payload.get('opened_date','')} · {payload.get('distance_km','?')}km away")
        lines.append(f"THEIR OFFER: {payload.get('their_offer','')}")

    # Trigger payload (raw, as fallback)
    if payload:
        lines.append(f"TRIGGER PAYLOAD (raw): {json.dumps(payload)}")

    # Digest items
    top_item_id = payload.get("top_item_id") or payload.get("alert_id") or payload.get("digest_item_id")
    if top_item_id:
        for d in digest:
            if d.get("id") == top_item_id:
                lines.append(f"DIGEST ITEM: [{d.get('kind','').upper()}] {d.get('title','')}")
                if d.get("trial_n"):
                    lines.append(f"  TRIAL SIZE: {d['trial_n']} patients")
                if d.get("source"):
                    lines.append(f"  SOURCE: {d['source']}")
                if d.get("summary"):
                    lines.append(f"  SUMMARY: {d['summary'][:200]}")
                if d.get("actionable"):
                    lines.append(f"  ACTIONABLE: {d['actionable']}")
                if d.get("credits"):
                    lines.append(f"  CREDITS: {d['credits']} CDE credits")
                if d.get("date"):
                    lines.append(f"  DATE: {d['date']}")
                break

    # All digest items (for general research_digest triggers)
    elif kind == "research_digest" and digest:
        for d in digest[:3]:
            lines.append(f"DIGEST: {d.get('title','')} [{d.get('source','')}]")

    # Customer context
    if customer:
        cid = customer.get("identity", {})
        rel = customer.get("relationship", {})
        lines.append(f"CUSTOMER: {cid.get('name','')} · language={cid.get('language_pref','')} · state={customer.get('state','')}")
        lines.append(f"  visits={rel.get('visits_total','?')} · last_visit={rel.get('last_visit','?')} · services={rel.get('services_received',[])[:-3:-1]}")
        pref = customer.get("preferences", {})
        if pref.get("preferred_slots"):
            lines.append(f"  PREFERRED SLOT: {pref['preferred_slots']}")

    lines += [
        "─" * 50,
        "⚠ USE ONLY THE NUMBERS, NAMES, AND ₹ AMOUNTS LISTED ABOVE.",
        "⚠ DO NOT INVENT ANY OTHER FACTS, STATISTICS, OR CLAIMS.",
        "⚠ TRIGGER KIND: " + kind,
        "⚠ PLAN SIGNAL: " + plan.get("chosen_signal", ""),
        "⚠ WHY NOW: " + plan.get("why_now_reason", ""),
        "⚠ MONETARY IMPACT: " + plan.get("monetary_impact", ""),
    ]
    return "\n".join(lines)


def _build_stage2_prompt(grounded_block, plan, cat_profile, language_mode) -> str:
    parts = [
        grounded_block, "",
        f"LANGUAGE MODE: {language_mode} (MANDATORY — write in this language mix)",
        f"CATEGORY VOICE: {cat_profile.get('voice', '')}",
        "TONE RULES:",
        *[f"  • {r}" for r in cat_profile.get("tone_rules", [])],
        f"AVOID: {', '.join(cat_profile.get('avoid', []))}",
        "",
        "MESSAGE PLAN:",
        f"  Signal: {plan.get('chosen_signal', '')}",
        f"  Primary fact to use: {plan.get('merchant_fact_to_use', '')}",
        f"  Secondary fact to use: {plan.get('secondary_fact', '')}",
        f"  WHY NOW reason: {plan.get('why_now_reason', '')}",
        f"  Monetary/growth impact: {plan.get('monetary_impact', '')}",
        f"  CTA goal: {plan.get('cta_intent', '')}",
        f"  Tone note: {plan.get('tone_note', '')}",
        "",
        "DECISION QUALITY CHECKLIST (Sentence 2 must tick all that apply):",
        "  ✓ State WHY NOW (deadline, data spike, or event)",
        "  ✓ State the specific benefit/cost of acting vs. not acting",
        "  ✓ Use owner name + business name",
        "  ✓ Use category-specific vocabulary",
        "",
        "CTA PATTERNS (adapt, do not copy verbatim):",
        *[f"  • {c}" for c in cat_profile.get("cta_patterns", [])[:3]],
    ]
    return "\n".join(parts)


# ── Post-processing ────────────────────────────────────────────────────────────

def _enforce_cta(message: str, cat_profile: dict) -> str:
    """Ensure message ends with exactly one yes/no question."""
    if not message:
        return message

    # Strip trailing whitespace
    message = message.strip()

    # Count question marks
    q_count = message.count("?")

    if q_count == 0:
        # No CTA — append a generic one from category
        cta_patterns = cat_profile.get("cta_patterns", [])
        if cta_patterns:
            cta = cta_patterns[0].replace("{price}", "").replace("{count}", "").replace("{name}", "").replace("{festival}", "this occasion")
            message = message.rstrip(".") + " " + cta
    elif q_count > 1:
        # Multiple questions — keep only the last one sentence
        parts = re.split(r'(?<=[.!?])\s+', message)
        non_q = [p for p in parts if "?" not in p]
        q_parts = [p for p in parts if "?" in p]
        if q_parts:
            message = " ".join(non_q) + " " + q_parts[-1]

    return message.strip()


def _classify_cta(body: str) -> str:
    b = body.lower()
    if any(w in b for w in ["reply 1", "reply 2", "option 1", "option 2", "slot"]):
        return "multi_choice_slot"
    if any(w in b for w in ["confirm", "cancel"]):
        return "binary_confirm_cancel"
    if any(w in b for w in ["reply yes", "reply no", "say yes", "say no",
                             "should i", "can i ", "want me to", "want me "]):
        return "binary_yes_no"
    if "?" in body:
        return "open_ended"
    return "none"


def _safe_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass
    return {}


def _build_rationale(plan: dict, trigger: dict, scores: dict, rewrote: bool) -> str:
    lines = [
        f"Trigger: {trigger.get('kind', 'unknown')} (urgency {trigger.get('urgency', '?')}).",
        f"Signal chosen: {plan.get('chosen_signal', 'N/A')}.",
        f"Key fact: {plan.get('merchant_fact_to_use', 'N/A')}.",
        f"CTA goal: {plan.get('cta_intent', 'N/A')}.",
    ]
    if scores:
        lines.append("Rubric: " + " | ".join(f"{k}={v}" for k, v in scores.items()) + ".")
    if rewrote:
        lines.append("Stage 3 triggered a rewrite — improved version sent.")
    return " ".join(lines)

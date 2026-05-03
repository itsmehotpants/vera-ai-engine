# Vera v4.0 — magicpin AI Challenge Submission

## Team
- **Name**: Naman
- **Model**: gemini-1.5-flash (message writing) + llama-3.3-70b-versatile via Groq (signal planning + critique)

## Approach

### 3-Stage LLM Pipeline

**Stage 1 — Signal Planner (Groq, JSON mode)**
Takes the full 4-context input (category with digest/peer_stats/trends, merchant with performance/signals/reviews, trigger payload, customer if present) and returns a structured plan: which signal to use, what fact to anchor on, language mode, CTA intent, suppression window.

**Stage 2 — Message Writer (Gemini Flash)**
Receives a grounded facts block (only real data from context — no approximations) plus the signal plan. Writes a 2-4 sentence WhatsApp message in the correct language mix (hi-en, te-en, etc.), category voice, and with a yes/no CTA as the last sentence.

**Stage 3 — Self-Critique (Groq)**
Scores the message on all 5 rubric dimensions. If any dimension < 7, triggers a targeted rewrite with a specific instruction. CTA enforcer post-processing ensures exactly one yes/no question ends each message.

### Key Design Decisions

1. **Dual LLM**: Gemini Flash for natural language (best Hindi-English code-mix), Groq for structured JSON (faster, reliable format)
2. **Anti-hallucination firewall**: All numbers, names, and ₹ amounts are extracted into a grounded block. LLM is explicitly instructed to use only those values. Stage 3 penalizes any invented fact with specificity=0.
3. **Language enforcement**: Detects merchant's `languages` array and forces the appropriate code-mix in Stage 2
4. **Auto-reply detection**: Token-based + pattern-based. Consecutive auto-reply counter counts correctly. 1 = nudge, 2 = wait 24h, 3+ = end gracefully.
5. **Intent transition handling**: `follow_through` instruction switches to action mode immediately when merchant says yes — no more qualifying questions after a clear commitment.
6. **Suppression**: `mark_sent()` only called in `_process_trigger()`, never inside the composer. Trigger suppression keys used directly when available.
7. **Clean API responses**: `/v1/tick` and `/v1/reply` return only spec-defined fields.

## What Additional Context Would Have Helped

1. **Real merchant performance benchmarks per city**: peer_stats are category-wide; city-scoped benchmarks would make comparisons more actionable
2. **Slot availability from merchant calendar**: for recall/appointment triggers, we could offer actual open slots instead of generic availability
3. **Historical response patterns**: knowing which message types this specific merchant has replied to before would let us personalize trigger selection
4. **WhatsApp template approval status**: to know which template_names are actually pre-approved with Meta

## Running

```bash
# Install dependencies
pip install -r requirements.txt

# Add your API keys to .env
# GROQ_API_KEY=gsk_...
# GEMINI_API_KEY=AIza...

# Start server
uvicorn main:app --host 0.0.0.0 --port 8080

# Run judge simulator
export BOT_URL=http://localhost:8080
python ../judge_simulator.py
```

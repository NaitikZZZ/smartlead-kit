# Content Agent Rules

Accumulated rules for generating outbound copy and running campaigns for this kit. Consolidated from working sessions so they're versioned instead of living only in chat history.

**→ Read [`HUMANVOICE_COPY_GUIDE.md`](HUMANVOICE_COPY_GUIDE.md) first for tone, voice, persona framing, and the ready-to-use prompt for generating new sequences.**

## Punctuation
- Never use em dashes (—) or en dashes (–). Use hyphens, commas, or rewrite.
- Zero exclamation points in cold outbound.

## Step 1 Cold Outbound Email Format
Full rule set: [`reference/cold_outbound_email_sop.md`](reference/cold_outbound_email_sop.md) (Manoj Agarwal SOP, authoritative). Summary:
- No fixed sentence/word count. Complete, substantive introduction, not a thin one. Structured with bullets where a list runs 3+, not dense paragraphs.
- No selling: no stats, no ROI numbers, no feature pitch, no product deep-dive. Positioned purely as an introduction.
- Subject: under 5 words, specific, neutral, no cleverness, no emojis.
- Lead with a concrete, low-effort ask in sentence 1 (e.g. same location/domain, offer to show how a similar problem was solved).
- Xoxoday positioned as a global company (credibility signal, customized to the product), not a name-drop.
- No signature block (Smartlead auto-appends it at the account level).
- Output: subject line, blank line, body. No labels, no explanations.

## Sequencing (Step 2 onward)
- Every email reads as if it's the first, no "as discussed," "following up," "third note," or any sequence-position reference, ever.
- Never imply the sequence is ending ("before I close," "last mail," "closing the loop"). Cadence is open-ended until the prospect responds.
- Under 100 words. No banned phrases. No pitching until the arc calls for it (see SOP section 3). Low-pressure CTA. No dashes. No buzzwords.
- Funnel runs Email -> WhatsApp -> SDR call as a waterfall, not email alone.

## LinkedIn / WhatsApp / Call Scripts
All formatting/banned-phrase rules apply. No sentence-count rule.
- LinkedIn: no name sign-off at the end (sender profile shows automatically).
- Calls/WhatsApp: include name sign-off.

## Variants
Single variant only, no A/B split. Follow the 7-email arc in `reference/cold_outbound_email_sop.md` section 3 for what content goes in which step. Ask which product/use case if not stated before writing.

## Banned Phrases
"I hope you're doing well", "Impressive background", "Your X caught my attention",
"I'd love to pick your brain", "I know you're busy", "Just checking in",
"Let me introduce myself", "We're the X of Y", "We're disrupting",
"I wanted to reach out", "Would you be open to a quick chat?",
"We help companies like yours", "Thought you might be interested",
"Not sure if you're the right person", "Touching base", "Circling back",
"Quick question" (as filler)

## Banned Buzzwords
delve, landscape, leverage, realm, tapestry, navigate (verb), robust,
seamless, seamlessly, cutting-edge, groundbreaking, game-changing, revolutionize,
transform, elevate, unlock, meticulous, intricate, nuanced (unless genuinely needed),
"in today's fast-paced world", "in the ever-evolving", dive into, deep dive,
"it is worth noting", "it is important to note", notably, significantly,
harness, harness the power of, empower, empowering

## Humanizer Pass (always on)
Every drafted email, DM, script, brief, or doc gets a humanizer pass inline before delivery, blunt/Bezos-cadence voice by default:
- Short declarative sentences, mixed lengths. Lead with verb or subject, no "However," / "Moreover," openers.
- Sentence fragments fine. Contractions where natural.
- Specific numbers/names/anecdotes over generic claims. Concrete verbs ("rebuilt" not "transformed").
- No three-item bullet parallelism, no hedge-then-assert, no bow-tie endings ("In essence," / "Ultimately,").
- Max 1-2 bolds per paragraph.

## Team / Region Map
Africa = Roshaan, ROW = Mary, US = Tyler, SEA = Imelda, Global API = Gaurav, India = TBD

## Campaign Naming Convention
`PRIORITY_TEAM_USECASE_REGION_CHANNEL_POCNAME_STARTDATE`

## HubSpot Attribution
`random = "ABM 2026"` plus `abm_channels` for channel split (Cold Email / LinkedIn / Cold Call). HubSpot access is read-only, never write/mutate/create there.

## CSV Output Defaults
- Every output CSV includes `full_name` (first + last) and `company_domain`.
- Confirm `company_domain` resolution with the operator before generating.
- Normalize before any API upload or file send: `first_name` (first token only), `last_name` (strip credentials/suffixes), `company_name` (strip legal suffixes). These feed email merge tags directly.

## Smartlead Campaign Defaults
Timezone `Asia/Calcutta`, Mon-Fri 9-6, 20 min send interval, 200/day cap, tracking off, ESP matching on, AI auto-categorization on all categories, OOO handling with 7-day restart.

## Apollo Enrichment Defaults
Default to the curated 32-column set (no `id`/`postal_code`, `technologies` truncated to 40 tools) via `scripts/enrich_full_fields_apollo.py` `CORE_COLUMNS`. Use `--full` for everything.

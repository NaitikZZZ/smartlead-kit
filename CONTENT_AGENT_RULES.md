# Content Agent Rules

Accumulated rules for generating outbound copy and running campaigns for this kit. Consolidated from working sessions so they're versioned instead of living only in chat history.

## Punctuation
- Never use em dashes (—) or en dashes (–). Use hyphens, commas, or rewrite.
- Zero exclamation points in cold outbound.

## Step 1 Cold Outbound Email Format
- Exactly 4 sentences. Each under 15 words. Each on its own line.
- Subject: under 5 words, specific, neutral, no cleverness, no emojis.
- Structure: (1) why now, (2) challenge they face, (3) Xoxoday as credibility signal only, (4) low-pressure question.
- No product pitch. No feature list. No pricing.
- No signature block (Smartlead auto-appends it at the account level).
- Output: subject line, blank line, 4-sentence body. No labels, no explanations.

## Follow-ups (Step 2-5)
Under 100 words. No banned phrases. No pitching. Low-pressure CTA. No dashes. No buzzwords.

## LinkedIn / WhatsApp / Call Scripts
4-sentence rule does not apply. All other rules do.
- LinkedIn: no name sign-off at the end (sender profile shows automatically).
- Calls/WhatsApp: include name sign-off.

## A/B Testing (always on)
Every email produced needs both:
- **Variant A** - the 4-sentence short cold-outbound format above.
- **Variant B** - long-form, pulled from the relevant product/use-case framework in `copy-frameworks.md`.
Ask which product/use case if not stated before writing either variant.

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

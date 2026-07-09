from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import HexColor
from reportlab.lib.units import inch, mm
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable, KeepTogether
)

W, H = A4
PURPLE = HexColor("#5B21B6")
DARK = HexColor("#1E293B")
GRAY = HexColor("#64748B")
LIGHT_BG = HexColor("#F8FAFC")
WHITE = HexColor("#FFFFFF")
ACCENT = HexColor("#7C3AED")
GREEN = HexColor("#059669")
BLUE = HexColor("#2563EB")
ORANGE = HexColor("#EA580C")

styles = getSampleStyleSheet()
styles.add(ParagraphStyle("Title2", parent=styles["Title"], fontSize=22, textColor=PURPLE, spaceAfter=6))
styles.add(ParagraphStyle("Sub", parent=styles["Normal"], fontSize=11, textColor=GRAY, spaceAfter=14))
styles.add(ParagraphStyle("H1", parent=styles["Heading1"], fontSize=16, textColor=DARK, spaceBefore=18, spaceAfter=8))
styles.add(ParagraphStyle("H2", parent=styles["Heading2"], fontSize=13, textColor=PURPLE, spaceBefore=14, spaceAfter=6))
styles.add(ParagraphStyle("H3", parent=styles["Heading3"], fontSize=11, textColor=ACCENT, spaceBefore=10, spaceAfter=4))
styles.add(ParagraphStyle("Body", parent=styles["Normal"], fontSize=9.5, textColor=DARK, leading=14, spaceAfter=6))
styles.add(ParagraphStyle("Small", parent=styles["Normal"], fontSize=8.5, textColor=GRAY, leading=12, spaceAfter=4))
styles.add(ParagraphStyle("EmailBody", parent=styles["Normal"], fontSize=9, textColor=DARK, leading=13, leftIndent=12, spaceAfter=4, backColor=LIGHT_BG))
styles.add(ParagraphStyle("SubjectLine", parent=styles["Normal"], fontSize=9.5, textColor=BLUE, leading=13, spaceAfter=2, fontName="Helvetica-Bold"))
styles.add(ParagraphStyle("ManualStep", parent=styles["Normal"], fontSize=9, textColor=DARK, leading=13, leftIndent=12, spaceAfter=4))
styles.add(ParagraphStyle("CenterNote", parent=styles["Normal"], fontSize=9, textColor=GRAY, alignment=TA_CENTER, spaceAfter=10))

def hr():
    return HRFlowable(width="100%", thickness=0.5, color=HexColor("#E2E8F0"), spaceAfter=8, spaceBefore=8)

def badge(text, color):
    return Paragraph(f'<font color="{color}" size="9"><b>{text}</b></font>', styles["Body"])

def make_cadence_table(data):
    col_w = [35, 55, 200, 35, 70]
    t = Table(data, colWidths=col_w, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PURPLE),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("LEADING", (0, 0), (-1, -1), 11),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.4, HexColor("#CBD5E1")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT_BG]),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t

def make_summary_table(data):
    t = Table(data, colWidths=[140, 320], repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), DARK),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("LEADING", (0, 0), (-1, -1), 12),
        ("GRID", (0, 0), (-1, -1), 0.4, HexColor("#CBD5E1")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT_BG]),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return t

story = []

# ── COVER ──
story.append(Spacer(1, 80))
story.append(Paragraph("P0 Passive Pipeline", styles["Title2"]))
story.append(Paragraph("Smartlead Campaign Plan", styles["Title2"]))
story.append(Spacer(1, 12))
story.append(Paragraph("Xoxoday | Plum (Global API) | 945 Leads | 3 Segments | 11-Day Multi-Channel Cadence", styles["Sub"]))
story.append(hr())
story.append(Spacer(1, 20))
story.append(Paragraph("Prepared for review before Smartlead deployment", styles["CenterNote"]))
story.append(Paragraph("Date: April 2026 | Product: Plum Pro API | Team: ABM + SDR", styles["CenterNote"]))
story.append(Spacer(1, 30))

summary_data = [
    ["Metric", "Value"],
    ["Total P0 Leads", "945 (100% untouched — zero cadence steps completed)"],
    ["Campaign 1", "Plum API / Integration Warm — 372 leads (re-engagement)"],
    ["Campaign 2", "Passive New Deals — 480 leads (cold intro)"],
    ["Campaign 3", "Empuls / Loyalty / Other — 93 leads (multi-product)"],
    ["Smartlead Steps", "5 auto-emails per campaign (D1, D3, D6, D9, D11)"],
    ["Manual Touches", "6 per lead (LinkedIn visits, likes, connect, DMs, 2 phone calls)"],
    ["Cadence Length", "11 days"],
    ["Product", "Plum Pro API — global rewards infrastructure"],
    ["Positioning", '"Your earn engine + our burn engine" (open-loop only)'],
]
story.append(make_summary_table(summary_data))
story.append(Spacer(1, 20))

deal_data = [
    ["Category", "Count / Detail"],
    ["New Deal (generic)", "472 (50%) — went cold early, never saw demo"],
    ["API / Integration", "127 (13%) — active integration interest signals"],
    ["Rewards (general)", "78 (8%) — referenced rewards in deal name"],
    ["Rewards API/Integration", "72 (8%) — specific API/integration + rewards"],
    ["Plum (general)", "58 (6%) — named Plum product"],
    ["Plum API/Integration", "47 (5%) — Plum + API keyword"],
    ["Empuls", "21 (2%) — employee R&R product"],
    ["Loyalty / Incentives / Perks", "15 (2%) — mixed product signals"],
    ["Other", "55 (6%) — misc"],
]
story.append(Paragraph("Deal Name Breakdown (from HubSpot)", styles["H2"]))
story.append(make_summary_table(deal_data))
story.append(Spacer(1, 14))

title_data = [
    ["Metric", "Value"],
    ["Top Titles", "Founder (46), Co-Founder (32), CEO (45), Director (19), Product Manager (13)"],
    ["Also Present", "HR Manager (6), Head of Product (6), Head of Marketing (4), Head of Partnerships (4)"],
    ["Missing Job Title", "~170 leads (18%) — can still send, weaker personalization"],
    ["Email Quality", "100% have email, but many are generic (info@, admin@, connect@)"],
]
story.append(Paragraph("Lead Profile Summary", styles["H2"]))
story.append(make_summary_table(title_data))

story.append(PageBreak())

# ── CAMPAIGN DEFINITIONS ──

campaigns = [
    {
        "num": 1,
        "name": "P0 — Plum API / Integration Warm Re-engagement",
        "leads": 372,
        "color": GREEN,
        "angle": "Re-engagement. These leads explored Plum/Rewards API/SSO/Integration before and went cold. Copy: \"we've shipped a lot since you last looked.\"",
        "cadence": [
            ["Day", "Channel", "Step", "Owner", "Auto?"],
            ["D1", "Email", "Email 1 — Re-engagement hook", "ABM", "Smartlead"],
            ["D1", "LinkedIn", "Profile visit", "ABM", "Manual"],
            ["D2", "LinkedIn", "Like/comment on post", "ABM", "Manual"],
            ["D3", "Email", "Email 2 — What's new + proof", "ABM", "Smartlead"],
            ["D4", "LinkedIn", "Connection request (no note)", "ABM", "Manual"],
            ["D5", "Phone", "SDR Call 1", "SDR", "Manual"],
            ["D6", "Email", "Email 3 — Competitive differentiation", "ABM", "Smartlead"],
            ["D7", "LinkedIn", "DM / InMail", "ABM", "Manual"],
            ["D8", "Phone", "SDR Call 2 + voicemail", "SDR", "Manual"],
            ["D9", "Email", "Email 4 — Sandbox CTA", "ABM", "Smartlead"],
            ["D11", "Email", "Email 5 — Breakup", "ABM", "Smartlead"],
        ],
        "emails": [
            {
                "step": "Step 1 — Day 0 | Re-engagement Hook",
                "subjects": [
                    "Subject A: {{first_name}}, quick update on the Plum integration you explored",
                    "Subject B: {{company_name}} + Plum — picking up where we left off"
                ],
                "body": "Hey {{first_name}},\n\nI noticed {{company_name}} explored a rewards integration with Plum a while back — and I wanted to flag that we've shipped quite a bit since then.\n\nQuick highlights:\n- 10,000+ reward options across 100+ countries (gift cards, experiences, merchandise, charity, mobile top-ups)\n- Perks API — a zero-cost engagement layer your users get for free\n- 2-3 week go-live for API integration, full sandbox access from day one\n- SOC 2 Type II + ISO 27001 + GDPR certified\n\nIf the use case is still relevant for {{company_name}}, happy to set up a quick sandbox walkthrough — 15 min, no commitment.\n\nWorth revisiting?\n\n{{sender_first_name}}\nXoxoday | Plum"
            },
            {
                "step": "Step 2 — Day 3 | What's New + Use Case Proof",
                "subjects": ["Subject: Re: {{first_name}}, quick update on the Plum integration you explored"],
                "body": "{{first_name}} — following up on my last note.\n\nSince you last looked at Plum, we've onboarded wellness apps like Viwell, banking platforms like HDB Financial, and survey companies like Nielsen — all through the same API you'd be using.\n\nThe pattern we're seeing: companies that have an earn engine (points, cashback, activity rewards) but need a global burn engine. Plum slots in as the redemption layer — your platform stays the destination, we power what happens after users earn.\n\nHappy to share a 2-min Loom showing how a company similar to {{company_name}} integrated. Want it?\n\n{{sender_first_name}}"
            },
            {
                "step": "Step 3 — Day 6 | Competitive Differentiation",
                "subjects": ["Subject: Why teams switch from Tremendous / Tango to Plum"],
                "body": "Hey {{first_name}},\n\nOne thing we keep hearing from teams evaluating reward infrastructure: most alternatives are gift-card-only platforms limited to a single geography.\n\nHere's how Plum compares:\n- Tremendous — gift cards only, limited international catalogue\n- Tango Card — primarily US-focused, narrow category mix\n- Rybbon — email-based delivery, no real API-first architecture\n\nPlum gives you gift cards + experiences + lounge access + merchandise + charity + mobile top-ups + always-on perks — all through one API, localised to 100+ countries.\n\nIf {{company_name}} is comparing options, I can put together a side-by-side tailored to your use case. Just reply.\n\n{{sender_first_name}}\nXoxoday | Plum"
            },
            {
                "step": "Step 4 — Day 9 | Sandbox CTA",
                "subjects": ["Subject: Free sandbox access for {{company_name}} — no strings"],
                "body": "{{first_name}},\n\nI know timing matters more than anything — so here's an open offer:\n\nI've set aside sandbox access for {{company_name}}. You can test the full Plum API — browse the catalogue, simulate reward orders, see the webhook responses — without talking to anyone or committing to anything.\n\nIf rewards infrastructure is on your roadmap for this year, this saves your eng team a week of evaluation. If not, no pressure at all.\n\nWant me to send the sandbox credentials?\n\n{{sender_first_name}}"
            },
            {
                "step": "Step 5 — Day 11 | Breakup",
                "subjects": ["Subject: Closing the loop, {{first_name}}"],
                "body": "Hey {{first_name}},\n\nLast note from me on this thread.\n\nIf {{company_name}} ever revisits the rewards integration — whether it's for customer loyalty, survey incentives, referral rewards, or employee recognition — Plum's API is ready to plug in. 2-3 weeks to go live, 100+ countries, one integration.\n\nI'll check back in a few months. But if something changes before then, just hit reply — I'm an easy conversation away.\n\nWishing you and the team a strong quarter.\n\n{{sender_first_name}}\nXoxoday | Plum"
            },
        ],
        "manual": [
            ("D1 — LinkedIn Profile Visit", "ABM", "Visit the prospect's LinkedIn profile via Dux-Soup or manually. Don't connect yet — just let the \"viewed your profile\" notification land alongside the email."),
            ("D2 — LinkedIn Like/Comment", "ABM", "Find a recent post. Like it. If substantive, leave a short 1-2 sentence comment relevant to their industry — not a pitch."),
            ("D4 — LinkedIn Connection Request", "ABM / HeyReach", "Clean connection request with NO note. Acceptance rates are higher without a pitch. If accepted, D7 DM becomes available."),
            ("D5 — SDR Call 1", "SDR", "Script: \"Hi {{first_name}}, this is [SDR Name] from Xoxoday. I'm following up on an email about Plum — you explored a rewards integration with us a while back. Is that still on your radar?\" Voicemail: \"Sent you an email about Plum's rewards API — just putting a voice to the name. Would love 15 minutes.\""),
            ("D7 — LinkedIn DM / InMail", "ABM", "\"Hey {{first_name}} — sent a couple of emails about Plum's rewards API. Quick version: we power the redemption layer for apps like Viwell and HDB — 10,000+ rewards, 100+ countries, one API. Happy to share sandbox access if relevant.\""),
            ("D8 — SDR Call 2", "SDR", "Second dial. Voicemail: \"[SDR Name] again from Xoxoday. Reached out a few times via email and LinkedIn — one more try by phone. If rewards infrastructure comes back on the roadmap, I'm here. All the best.\""),
        ]
    },
    {
        "num": 2,
        "name": "P0 — Passive New Deals (Cold Intro)",
        "leads": 480,
        "color": BLUE,
        "angle": "Fresh introduction. Generic 'New Deal' entries — went cold early, likely never saw a demo. Copy: educational, value-first, \"your earn engine + our burn engine.\"",
        "cadence": [
            ["Day", "Channel", "Step", "Owner", "Auto?"],
            ["D1", "Email", "Email 1 — Value hook (earn + burn)", "ABM", "Smartlead"],
            ["D1", "LinkedIn", "Profile visit", "ABM", "Manual"],
            ["D2", "LinkedIn", "Like/comment on post", "ABM", "Manual"],
            ["D3", "Email", "Email 2 — Use-case proof point", "ABM", "Smartlead"],
            ["D4", "LinkedIn", "Connection request (no note)", "ABM", "Manual"],
            ["D5", "Phone", "SDR Call 1", "SDR", "Manual"],
            ["D6", "Email", "Email 3 — How it works (product-led)", "ABM", "Smartlead"],
            ["D7", "LinkedIn", "DM / InMail", "ABM", "Manual"],
            ["D8", "Phone", "SDR Call 2 + voicemail", "SDR", "Manual"],
            ["D9", "Email", "Email 4 — Sandbox CTA", "ABM", "Smartlead"],
            ["D11", "Email", "Email 5 — Breakup", "ABM", "Smartlead"],
        ],
        "emails": [
            {
                "step": "Step 1 — Day 0 | Value Hook — Earn + Burn",
                "subjects": [
                    "Subject A: {{first_name}}, quick question about rewards at {{company_name}}",
                    "Subject B: Your users earn. What do they redeem?"
                ],
                "body": "Hey {{first_name}},\n\nQuick question: if {{company_name}} runs any kind of points, cashback, referral, or engagement program — what does the redemption experience look like for your users?\n\nMost companies we speak with have built a strong earn engine but struggle with the burn side — limited reward options, single-geography catalogues, or high fulfilment overhead.\n\nWe power the rewards infrastructure for companies like Viwell, HDB Financial, and Curefit — giving their users instant access to 10,000+ reward options across 100+ countries. All through a single API integration that goes live in 2-3 weeks.\n\nIf this is relevant to what {{company_name}} is building, happy to discuss. 15 min, no commitment.\n\n{{sender_first_name}}\nXoxoday | Plum"
            },
            {
                "step": "Step 2 — Day 3 | Use-Case Proof Point",
                "subjects": ["Subject: Re: {{first_name}}, quick question about rewards at {{company_name}}"],
                "body": "{{first_name}} — following up with something specific.\n\nOne of our clients — a wellness app — was struggling with low reward redemption rates. Users earned points but didn't convert them because the catalogue was limited to a handful of local gift cards.\n\nAfter integrating Plum's API, they expanded to 10,000+ options across 100+ countries. Within 90 days, redemption rates tripled and monthly active users on the rewards page grew 40%.\n\nThe integration took under 3 weeks. They're now also using our Perks API to offer always-on discounts to users at zero cost.\n\nWould a quick sandbox demo tailored to {{company_name}}'s use case be useful? Just reply with a time.\n\n{{sender_first_name}}"
            },
            {
                "step": "Step 3 — Day 6 | How It Works (Product-Led)",
                "subjects": ["Subject: How companies integrate a global rewards catalogue in under 3 weeks"],
                "body": "Hey {{first_name}},\n\nHere's what a typical Plum integration looks like:\n\nDay 1-2: Sandbox access and API walkthrough. Full documentation, Postman collections, dedicated onboarding engineer.\n\nWeek 1: Integration build. Connect your platform to our Rewards API. Configure catalogue filters by country, category, and denomination.\n\nWeek 2-3: Testing and go-live. End-to-end sandbox testing, followed by production deployment.\n\nThrough that single integration, your users get access to gift cards, experiences, dining, merchandise, subscriptions, mobile top-ups, charity donations, and always-on perks — localised by country.\n\nWe also offer a white-labelled storefront if you prefer plug-and-play over building your own UI.\n\nReply if a 15-min technical walkthrough would help.\n\n{{sender_first_name}}\nXoxoday | Plum"
            },
            {
                "step": "Step 4 — Day 9 | Direct CTA / Sandbox Offer",
                "subjects": ["Subject: Free sandbox access for {{company_name}} — no commitment"],
                "body": "{{first_name}},\n\nRather than another email, here's a standing offer:\n\nI've set aside sandbox access for {{company_name}}. Your team can test the full Plum API — browse 10,000+ rewards, simulate orders, see webhook responses — without talking to anyone or signing anything.\n\nIf rewards infrastructure is on your roadmap this year, this saves your eng team a week of evaluation time. If it's not the right time, totally fine.\n\nWant me to send the sandbox credentials?\n\n{{sender_first_name}}"
            },
            {
                "step": "Step 5 — Day 11 | Breakup",
                "subjects": ["Subject: Last note, {{first_name}}"],
                "body": "Hey {{first_name}},\n\nI'll keep this short — this is my last email on this thread.\n\nIf {{company_name}} ever needs a global rewards API — whether for customer loyalty, survey incentives, referral programs, employee recognition, or anything in between — Plum integrates in 2-3 weeks and covers 100+ countries through one connection.\n\nI'll circle back in a few months. But if something changes before then, just reply to this thread.\n\nAll the best to you and the team.\n\n{{sender_first_name}}\nXoxoday | Plum"
            },
        ],
        "manual": [
            ("D1 — LinkedIn Profile Visit", "ABM", "Visit the prospect's LinkedIn profile. Let the notification create a warm signal alongside the email. No connect request yet."),
            ("D2 — LinkedIn Like/Comment", "ABM", "Engage with a recent post. 1-2 sentence comment if substantive. No pitch."),
            ("D4 — LinkedIn Connection Request", "ABM / HeyReach", "Clean connection request, no message attached. Sets up D7 DM."),
            ("D5 — SDR Call 1", "SDR", "Script: \"Hi {{first_name}}, [SDR Name] from Xoxoday. Sent an email about Plum — we build the rewards infrastructure that companies plug into when they need a global redemption catalogue. Is that something {{company_name}} is exploring?\" Voicemail: \"Just putting a voice to the name. Would love 15 minutes if the timing works.\""),
            ("D7 — LinkedIn DM / InMail", "ABM", "\"Hey {{first_name}} — sent a couple of emails about Plum's rewards API. Quick version: one integration gives you 10,000+ rewards in 100+ countries — gift cards, experiences, perks, and more. If {{company_name}} is exploring this, happy to share sandbox access.\""),
            ("D8 — SDR Call 2", "SDR", "Second dial. Voicemail: \"Reached out a few times — just one last try by phone. If rewards infrastructure comes on the roadmap, I'd love to help. All the best.\""),
        ]
    },
    {
        "num": 3,
        "name": "P0 — Empuls / Loyalty / Mixed Product",
        "leads": 93,
        "color": ORANGE,
        "angle": "Broader Xoxoday platform angle. Mixed product signals (Empuls, loyalty, incentives, perks). Copy: problem-first, then Plum API as the primary recommendation.",
        "cadence": [
            ["Day", "Channel", "Step", "Owner", "Auto?"],
            ["D1", "Email", "Email 1 — Platform intro (multi-product)", "ABM", "Smartlead"],
            ["D1", "LinkedIn", "Profile visit", "ABM", "Manual"],
            ["D2", "LinkedIn", "Like/comment on post", "ABM", "Manual"],
            ["D3", "Email", "Email 2 — Use-case alignment", "ABM", "Smartlead"],
            ["D4", "LinkedIn", "Connection request (no note)", "ABM", "Manual"],
            ["D5", "Phone", "SDR Call 1", "SDR", "Manual"],
            ["D6", "Email", "Email 3 — Social proof across use cases", "ABM", "Smartlead"],
            ["D7", "LinkedIn", "DM / InMail", "ABM", "Manual"],
            ["D8", "Phone", "SDR Call 2 + voicemail", "SDR", "Manual"],
            ["D9", "Email", "Email 4 — Direct CTA", "ABM", "Smartlead"],
            ["D11", "Email", "Email 5 — Breakup", "ABM", "Smartlead"],
        ],
        "emails": [
            {
                "step": "Step 1 — Day 0 | Platform Intro",
                "subjects": [
                    "Subject A: {{first_name}}, the rewards problem no one wants to build in-house",
                    "Subject B: Quick question for {{company_name}} on rewards infrastructure"
                ],
                "body": "Hey {{first_name}},\n\nWhether it's employee recognition, customer loyalty, sales incentives, or survey rewards — the pattern is the same: companies build the program logic in-house but don't want to build the rewards catalogue, fulfilment, and compliance layer themselves.\n\nThat's exactly what Xoxoday powers. Our platform — Plum — gives you a single API to access 10,000+ reward options across 100+ countries: gift cards, experiences, merchandise, charity, mobile top-ups, and always-on perks.\n\nCompanies like Viwell, HDB Financial, Nielsen, and Brenntag use it for everything from wellness rewards to banking loyalty to channel incentives.\n\nIf {{company_name}} is running (or planning) any kind of rewards motion, happy to share how teams in your space are doing it. 15 min.\n\n{{sender_first_name}}\nXoxoday"
            },
            {
                "step": "Step 2 — Day 3 | Use-Case Alignment",
                "subjects": ["Subject: Re: {{first_name}}, the rewards problem no one wants to build in-house"],
                "body": "{{first_name}} — quick follow-up.\n\nBased on {{company_name}}'s space, here are the most common use cases we see teams solve with Plum:\n\n- Employee R&R: Peer recognition, service awards, sales SPIFFs — with a global catalogue employees actually want to redeem from\n- Customer loyalty: Open-loop redemption layer for points/cashback programs — your earn engine, our burn engine\n- Survey & market research: Instant, automated incentive delivery to panelists across 100+ countries\n- Channel / partner incentives: Reward distributors, agents, or partners without the gift-card procurement headache\n\nWhich of these (if any) is closest to what {{company_name}} is exploring? Happy to tailor a walkthrough to your specific use case.\n\n{{sender_first_name}}"
            },
            {
                "step": "Step 3 — Day 6 | Social Proof Across Use Cases",
                "subjects": ["Subject: How 3 very different companies use the same rewards API"],
                "body": "Hey {{first_name}},\n\nThree quick examples — same API, very different outcomes:\n\n1. Wellness app (Viwell): Users earn points for healthy behaviours, redeem on Plum's catalogue. Perks API adds zero-cost discounts. Result: 3x redemption rate lift.\n\n2. Neo bank (HDB Financial): Rewards for credit card spending and referrals. Plum handles multi-currency fulfilment with SOC 2 + ISO 27001 compliance. Result: faster go-live than building in-house.\n\n3. Market research firm (Nielsen): Survey panelist incentives delivered instantly in 40+ countries. Replaced manual gift card procurement. Result: 60% reduction in ops overhead.\n\nI'm guessing {{company_name}} doesn't fit exactly into any of these — but the infrastructure is the same. One integration, any use case.\n\nWorth a look?\n\n{{sender_first_name}}\nXoxoday | Plum"
            },
            {
                "step": "Step 4 — Day 9 | Direct CTA",
                "subjects": ["Subject: 15 min to see if Plum fits {{company_name}}"],
                "body": "{{first_name}},\n\nI've sent a few notes and don't want to assume — so here's a direct ask:\n\nIs rewards infrastructure something {{company_name}} is actively exploring this year? If yes, I'd love to set up a 15-min call where I can:\n\n1. Understand your specific use case\n2. Show you a sandbox tailored to it\n3. Share what similar companies have done\n\nIf the timing isn't right, just say so — no hard feelings. I'll circle back later in the year.\n\n{{sender_first_name}}"
            },
            {
                "step": "Step 5 — Day 11 | Breakup",
                "subjects": ["Subject: Wrapping up, {{first_name}}"],
                "body": "Hey {{first_name}},\n\nLast email from me. I know inboxes are brutal.\n\nIf {{company_name}} ever needs a plug-and-play rewards layer — for employees, customers, partners, or anything in between — Xoxoday's here. One API, 10,000+ rewards, 100+ countries.\n\nI'll check back in a quarter. Until then, wishing you and the team all the best.\n\n{{sender_first_name}}\nXoxoday"
            },
        ],
        "manual": [
            ("D1 — LinkedIn Profile Visit", "ABM", "Visit the prospect's LinkedIn profile. Let the notification create a warm signal alongside the email."),
            ("D2 — LinkedIn Like/Comment", "ABM", "Engage with a recent post. 1-2 sentence comment if substantive. No pitch."),
            ("D4 — LinkedIn Connection Request", "ABM / HeyReach", "Clean connection request — no note. Sets up D7 DM."),
            ("D5 — SDR Call 1", "SDR", "Script: \"Hi {{first_name}}, [SDR Name] from Xoxoday. Sent an email about our rewards platform — we help companies power their redemption layer for everything from employee recognition to customer loyalty. Relevant to {{company_name}} right now?\" Voicemail: \"Just putting a voice to the name. Would love 15 min.\""),
            ("D7 — LinkedIn DM / InMail", "ABM", "\"Hey {{first_name}} — sent a couple of emails about Xoxoday's rewards API. One integration gives you 10,000+ rewards in 100+ countries — works for employee R&R, customer loyalty, survey incentives, or channel rewards. Happy to set up a sandbox if relevant.\""),
            ("D8 — SDR Call 2", "SDR", "Second dial. Voicemail: \"Last phone attempt — if rewards come back on the radar, we'd love to help. All the best.\""),
        ]
    },
]

for c in campaigns:
    story.append(PageBreak())
    color = c["color"]
    story.append(Paragraph(f'Campaign {c["num"]}', styles["H1"]))
    story.append(Paragraph(f'<font color="{color}">{c["name"]}</font>', ParagraphStyle("CName", parent=styles["Heading2"], fontSize=14, textColor=color)))
    story.append(Paragraph(f'<b>{c["leads"]} leads</b> | {c["angle"]}', styles["Body"]))
    story.append(hr())

    # Cadence table
    story.append(Paragraph("11-Day Cadence Overview", styles["H2"]))
    story.append(make_cadence_table(c["cadence"]))
    story.append(Spacer(1, 14))

    # Smartlead emails
    story.append(Paragraph("Smartlead Email Steps (Auto-Sent)", styles["H2"]))
    for em in c["emails"]:
        story.append(Spacer(1, 6))
        story.append(Paragraph(em["step"], styles["H3"]))
        for subj in em["subjects"]:
            story.append(Paragraph(subj, styles["SubjectLine"]))
        # Body — preserve newlines
        body_lines = em["body"].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").split("\n")
        body_html = "<br/>".join(body_lines)
        story.append(Paragraph(body_html, styles["EmailBody"]))
        story.append(Spacer(1, 4))

    story.append(PageBreak())

    # Manual touches
    story.append(Paragraph(f"Campaign {c['num']} — Manual Touches (ABM/SDR)", styles["H2"]))
    story.append(Paragraph("These are NOT in Smartlead. Execute via LinkedIn (manual / Dux-Soup / HeyReach) and phone.", styles["Small"]))
    story.append(Spacer(1, 6))
    for touch_name, owner, desc in c["manual"]:
        story.append(Paragraph(f'<b>{touch_name}</b> | Owner: {owner}', styles["H3"]))
        story.append(Paragraph(desc.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"), styles["ManualStep"]))
        story.append(Spacer(1, 4))

# ── FINAL PAGE ──
story.append(PageBreak())
story.append(Paragraph("Next Steps", styles["H1"]))
story.append(hr())
next_steps = [
    "1. Review all 3 campaign sequences above — flag any copy/tone changes.",
    "2. Confirm sender inbox(es) — which Smartlead email accounts should send?",
    "3. Set schedule — timezone, sending window (e.g. 9am-5pm EST, weekdays), max leads/day.",
    "4. Email verification — run through NeverBounce/ZeroBounce first, or send as-is?",
    "5. Once approved: Claude creates 3 campaigns in Smartlead via API, saves sequences, attaches inboxes, uploads leads, and launches.",
]
for ns in next_steps:
    story.append(Paragraph(ns, styles["Body"]))
    story.append(Spacer(1, 4))

story.append(Spacer(1, 20))
story.append(Paragraph("Prepared by Claude | Xoxoday ABM Team | April 2026", styles["CenterNote"]))

# Build
outpath = "/Users/naitikchavda/Event Auto push/smartlead-kit/outputs/P0_Passive_Pipeline_Campaign_Plan.pdf"
doc = SimpleDocTemplate(outpath, pagesize=A4, leftMargin=25*mm, rightMargin=25*mm, topMargin=20*mm, bottomMargin=20*mm)
doc.build(story)
print(f"PDF saved: {outpath}")

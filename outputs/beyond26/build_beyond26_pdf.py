from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import HexColor
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable
)

PURPLE = HexColor("#5B21B6")
DARK = HexColor("#1E293B")
GRAY = HexColor("#64748B")
LIGHT_BG = HexColor("#F8FAFC")
WHITE = HexColor("#FFFFFF")
ACCENT = HexColor("#7C3AED")
GREEN = HexColor("#059669")
BLUE = HexColor("#2563EB")
ORANGE = HexColor("#EA580C")
RED = HexColor("#DC2626")

styles = getSampleStyleSheet()
styles.add(ParagraphStyle("Title2", parent=styles["Title"], fontSize=22, textColor=PURPLE, spaceAfter=6))
styles.add(ParagraphStyle("Sub", parent=styles["Normal"], fontSize=11, textColor=GRAY, spaceAfter=14))
styles.add(ParagraphStyle("H1", parent=styles["Heading1"], fontSize=16, textColor=DARK, spaceBefore=18, spaceAfter=8))
styles.add(ParagraphStyle("H2", parent=styles["Heading2"], fontSize=13, textColor=PURPLE, spaceBefore=14, spaceAfter=6))
styles.add(ParagraphStyle("H3", parent=styles["Heading3"], fontSize=11, textColor=ACCENT, spaceBefore=10, spaceAfter=4))
styles.add(ParagraphStyle("Body", parent=styles["Normal"], fontSize=10, textColor=DARK, leading=14, spaceAfter=6))
styles.add(ParagraphStyle("Small", parent=styles["Normal"], fontSize=9, textColor=GRAY, leading=12, spaceAfter=4))
styles.add(ParagraphStyle("Script", parent=styles["Normal"], fontSize=10, textColor=DARK, leading=14, leftIndent=12, spaceBefore=4, spaceAfter=6, backColor=LIGHT_BG, borderPadding=8))
styles.add(ParagraphStyle("Instr", parent=styles["Normal"], fontSize=9, textColor=GRAY, leading=13, leftIndent=12, spaceAfter=4))
styles.add(ParagraphStyle("Obj", parent=styles["Normal"], fontSize=10, textColor=RED, leading=14, spaceAfter=3, fontName="Helvetica-Bold"))
styles.add(ParagraphStyle("Resp", parent=styles["Normal"], fontSize=10, textColor=DARK, leading=14, leftIndent=12, spaceAfter=8, backColor=LIGHT_BG, borderPadding=6))
styles.add(ParagraphStyle("CenterNote", parent=styles["Normal"], fontSize=9, textColor=GRAY, alignment=TA_CENTER, spaceAfter=10))

def hr():
    return HRFlowable(width="100%", thickness=0.5, color=HexColor("#E2E8F0"), spaceAfter=8, spaceBefore=8)

def make_table(data, col_widths=None, header_color=DARK):
    t = Table(data, colWidths=col_widths or [140, 320], repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), header_color),
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

# COVER
story.append(Spacer(1, 60))
story.append(Paragraph("Beyond 2026 Campaign", styles["Title2"]))
story.append(Paragraph("Post-Event Outreach to 47 AI & Data Leaders", styles["Title2"]))
story.append(Spacer(1, 10))
story.append(Paragraph("Event: 3AI Beyond 2026 | Theme: #TheAIsupremacy | Venue: Radisson Blu ORR Bengaluru", styles["Sub"]))
story.append(hr())
story.append(Spacer(1, 16))

cover_info = [
    ["Field", "Value"],
    ["Campaign name", "P0_EVNTS_Beyond26Speakers_IND_EMAIL-LI-WP-CALL_AbhimanNaitik24Apr2026"],
    ["Priority", "P0 (Critical, CXO-level, 48-hour launch window)"],
    ["Team", "EVENTS"],
    ["Use case", "Beyond26Speakers (custom post-event outreach)"],
    ["Region", "India"],
    ["Channels", "Email + LinkedIn + WhatsApp + Call"],
    ["POCs", "Abhiman + Naitik"],
    ["Event date", "Friday, 24 April 2026, 08:30-17:30 IST"],
    ["Target list", "HubSpot list ID 26550 (47 contacts)"],
    ["Smartlead campaign ID", "3226524 (paused)"],
    ["HeyReach list ID", "633010 (paused)"],
]
story.append(make_table(cover_info))

# EVENT CONTEXT
story.append(PageBreak())
story.append(Paragraph("Event Context", styles["H1"]))
story.append(Paragraph("Beyond 2026 is the 4th edition of 3AI's annual India summit focused on applied AI, analytics, and GCC leadership. Hosted by 3AI, India's largest platform for AI and GCC leaders representing 1,700+ thought leaders across 980+ organisations and 58,000+ active members globally.", styles["Body"]))
story.append(Paragraph("This year's theme, #TheAIsupremacy, centres on competitive advantage through AI innovation. The agenda covers enterprise transformation, GCC innovation, business function optimisation, and strategic AI deployment across BFSI, retail, healthcare, manufacturing, and technology.", styles["Body"]))

event_details = [
    ["Detail", "Value"],
    ["Date", "Friday, 24 April 2026 (08:30-17:30 IST)"],
    ["Venue", "Radisson Blu ORR, Marathahalli, Bengaluru"],
    ["Delegates", "100+ (50+ CXOs)"],
    ["Speakers", "50+ senior AI, data, analytics leaders"],
    ["Host", "3AI"],
    ["Awards", "ACME Awards run parallel (top AI organisations and professionals)"],
    ["Website", "beyond.3ai.in"],
]
story.append(make_table(event_details))

# WHY THIS LIST
story.append(Paragraph("Why This Audience Matters", styles["H1"]))
story.append(Paragraph("Speakers at Beyond 2026 are Vice Presidents, Directors, and C-suite leaders running the AI, analytics, and data strategy at some of the largest enterprises operating in India. They are not the typical direct buyers for Xoxoday's rewards and loyalty products, but they sit next to the functions that are: Marketing (customer loyalty, campaign rewards), HR (employee R&R), CX (consumer loyalty programs), Sales Ops (partner and channel incentives).", styles["Body"]))
story.append(Paragraph("The play is two-pronged:", styles["Body"]))
story.append(Paragraph("1. Build relationships with senior AI leaders as long-term champions inside their companies.", styles["Body"]))
story.append(Paragraph("2. Use them as a warm intro path to the right buyer at the same company.", styles["Body"]))

story.append(Paragraph("Pitch Angle", styles["H2"]))
story.append(Paragraph('"You build the AI that drives how customers, employees, and partners experience your company. We build the rewards and loyalty layer on top that turns AI-driven insight into an actual experience. Plum (rewards API), Empuls (employee R&R), Loyalife (consumer loyalty)."', styles["Script"]))

# TARGET LIST
story.append(PageBreak())
story.append(Paragraph("Target List (47 Speakers)", styles["H1"]))
story.append(Paragraph("Distribution across industries:", styles["Body"]))
industry_data = [
    ["Industry", "Count", "Notable Companies"],
    ["BFSI", "12", "Swiss Re, Standard Chartered, Citi, Citigroup, First Citizens, Broadridge, Marsh, TMF Group"],
    ["IT Services / GCC / Consulting", "14", "EXL, Datamatics, Kyndryl India, HCLTech, LTIMindtree, Damco, ANSR, BCG, Microsoft, Fractal.AI, 3AI, Symplr, Vivish"],
    ["Retail / CPG / Food", "6", "Albertsons, Lowe's India, Landmark Group, Jubilant FoodWorks, Kenvue"],
    ["Healthcare / Pharma", "3", "Carelon, Viatris, Kenvue"],
    ["Manufacturing / Chemicals", "4", "UltraTech, Birla Carbon, Aditya Birla, Linde"],
    ["Media / Consumer Internet", "1", "JioHotstar"],
    ["Oil & Energy", "1", "Shell"],
    ["Other / Misc", "6", "Various"],
]
story.append(make_table(industry_data, col_widths=[140, 50, 270]))

story.append(Paragraph("Data Quality Summary", styles["H2"]))
dq = [
    ["Metric", "Value"],
    ["Total speakers on list", "47"],
    ["Verified work emails", "35 (74%)"],
    ["LinkedIn URLs", "37 (79%)"],
    ["Mobile phone numbers (Clay waterfall)", "~35"],
    ["Fully enriched (email + LinkedIn + phone)", "30+"],
]
story.append(make_table(dq))

# CADENCE OVERVIEW
story.append(PageBreak())
story.append(Paragraph("14-Day Multi-Channel Cadence", styles["H1"]))
cadence = [
    ["Day", "Channel", "Action", "Platform"],
    ["D1 (25 Apr)", "Email", "Email 1 - Congrats on Beyond 2026", "Smartlead"],
    ["D1", "LinkedIn", "Profile visit (automatic)", "HeyReach"],
    ["D2", "LinkedIn", "Like recent post", "HeyReach / manual"],
    ["D4", "LinkedIn", "Connection request (NO note)", "HeyReach"],
    ["D4 (28 Apr)", "Email", "Email 2 - AI + rewards pattern", "Smartlead"],
    ["D5 (29 Apr)", "Phone", "SDR Call 1", "Manual / Frejun"],
    ["D7 (1 May)", "Email", "Email 3 - Three production examples", "Smartlead"],
    ["D7", "LinkedIn", "DM (if connected) / InMail", "HeyReach"],
    ["D9 (3 May)", "Phone", "SDR Call 2 + voicemail", "Manual / Frejun"],
    ["D10 (4 May)", "Email", "Email 4 - Direct CTA", "Smartlead"],
    ["D10", "LinkedIn", "Follow-up DM / value add", "HeyReach"],
    ["D14 (8 May)", "Email", "Email 5 - Breakup", "Smartlead"],
]
t = Table(cadence, colWidths=[70, 60, 270, 90], repeatRows=1)
t.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, 0), PURPLE),
    ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ("FONTSIZE", (0, 0), (-1, -1), 9),
    ("LEADING", (0, 0), (-1, -1), 11),
    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ("GRID", (0, 0), (-1, -1), 0.4, HexColor("#CBD5E1")),
    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT_BG]),
    ("TOPPADDING", (0, 0), (-1, -1), 4),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
]))
story.append(t)

# EMAIL SEQUENCE
story.append(PageBreak())
story.append(Paragraph("Email Sequence (5 Steps in Smartlead)", styles["H1"]))

emails = [
    ("Step 1 - Day 1 (25 Apr)", ["{{first_name}}, enjoyed the Beyond 2026 lineup", "Your session at Beyond 2026, {{first_name}}"],
     "Hi {{first_name}},\n\nQuick note after Beyond 2026. The speaker lineup this year was one of the sharpest India has had on applied AI and analytics, and it is clear why 3AI put you on stage.\n\nReason I am reaching out: you work on the intelligence layer that drives how customers, employees, and partners experience {{company_name}}. My team at Xoxoday works on the other half of that equation, the rewards and loyalty layer that companies use to convert all that AI-driven insight into an actual experience (loyalty points, campaign rewards, employee recognition, channel incentives).\n\nIt plugs into the CRM, marketing automation, and HRIS stack most GCCs already run. 10,000+ reward options across 100+ countries, one API.\n\nNo pitch here. Would be good to know who at {{company_name}} owns the rewards or loyalty side, in case an intro makes sense. Or if it is you, even better.\n\nBest,\n{{sender_first_name}}\nXoxoday | Plum, Empuls, Loyalife"),
    ("Step 2 - Day 4 (28 Apr)", ["Re: {{first_name}}, enjoyed the Beyond 2026 lineup"],
     "{{first_name}},\n\nFollowing up with something more specific to your space.\n\nOne pattern we see repeatedly with GCC and global enterprise teams in India:\n\n1. Marketing builds AI-driven journeys on Netcore, CleverTap, Salesforce Marketing Cloud, or Adobe Experience Cloud.\n2. HR rolls out AI-informed engagement surveys, sentiment tracking, and personalisation on their HCM.\n3. Revenue Ops uses AI for sales forecasting and partner management.\n\nAll three teams end up needing the same thing downstream: a reward catalogue that actually scales across geographies and a platform to deliver it without manual procurement.\n\nThat is where Xoxoday fits. Plum (API-first rewards), Empuls (employee R&R), Loyalife (consumer loyalty).\n\nCompanies in your orbit already using us: HDB Financial, Freshworks, Nielsen, Aditya Birla Capital, Jubilant, Brenntag.\n\nWorth a 15-min chat, or happy to just share a 2-min Loom.\n\n{{sender_first_name}}"),
    ("Step 3 - Day 7 (1 May)", ["How AI-driven rewards look in production"],
     "Hi {{first_name}},\n\nSince your talk at Beyond 2026 touched on AI in production, thought this might be interesting.\n\nThe part of the stack that is least talked about but arguably the most visible to the end user is the reward / recognition moment. Three short examples from our customers:\n\n1. Banking: AI scores a customer's referral likelihood, triggers a points reward via Plum API at the right moment. Redemption happens on a 100+ country catalogue. No manual gift card procurement, no finance tickets.\n\n2. Retail: AI predicts churn risk on loyalty members, fires a targeted reward through Loyalife. Reactivation rates lift 2 to 3x vs generic coupons.\n\n3. GCC employee experience: AI-powered sentiment analysis on Empuls triggers manager-led recognition. Reduces time-to-recognition from weeks to hours.\n\nNot a sales pitch, just sharing what we see working. If any of this is relevant at {{company_name}}, happy to dig in further.\n\n{{sender_first_name}}"),
    ("Step 4 - Day 10 (4 May)", ["15 min to explore if Xoxoday fits {{company_name}}"],
     "{{first_name}},\n\nDirect ask.\n\nIs rewards, recognition, or loyalty infrastructure on {{company_name}}'s roadmap this year? If yes, would 15 minutes next week work to:\n\n1. Understand what is currently in place\n2. Show a sandbox tailored to your stack\n3. Introduce you to the customers solving the closest problem\n\nIf you are not the owner but can point me to the right person (marketing, HR, CX, sales ops), that works too.\n\nIf timing is off, no hard feelings. I will circle back later.\n\n{{sender_first_name}}"),
    ("Step 5 - Day 14 (8 May)", ["Closing the loop, {{first_name}}"],
     "Hi {{first_name}},\n\nLast note from me on this thread.\n\nIf {{company_name}} ever needs a rewards API, a loyalty platform, or an employee R&R layer, Xoxoday is a quick conversation away. Plug-and-play with the AI-driven stack you are already building.\n\nAppreciated the work you shared at Beyond 2026. Will keep an eye out for the next one.\n\nBest,\n{{sender_first_name}}\nXoxoday | Plum, Empuls, Loyalife"),
]
for step, subjects, body in emails:
    story.append(Paragraph(step, styles["H3"]))
    for s in subjects:
        story.append(Paragraph(f"<b>Subject:</b> {s}", styles["Body"]))
    body_html = body.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br/>")
    story.append(Paragraph(body_html, styles["Script"]))

# LINKEDIN SEQUENCE
story.append(PageBreak())
story.append(Paragraph("LinkedIn Sequence (5 Steps in HeyReach)", styles["H1"]))
story.append(Paragraph("Runs in parallel with email, same Day 1 start (25 Apr).", styles["Small"]))

story.append(Paragraph("Day 1 - Profile Visit", styles["H3"]))
story.append(Paragraph("Automatic via HeyReach. No message.", styles["Body"]))

story.append(Paragraph("Day 2 - Like Recent Post", styles["H3"]))
story.append(Paragraph('Look for Beyond 2026 share or recap post. Like it. Optionally comment one line like "Strong lineup this year" or "Agreed on the agentic AI production point."', styles["Body"]))

story.append(Paragraph("Day 4 - Connection Request (NO note)", styles["H3"]))
story.append(Paragraph("Clean connection request. Empty note field.", styles["Body"]))

story.append(Paragraph("Day 7 - DM (if connected) / InMail (if not)", styles["H3"]))
story.append(Paragraph("<b>InMail subject:</b> Beyond 2026 + a quick thought, {{first_name}}", styles["Body"]))
dm1 = "Hey {{first_name}},\n\nCaught your session at Beyond 2026 this week. Strong lineup across the board.\n\nQuick context on why I connected. I run outbound for Xoxoday. We power the rewards and loyalty layer (APIs, employee R&R platforms, consumer loyalty) that companies plug onto their AI-driven engagement stack.\n\nYou are not the usual buyer for this, but you sit next to the teams who are (marketing, HR, CX). If rewards, recognition, or loyalty is in scope at {{company_name}} this year, an intro to the right person would go a long way. Or if it is you, even better.\n\nSent you an email earlier with a bit more context. No pressure if the timing is off.\n\n{{sender_first_name}}\nXoxoday"
story.append(Paragraph(dm1.replace("\n", "<br/>"), styles["Script"]))

story.append(Paragraph("Day 10 - Follow-up DM / Value Add", styles["H3"]))
dm2 = "{{first_name}}, one more and I will stop filling your inbox.\n\nQuick set of customer examples in case any are relevant at {{company_name}}:\n\n1. Banking rewards (HDB Financial): AI-triggered referral rewards via Plum API, redemption across 100+ countries.\n2. Retail loyalty (Landmark, Jubilant): Loyalife running the member dashboard, points logic, and segmentation.\n3. GCC employee experience (Brenntag, Freshworks, Bosch): Empuls for peer recognition and service awards across global teams.\n\nIf any of these angles line up with a problem you or a peer at {{company_name}} is looking at, a 15-min intro call would be useful.\n\nOtherwise no worries, enjoy the weekend.\n\n{{sender_first_name}}"
story.append(Paragraph(dm2.replace("\n", "<br/>"), styles["Script"]))

# CALL SCRIPTS
story.append(PageBreak())
story.append(Paragraph("Call Scripts", styles["H1"]))
story.append(Paragraph("Two dial attempts during the 14-day window: Day 5 (29 Apr) and Day 9 (3 May). Always reference Beyond 2026 in the first 15 seconds, along with any email or LinkedIn touches already made.", styles["Small"]))

story.append(Paragraph("Pre-Call Prep (30 sec)", styles["H2"]))
prep = [
    "Confirm their speaker topic from Beyond 2026 agenda",
    "Check LinkedIn for post-event posts (share, recap, photos)",
    "Confirm company, role, industry",
    "Check if any email from the sequence has been opened (Smartlead tracking)",
]
for p in prep:
    story.append(Paragraph(f"- {p}", styles["Body"]))

story.append(Paragraph("Call 1 - Day 5 (29 Apr)", styles["H2"]))
story.append(Paragraph("Opening", styles["H3"]))
story.append(Paragraph('"Hi {{first_name}}, this is [YOUR NAME] from Xoxoday. Have I caught you at a bad time? I will keep it quick."', styles["Script"]))
story.append(Paragraph("If bad time:", styles["Instr"]))
story.append(Paragraph('"Totally understand. What is a better 2-minute window, today or tomorrow? I will call back."', styles["Script"]))

story.append(Paragraph("Purpose (20 sec)", styles["H3"]))
story.append(Paragraph('"Thanks. I caught you speaking at Beyond 2026 last Friday, strong session. I am working with a few AI and data leaders in India whose companies are starting to rethink the rewards and loyalty layer on top of their AI-driven engagement stack. Wanted to get your perspective, and possibly an intro to the right owner at {{company_name}}."', styles["Script"]))

story.append(Paragraph("Discovery (4 questions)", styles["H3"]))
discovery = [
    '"Quick one, does rewards, recognition, or loyalty sit anywhere near your charter at {{company_name}}, or is it fully on the marketing or HR side?"',
    '"If you had to guess, how is it handled today? In-house platform, point solution, manual procurement, or something else?"',
    '"On a scale of 1 to 10, how much of a priority is this for {{company_name}} this year?"',
    '"Who at {{company_name}} would be the best person for me to speak with, Marketing, HR, CX, or Sales Ops? I would love an intro if you are open to it."',
]
for d in discovery:
    story.append(Paragraph(d, styles["Script"]))

story.append(Paragraph("Pitch (30 sec)", styles["H3"]))
story.append(Paragraph('"{{first_name}}, based on what you shared, we do three things that would be relevant: One, Plum, an API for rewards delivery across 100+ countries. Two, Empuls, an employee recognition and engagement platform. Three, Loyalife, a full consumer loyalty platform for brands running multi-tier customer programs. Customers you would recognise: HDB Financial, Freshworks, Nielsen, Aditya Birla, Jubilant."', styles["Script"]))

story.append(Paragraph("CTA (15 sec)", styles["H3"]))
story.append(Paragraph('"Two asks. One, if rewards or loyalty is on the roadmap at {{company_name}} this year, can we set up a 15-minute walkthrough next week? Two, if not, can I get 30 seconds on the right person to reach out to? I will use your name if that is okay."', styles["Script"]))

story.append(Paragraph("Call 2 - Day 9 (3 May)", styles["H2"]))
story.append(Paragraph("Only if no pickup on Call 1.", styles["Small"]))
story.append(Paragraph('"Hi {{first_name}}, [YOUR NAME] from Xoxoday again. Sent you a voicemail and a couple of emails last week about rewards and loyalty infrastructure, post Beyond 2026. Wanted to try once more before I stop. Is this a better time?"', styles["Script"]))

story.append(Paragraph("Voicemail (if no pickup)", styles["H3"]))
story.append(Paragraph('"Hey {{first_name}}, [YOUR NAME] from Xoxoday. Caught your Beyond 2026 session, reached out last week about the rewards side. Last call from me on this. If it is relevant for {{company_name}} this year, just reply to the email. Otherwise no hard feelings, appreciate the work you are doing. Thanks."', styles["Script"]))

# OBJECTIONS
story.append(PageBreak())
story.append(Paragraph("Objection Handlers", styles["H1"]))

objections = [
    ('"I do not own rewards or loyalty"',
     '"Got it, expected that given your role. Who at {{company_name}} would be the right person, Marketing, HR, CX, or someone else? Happy to reach out directly and mention your name so it is warm. 30 seconds of your time."'),
    ('"We have a vendor already"',
     '"Which one, if you do not mind me asking? Most teams we speak with are using Capillary, Vantage Circle, or a Salesforce Loyalty Cloud setup, and we hear specific gaps around global catalogue, AI integration depth, or multi-product coverage. Worth a 15-min comparison just so you know the alternatives."'),
    ('"We are not buying anything this year"',
     '"Completely fair. I am not asking you to buy, I am asking if it is worth 20 minutes to see what peer companies are doing so when budget does come up at {{company_name}} you are not starting from zero."'),
    ('"Send me an email"',
     '"Already in your inbox. Rather than send a second generic one, which of the three is most relevant to share a deeper cut on: Plum (rewards API), Empuls (employee R&R), or Loyalife (consumer loyalty)?"'),
    ('"How did you find my number?"',
     '"Public data, your speaker listing on beyond.3ai.in plus standard enrichment. Not spam, targeted outreach because your role overlaps with what we solve. Happy to remove you from my list if you prefer."'),
    ('"Call me after the quarter"',
     '"Sure, let me book it now so it does not slip. What week in July works?" (Book the callback specifically.)'),
]
for title, response in objections:
    story.append(Paragraph(title, styles["Obj"]))
    story.append(Paragraph(response, styles["Resp"]))

# SDR QUICK NOTES
story.append(PageBreak())
story.append(Paragraph("Quick Notes for the SDR Team", styles["H1"]))
notes = [
    "Always reference Beyond 2026 in the first 15 seconds. This is not a cold call, it is a post-event follow-up. Treat it as such.",
    "These are senior people (VP+, C-suite). Tone is peer-to-peer, not transactional. No 'touching base' or 'circling back' filler language.",
    "The ask is often an intro, not a meeting. If they point you to the right person internally, that is a win.",
    "Skip the feature dump. Name the 3 products in one line if asked, then shut up and listen.",
    "Data quality flag: Not all 47 speakers have valid emails. Prioritise the 35 verified emails first. Use LinkedIn and phone for the rest.",
    "Log every call in HubSpot against the contact record. Our dashboard splits attribution by channel (Cold Email, LinkedIn, Cold Call).",
    "If they change companies, do not keep pushing. Pause and let the next outreach be at the new employer (check Apollo job change flags).",
    "No em dashes or en dashes in any written follow-up (use hyphens, commas, or rewrite).",
]
for n in notes:
    story.append(Paragraph(f"- {n}", styles["Body"]))

# PLATFORM STATUS
story.append(Paragraph("Platform Status", styles["H1"]))
status = [
    ["Platform", "Status", "Next Step"],
    ["HubSpot List", "Created, 47 contacts (list ID 26550)", "Source of truth, no action"],
    ["Smartlead Campaign", "Created (ID 3226524), paused. Sequence saved, 50 India-region accounts attached, IST schedule set, stop-on-reply on. No leads yet.", "Open campaign in Smartlead UI, Leads tab > Import from CRM > select HubSpot list P0_EVNTS_Beyond26Speakers_IND_EMAIL-LI-WP-CALL_AbhimanNaitik24Apr2026, map Email field, import. Then review and flip to START."],
    ["HeyReach List", "Created (ID 633010, name P0_EVNTS_Beyond26_IND_LI_AbhimanNaitik_24Apr26). HeyReach API throwing errors on bulk upload right now.", "Drag-drop heyreach_beyond26_upload.csv into the HeyReach UI list (outputs/beyond26/). Then create campaign with the 5-step LinkedIn cadence. Sender: Gaurav Sava's account or Naitik's."],
    ["SDR Calls", "Scripts ready (this doc)", "Day 5 (29 Apr) and Day 9 (3 May) dial attempts per contact. Log dispositions in HubSpot."],
]
t = Table(status, colWidths=[90, 180, 200], repeatRows=1)
t.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, 0), DARK),
    ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ("FONTSIZE", (0, 0), (-1, -1), 8.5),
    ("LEADING", (0, 0), (-1, -1), 11),
    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
    ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ("GRID", (0, 0), (-1, -1), 0.4, HexColor("#CBD5E1")),
    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT_BG]),
    ("TOPPADDING", (0, 0), (-1, -1), 5),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
]))
story.append(t)

story.append(Spacer(1, 20))
story.append(Paragraph("Xoxoday | GTM and Outbound Team | Internal Use Only | Prepared 24 April 2026", styles["CenterNote"]))

outpath = "/Users/naitikchavda/Event Auto push/smartlead-kit/outputs/beyond26/Beyond26_Campaign_Sales_Team_Brief.pdf"
doc = SimpleDocTemplate(outpath, pagesize=A4,
                        leftMargin=22*mm, rightMargin=22*mm,
                        topMargin=20*mm, bottomMargin=20*mm)
doc.build(story)
print(f"Saved: {outpath}")

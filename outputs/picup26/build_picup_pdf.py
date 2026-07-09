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
RED = HexColor("#DC2626")
BLUE = HexColor("#2563EB")
GREEN = HexColor("#059669")

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
story.append(Paragraph("PICUP Fintech 2026", styles["Title2"]))
story.append(Paragraph("Post-Event Campaign Brief", styles["Title2"]))
story.append(Spacer(1, 10))
story.append(Paragraph("6th edition | FICCI + IBA | BCG knowledge partner | 23 April 2026 New Delhi", styles["Sub"]))
story.append(hr())
story.append(Spacer(1, 16))

cover = [
    ["Field", "Value"],
    ["Campaign name", "P0_EVNTS_PICUP26_IND_EMAIL-LI-CALL_naitik_24APR26"],
    ["Priority", "P0 (post-event, time-sensitive)"],
    ["Team", "EVENTS"],
    ["Region", "India"],
    ["Channels", "Email + LinkedIn + Phone"],
    ["POC", "Naitik"],
    ["Smartlead Campaign ID", "3265336 (paused)"],
    ["HeyReach List ID", "645382 (empty, awaiting LinkedIn enrichment)"],
    ["Source list", "PICUP Fintech Awards CSV (7 leads)"],
    ["Sendable via email", "4 of 7 (rest need phone or skip)"],
]
story.append(make_table(cover))

# EVENT
story.append(PageBreak())
story.append(Paragraph("Event Context", styles["H1"]))
story.append(Paragraph("The 6th PICUP Fintech Conference and Awards 2026 was jointly organised by the Indian Banks Association (IBA) and the Federation of Indian Chambers of Commerce and Industry (FICCI) on 23 April 2026 at Federation House, New Delhi. Boston Consulting Group (BCG) was the Knowledge Partner. Shri M. Nagaraju, Secretary, Department of Financial Services, Government of India, delivered the inaugural address.", styles["Body"]))
story.append(Paragraph("The agenda focused on Generative AI in lending, Digital Public Infrastructure, Credit Line on UPI (CLOU), responsible AI in financial services, and customer engagement. Audience: banks, fintechs, NBFCs, insurance companies, technology providers, and policymakers.", styles["Body"]))

themes = [
    ["Theme", "Why it matters for our outreach"],
    ["GenAI in lending and underwriting", "Most banks now have sharp AI decisioning. Customer-side experience post-approval is the weak link."],
    ["Digital Public Infrastructure / CLOU", "UPI orchestration is mature. Reward layer on top is still manual at most fintechs."],
    ["Customer engagement and personalisation", "Direct fit for Plum and Loyalife - this is the wedge."],
    ["Responsible AI", "Compliance posture matters. SOC 2, ISO 27001, GDPR, RBI alignment all relevant."],
]
story.append(make_table(themes, col_widths=[180, 280]))

# TARGET LIST
story.append(PageBreak())
story.append(Paragraph("Target List (7 leads)", styles["H1"]))
story.append(Paragraph("Source CSV had 7 attendee names. 4 have valid work emails and go into Smartlead. 2 are phone-only (PNB Marketing and BCG Marketing) and need direct SDR call. 1 has insufficient data and is on hold.", styles["Body"]))

leads = [
    ["#", "Name", "Title", "Company", "Email", "Phone", "Fit"],
    ["1", "Digvijay Singh", "Mgr Corp Relations", "JK Lakshmipur Univ", "Yes", "8127766668", "Edge"],
    ["2", "Vivek Kumar Sagar", "Marketing", "Business Next", "Yes", "9979768628", "Edge"],
    ["3", "Nikhil Kochhar", "Sr Mgr Sales", "Perfios", "Yes", "8375061168", "Strong"],
    ["4", "Priyam Garg", "(blank)", "Nucleus Software", "Yes", "9560335306", "Strong"],
    ["5", "Rajni", "(unclear)", "(unknown)", "No", "9731905732", "Skip"],
    ["6", "Mithlesh", "Marketing", "PNB", "No", "7541806998", "Strong, phone"],
    ["7", "Ishmeet", "Marketing", "BCG", "No", "9210067468", "Warmest, phone"],
]
t = Table(leads, colWidths=[20, 100, 95, 110, 35, 65, 50], repeatRows=1)
t.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, 0), DARK),
    ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ("FONTSIZE", (0, 0), (-1, -1), 8),
    ("LEADING", (0, 0), (-1, -1), 10),
    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
    ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ("GRID", (0, 0), (-1, -1), 0.4, HexColor("#CBD5E1")),
    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT_BG]),
    ("TOPPADDING", (0, 0), (-1, -1), 4),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
]))
story.append(t)

story.append(Paragraph("Pitch Angle", styles["H2"]))
story.append(Paragraph('"Banks and fintechs are moving fast on AI underwriting, UPI orchestration, and Credit Line on UPI. The customer engagement layer that sits on top of all that decisioning is still mostly manual. That is where Plum and Loyalife fit."', styles["Script"]))
story.append(Paragraph("Use Xoxoday only as a credibility signal, not a pitch. Customer names that resonate: HDB Financial, Fino Payments Bank, AU Small Finance Bank.", styles["Body"]))

# EMAIL SEQUENCE
story.append(PageBreak())
story.append(Paragraph("Email Sequence (Smartlead)", styles["H1"]))
story.append(Paragraph("5 steps over 13 days. IST Mon-Fri 9am-6pm, 10 leads/day, stop on reply. No signature in body (Smartlead handles).", styles["Small"]))

emails = [
    ("Step 1 - Day 0 (24 Apr)", "PICUP follow up",
     "Caught the PICUP Fintech recap and saw {{company_name}} was in the room.\n\nMost banks I speak with say their AI underwriting is sharp but post-approval engagement stays manual.\n\nPlum handles that layer for HDB and Fino across credit and savings rewards.\n\nCurious whether {{company_name}} has solved this internally or it is still open?"),
    ("Step 2 - Day 3 (27 Apr)", "Re: PICUP follow up",
     "{{first_name}}, quick follow up.\n\nThe pattern across BFSI in India: AI decisioning gets sharper every quarter, but the moment a customer earns a reward or hits a milestone, it falls back to manual gift card flows.\n\nProcurement loops, finance approvals, single-currency catalogues.\n\nHDB moved that work to Plum last year and pulled two FTE-weeks back per month.\n\nWorth a 15-min look?"),
    ("Step 3 - Day 6 (30 Apr)", "One BFSI example",
     "Hi {{first_name}},\n\nSince the BFSI patterns at PICUP repeated themselves, one specific example.\n\nFino Payments Bank uses Plum for referral and milestone rewards, including the multi-currency NRI segment.\n\nAudit trail per transaction, RBI-aligned catalogue, no vendor sprawl.\n\nSame shape works for credit cards, savings, BNPL, insurance partnerships.\n\nDoes {{company_name}} run into similar friction on the rewards side?"),
    ("Step 4 - Day 9 (3 May)", "15 minutes, {{first_name}}",
     "{{first_name}},\n\nDirect ask.\n\nIs rewards or loyalty on {{company_name}}'s 2026 roadmap?\n\nThree options:\n1. Yes, you own it. 15 minutes next week.\n2. Yes, someone else owns it. Point me to them.\n3. Not this year. Fair, I will circle back in Q3.\n\nWhich one?"),
    ("Step 5 - Day 13 (7 May)", "Closing the loop",
     "Hi {{first_name}},\n\nLast one from me.\n\nIf rewards or customer engagement comes up at {{company_name}} later this year, Plum and Loyalife are already integrated with the BFSI stacks most fintechs and banks in India run.\n\nAppreciated the work the speakers shared at PICUP.\n\nWill keep an eye out for the next one."),
]
for step, subj, body in emails:
    story.append(Paragraph(step, styles["H3"]))
    story.append(Paragraph(f"<b>Subject:</b> {subj}", styles["Body"]))
    body_html = body.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br/>")
    story.append(Paragraph(body_html, styles["Script"]))

# LINKEDIN
story.append(PageBreak())
story.append(Paragraph("LinkedIn Sequence (HeyReach)", styles["H1"]))
story.append(Paragraph("5 steps, runs in parallel with email. Sender: Gaurav Sava or Naitik. NOTE: HeyReach list 645382 is empty until LinkedIn URLs are enriched (Apollo run pending).", styles["Small"]))

story.append(Paragraph("Day 1 - Profile Visit", styles["H3"]))
story.append(Paragraph("Automatic. No message.", styles["Body"]))

story.append(Paragraph("Day 2 - Like Recent Post", styles["H3"]))
story.append(Paragraph("Look for any PICUP recap. Like it. Optional one-line comment if substantive.", styles["Body"]))

story.append(Paragraph("Day 4 - Connection Request (NO note)", styles["H3"]))
story.append(Paragraph("Empty note. No pitch in the request.", styles["Body"]))

story.append(Paragraph("Day 7 - DM (if connected) or InMail (if not)", styles["H3"]))
story.append(Paragraph("<b>InMail Subject:</b> PICUP Fintech, {{first_name}}", styles["Body"]))
dm1 = "Hey {{first_name}},\n\nCaught the PICUP recap this week. Strong agenda, especially the CLOU and GenAI lending sessions.\n\nQuick reason I connected. I run BFSI outbound for Xoxoday. Plum is the rewards API HDB, Fino, and AU Small Finance use for credit, savings, and referral rewards.\n\nIt is the layer that sits on top of the AI decisioning every fintech is building. RBI-aligned catalogue, multi-currency for cross-border.\n\nIf rewards or loyalty is in scope at {{company_name}} this year, an intro to the right person would help. Or if it is you, even better.\n\n{{sender_first_name}}\nXoxoday"
story.append(Paragraph(dm1.replace("\n", "<br/>"), styles["Script"]))

story.append(Paragraph("Day 10 - Follow-up DM", styles["H3"]))
dm2 = "{{first_name}}, one more then I will stop.\n\nThree short examples in case any line up with what {{company_name}} is building:\n\n1. HDB Financial: card and savings rewards via Plum API, ops down 80%, redemption up 3x.\n2. Fino Payments Bank: referral and milestone rewards, multi-currency for NRI segment.\n3. AU Small Finance: tiered customer loyalty on Loyalife, full member dashboard.\n\nIf any of these shapes match a roadmap item at {{company_name}}, 15 minutes is enough to know. Otherwise no worries.\n\n{{sender_first_name}}"
story.append(Paragraph(dm2.replace("\n", "<br/>"), styles["Script"]))

# CALLS
story.append(PageBreak())
story.append(Paragraph("Call Scripts", styles["H1"]))
story.append(Paragraph("Two dial attempts: Day 5 (29 Apr) and Day 9 (3 May). Reference PICUP in the first 15 seconds.", styles["Small"]))

story.append(Paragraph("Pre-Call Prep (30 sec)", styles["H2"]))
prep = [
    "Confirm prospect's company segment (bank, NBFC, fintech, insurance, vendor)",
    "Check LinkedIn for any PICUP recap post",
    "Check Smartlead for email-open status",
]
for p in prep:
    story.append(Paragraph(f"- {p}", styles["Body"]))

story.append(Paragraph("Call 1 - Day 5 (29 Apr)", styles["H2"]))
story.append(Paragraph("Opening", styles["H3"]))
story.append(Paragraph('"Hi {{first_name}}, this is [YOUR NAME] from Xoxoday. Have I caught you at a bad time?"', styles["Script"]))
story.append(Paragraph("Purpose", styles["H3"]))
story.append(Paragraph('"Quick reason for the call. I work with banks and fintechs in India on the rewards and loyalty side of customer engagement, the bit that sits on top of UPI, CLOU, and the AI underwriting work most teams are doing. Wanted to get your perspective on how {{company_name}} handles it today."', styles["Script"]))

story.append(Paragraph("Discovery (4 questions)", styles["H3"]))
discovery = [
    '"Quick one, does customer rewards or loyalty sit anywhere near your charter, or is it on the marketing or product side?"',
    '"How is it handled today - in-house build, point vendor, or manual gift card procurement?"',
    '"On a scale of 1 to 10, how much of a priority is customer engagement infrastructure for {{company_name}} this year?"',
    '"Who would be the right person internally if not you - Marketing, CX, Product, Loyalty?"',
]
for d in discovery:
    story.append(Paragraph(d, styles["Script"]))

story.append(Paragraph("Pitch (30 sec)", styles["H3"]))
story.append(Paragraph('"Three things we do that are relevant. One, Plum, an API for rewards delivery, used by HDB, Fino, AU Small Finance. Two, Loyalife, a full multi-tier consumer loyalty platform. Three, Compass, agent and channel commission automation if {{company_name}} runs distribution partners. RBI-compliant Indian catalogue, SOC 2, ISO 27001."', styles["Script"]))

story.append(Paragraph("CTA", styles["H3"]))
story.append(Paragraph('"Two asks. If rewards or loyalty is on the roadmap, can we set up 15 minutes next week? If not, can I get the right name internally? I will mention you."', styles["Script"]))

story.append(Paragraph("Call 2 - Day 9 (3 May)", styles["H2"]))
story.append(Paragraph("Only if no pickup on Call 1.", styles["Small"]))
story.append(Paragraph('"Hi {{first_name}}, [YOUR NAME] from Xoxoday again. Sent a voicemail and a couple of emails last week about rewards and loyalty post PICUP Fintech. Last try by phone before I stop. Better time now?"', styles["Script"]))

story.append(Paragraph("Voicemail", styles["H3"]))
story.append(Paragraph('"Hey {{first_name}}, [YOUR NAME] from Xoxoday. Caught PICUP Fintech this week, reached out about rewards and loyalty for {{company_name}}. Last call from me on this. If it is relevant this year, just reply to the email. Otherwise no hard feelings, appreciate the work. Thanks."', styles["Script"]))

# OBJECTIONS
story.append(PageBreak())
story.append(Paragraph("Objection Handlers", styles["H1"]))

objections = [
    ('"We have a vendor"',
     '"Which one? Most banks I speak with are using Vantage Circle or building in-house, and I usually hear specific gaps around catalogue depth, multi-currency, or reconciliation. Worth a 15-min comparison."'),
    ('"Not the right person"',
     '"Got it. Marketing, CX, or Loyalty Head? Happy to reach out and mention your name."'),
    ('"No budget this year"',
     '"Fair. Not asking you to buy. Asking if it is worth 20 minutes so when budget comes up, you are not starting from zero."'),
    ('"Send an email"',
     '"Already in your inbox. Which is most relevant to expand on - Plum, Loyalife, or Compass? I will send something specific."'),
    ('"How did you find me"',
     '"Public PICUP attendee data plus standard B2B enrichment. Not spam, targeted outreach because your role overlaps with what we solve. Happy to remove you if you prefer."'),
]
for title, response in objections:
    story.append(Paragraph(title, styles["Obj"]))
    story.append(Paragraph(response, styles["Resp"]))

# SDR NOTES + STATUS
story.append(Paragraph("SDR Quick Notes", styles["H1"]))
notes = [
    "Reference PICUP Fintech in the first 15 seconds. This is post-event, not cold.",
    "Audience is senior. Tone is peer-to-peer, not transactional.",
    "The ask is often an intro, not a meeting. Internal pointer is a win.",
    "Skip the feature dump. Three product names in one line, then listen.",
    "Prioritise the 4 with valid emails. Use phone for PNB and BCG (high value).",
    "Log every call in HubSpot. Dashboard splits attribution by channel.",
    "No em or en dashes in any written follow-up.",
    "No Smartlead email signatures in body - Smartlead account-level signatures handle it.",
]
for n in notes:
    story.append(Paragraph(f"- {n}", styles["Body"]))

story.append(Paragraph("Platform Status", styles["H1"]))
status = [
    ["Platform", "Status", "Next Step"],
    ["Smartlead", "Campaign 3265336 paused. Sequence saved, 30 India accounts attached, IST schedule, stop on reply. 4 leads uploaded.", "Review in Smartlead UI. Flip PAUSED to START when ready."],
    ["HeyReach", "List 645382 created. 0 leads (no LinkedIn URLs in source).", "Run Apollo enrichment for the 7 leads, then upload."],
    ["HubSpot", "Read-only context. No writes.", "Source of truth."],
    ["SDR calls", "Scripts ready (this brief).", "Day 5 (29 Apr) and Day 9 (3 May) dials. Phone-only for Mithlesh / Ishmeet."],
]
t = Table(status, colWidths=[80, 200, 180], repeatRows=1)
t.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, 0), DARK),
    ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ("FONTSIZE", (0, 0), (-1, -1), 8.5),
    ("LEADING", (0, 0), (-1, -1), 11),
    ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ("GRID", (0, 0), (-1, -1), 0.4, HexColor("#CBD5E1")),
    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT_BG]),
    ("TOPPADDING", (0, 0), (-1, -1), 5),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
]))
story.append(t)

story.append(Spacer(1, 20))
story.append(Paragraph("Xoxoday | GTM and Outbound Team | Internal Use Only | Prepared 24 April 2026", styles["CenterNote"]))

outpath = "/Users/naitikchavda/Event Auto push/smartlead-kit/outputs/picup26/PICUP26_Campaign_Brief.pdf"
doc = SimpleDocTemplate(outpath, pagesize=A4,
                        leftMargin=22*mm, rightMargin=22*mm,
                        topMargin=20*mm, bottomMargin=20*mm)
doc.build(story)
print(f"Saved: {outpath}")

"""Render SDR_Script_Compass_Empuls_INDIA_v1.md to a styled PDF.

Mirrors the look of build_sdr_script_pdf.py so internal SDR docs feel uniform.
"""

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.colors import HexColor
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable, KeepTogether
)

PURPLE = HexColor("#5B21B6")
DARK = HexColor("#1E293B")
GRAY = HexColor("#64748B")
LIGHT_BG = HexColor("#F8FAFC")
WHITE = HexColor("#FFFFFF")
ACCENT = HexColor("#7C3AED")
GREEN = HexColor("#059669")
RED = HexColor("#DC2626")
BLUE = HexColor("#2563EB")
ORANGE = HexColor("#EA580C")

styles = getSampleStyleSheet()
styles.add(ParagraphStyle("Title2", parent=styles["Title"], fontSize=22, textColor=PURPLE, spaceAfter=6))
styles.add(ParagraphStyle("Sub", parent=styles["Normal"], fontSize=11, textColor=GRAY, spaceAfter=14))
styles.add(ParagraphStyle("H1", parent=styles["Heading1"], fontSize=16, textColor=DARK, spaceBefore=18, spaceAfter=8))
styles.add(ParagraphStyle("H2", parent=styles["Heading2"], fontSize=13, textColor=PURPLE, spaceBefore=14, spaceAfter=6))
styles.add(ParagraphStyle("H3", parent=styles["Heading3"], fontSize=11, textColor=ACCENT, spaceBefore=10, spaceAfter=4))
styles.add(ParagraphStyle("Body", parent=styles["Normal"], fontSize=10, textColor=DARK, leading=14, spaceAfter=6))
styles.add(ParagraphStyle("Small", parent=styles["Normal"], fontSize=9, textColor=GRAY, leading=12, spaceAfter=4))
styles.add(ParagraphStyle("Script", parent=styles["Normal"], fontSize=10.5, textColor=DARK, leading=15, leftIndent=12, spaceBefore=4, spaceAfter=6, backColor=LIGHT_BG, borderPadding=8))
styles.add(ParagraphStyle("Instr", parent=styles["Normal"], fontSize=9.5, textColor=GRAY, leading=13, leftIndent=12, spaceAfter=4))
styles.add(ParagraphStyle("Obj", parent=styles["Normal"], fontSize=10, textColor=RED, leading=14, spaceAfter=3, fontName="Helvetica-Bold"))
styles.add(ParagraphStyle("Resp", parent=styles["Normal"], fontSize=10, textColor=DARK, leading=14, leftIndent=12, spaceAfter=8, backColor=LIGHT_BG, borderPadding=6))
styles.add(ParagraphStyle("CenterNote", parent=styles["Normal"], fontSize=9, textColor=GRAY, alignment=TA_CENTER, spaceAfter=10))
styles.add(ParagraphStyle("Tag", parent=styles["Normal"], fontSize=9.5, textColor=BLUE, leading=13, spaceAfter=4, fontName="Helvetica-Bold"))


def hr():
    return HRFlowable(width="100%", thickness=0.5, color=HexColor("#E2E8F0"), spaceAfter=8, spaceBefore=8)


def make_table(data, col_widths=None, header_color=DARK):
    t = Table(data, colWidths=col_widths or [120, 340], repeatRows=1)
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


def cell(text):
    return Paragraph(text, styles["Small"])


story = []

# ============================================================
# COVER
# ============================================================
story.append(Spacer(1, 50))
story.append(Paragraph("SDR Calling Script", styles["Title2"]))
story.append(Paragraph("Compass + Empuls, India SMB Tech SaaS", styles["Title2"]))
story.append(Spacer(1, 8))
story.append(Paragraph("Owner: Naitik | Updated: 2026-05-06 | Call length: 4 to 6 min | CTA: 20 min discovery", styles["Sub"]))
story.append(hr())
story.append(Spacer(1, 12))

cover_info = [
    [cell("<b>Field</b>"), cell("<b>Value</b>")],
    [cell("Region"), cell("India (Mumbai, Bengaluru, NCR, Pune, Hyderabad, Chennai)")],
    [cell("Vertical"), cell("B2B Tech SaaS / IT services, 200 to 5,000 FTE")],
    [cell("Buyers"), cell("Sales (Compass) | HR (Empuls)")],
    [cell("Total leads"), cell("49 (25 Compass + 24 Empuls)")],
    [cell("Cadence placement"), cell("Day 5 first dial + Day 8 second dial of 11-day multi-channel sequence")],
    [cell("Companion channels"), cell("Smartlead email + HeyReach LinkedIn on same list")],
    [cell("Goal"), cell("5 to 8 meetings booked into Naitik's pipeline")],
]
story.append(make_table(cover_info, col_widths=[110, 350]))

story.append(Spacer(1, 16))
story.append(Paragraph("Campaign IDs", styles["H3"]))
camp_info = [
    [cell("<b>Campaign</b>"), cell("<b>Smartlead</b>"), cell("<b>HeyReach</b>"), cell("<b>Buyer</b>"), cell("<b>Leads</b>")],
    [cell("Compass (Sales Incentives module of Empuls)"), cell("3238358"), cell("414235"), cell("VP / Head / Director of Sales"), cell("25")],
    [cell("Empuls (R&R, engagement, rewards)"), cell("3238359"), cell("414202"), cell("CHRO / HR Head / HRBP"), cell("24")],
]
story.append(make_table(camp_info, col_widths=[160, 65, 65, 110, 50]))

story.append(Spacer(1, 14))
story.append(Paragraph("Live engagement (as of 2026-05-06)", styles["H3"]))
eng_info = [
    [cell("<b>Campaign</b>"), cell("<b>Sends</b>"), cell("<b>Opens</b>"), cell("<b>Open %</b>"), cell("<b>Replies</b>"), cell("<b>Bounces</b>")],
    [cell("Compass 3238358"), cell("75"), cell("58"), cell("77%"), cell("0"), cell("1")],
    [cell("Empuls 3238359"), cell("72"), cell("52"), cell("72%"), cell("0"), cell("0")],
]
story.append(make_table(eng_info, col_widths=[140, 60, 60, 60, 70, 60]))

story.append(Spacer(1, 12))
story.append(Paragraph(
    "Read this number: ~75% opens, zero replies. Buyers have read the framing, no one has objected, no one has said yes. The phone is the next forcing function.",
    styles["Body"]))

# ============================================================
# PRE-CALL CHECKLIST
# ============================================================
story.append(PageBreak())
story.append(Paragraph("1. Pre-call checklist (90 seconds before dialing)", styles["H1"]))
prep = [
    "Open the lead row in HubSpot. Confirm <b>campaign_id</b> (3238358 = Compass / Sales, 3238359 = Empuls / HR).",
    "Note the <b>segment</b> column. For Compass watch for the 4 channel-flagged leads: Vipul Mathur (Spectranet), Rakesh Kumar (Atlys), Tejas Shah (Emudhra), Rakesh Banga (Atlys).",
    "Check the <b>last_email_subject</b> field. Drop that exact phrase in the opener.",
    "Glance at LinkedIn for one specific signal you can name in the first 30 seconds (a recent post, a hire, a product launch).",
    "Have the calendar tab open <b>before</b> the dial connects.",
]
for p in prep:
    story.append(Paragraph(f"- {p}", styles["Body"]))

# ============================================================
# OPENER
# ============================================================
story.append(Paragraph("2. The universal opener (15 seconds, both campaigns)", styles["H1"]))
story.append(Paragraph("Say:", styles["Instr"]))
story.append(Paragraph(
    '"Hi {first_name}, this is [SDR name] calling from Xoxoday. I know I am calling cold, can I borrow 30 seconds to tell you why, and you can decide if it is worth a real conversation?"',
    styles["Script"]))
story.append(Paragraph("Pause. Wait for yes, go ahead, silence, or pushback.", styles["Instr"]))
story.append(Paragraph(
    "<b>Why this works:</b> You are giving them control. Indian sales and HR leaders accept a 30 second ask far more than a generic 'got a minute?'",
    styles["Body"]))
story.append(Paragraph('If they say "what is this about":', styles["Instr"]))
story.append(Paragraph(
    '"A quick note I sent you last week landed on your inbox, subject line was around {last_email_subject}. Worth 30 seconds to give you the why?"',
    styles["Script"]))

# ============================================================
# PITCH FORK
# ============================================================
story.append(PageBreak())
story.append(Paragraph("3. The pitch fork (choose one, based on campaign_id + segment)", styles["H1"]))

story.append(Paragraph("3A. Compass, Direct Sales segment (21 of 25 leads)", styles["H2"]))
story.append(Paragraph(
    '"Most VP Sales we work with at SaaS firms in your headcount band still run commissions on Sheets. RevOps loses 5 to 7 days every month, reps shadow-track their own numbers, rolling out a new SPIFF takes a week. We built Compass, the sales incentives module inside Empuls, to fix that end to end. Pepsico, Capgemini, and Aditya Birla Capital are on it."',
    styles["Script"]))
story.append(Paragraph("Then ask both:", styles["Instr"]))
story.append(Paragraph("1) Is comp at {company_name} on a tool today, or is it still in Sheets?", styles["Body"]))
story.append(Paragraph("2) Is fixing the comp process on the priority list for FY26?", styles["Body"]))

story.append(Paragraph("3B. Compass, Channel segment (4 leads: Spectranet, Atlys x2, Emudhra)", styles["H2"]))
story.append(Paragraph(
    '"Most channel sales leaders we work with at SaaS firms your size are running partner SPIFFs and override commissions on a Sheet shared with 50 to 200 partners. Partners cannot see their own attainment, escalations pile up on the channel manager, and contest payouts take weeks. Compass, the sales incentives module inside Empuls, runs the plan logic. Payouts flow through Plum so partners in India and abroad can take it as cash, gift cards, or experiences in their own country."',
    styles["Script"]))
story.append(Paragraph("Then ask both:", styles["Instr"]))
story.append(Paragraph("1) How many active partners is {company_name} running incentives for today?", styles["Body"]))
story.append(Paragraph("2) Where does most of the friction sit, plan rollout, payout, or visibility for partners?", styles["Body"]))

story.append(Paragraph("3C. Empuls, HR segment (all 24 leads)", styles["H2"]))
story.append(Paragraph(
    '"Most People leaders we work with at SaaS firms your size are running R&R across four places: Slack shoutouts, ad-hoc gift cards once a quarter, an Excel sheet for service anniversaries, and one annual awards night that 30 percent of the company misses. We built Empuls to pull all of that into one platform that lives inside Slack or Teams. KPIT, Prodevans, and Bahwan CyberTek run on it."',
    styles["Script"]))
story.append(Paragraph("Then ask both:", styles["Instr"]))
story.append(Paragraph("1) Is recognition at {company_name} on a single tool today, or stitched together?", styles["Body"]))
story.append(Paragraph("2) Is engagement or attrition something the team is actively solving for in 2026?", styles["Body"]))

# ============================================================
# READ THE ROOM
# ============================================================
story.append(PageBreak())
story.append(Paragraph("4. Read the room, then route", styles["H1"]))
story.append(Paragraph("Pick the path the prospect signals. Do not stack pitches.", styles["Small"]))

story.append(Paragraph('Path A, "yes, this is a problem for us"', styles["H3"]))
story.append(Paragraph(
    '"Got it. Two ways forward. I can either send a 90 second loom that walks you through how a {company_size_band} team uses it, or we book 20 minutes later this week and I show you a sandbox built around your motion. Which is easier?"',
    styles["Script"]))
story.append(Paragraph("If they take the meeting, jump to Section 7 (booking). If they take the loom, confirm email, send within the hour, log <b>LOOM_SENT_NURTURE</b>.", styles["Instr"]))

story.append(Paragraph('Path B, "we already have a tool"', styles["H3"]))
story.append(Paragraph("Find out which one, then use the angle below.", styles["Instr"]))
toolmap = [
    [cell("<b>If they have</b>"), cell("<b>Open with</b>")],
    [cell("Spiff, Everstage, Xactly, Performio (Compass)"),
     cell('Most teams that switch to us from those want India-specific support, faster plan rollouts, or the integrated rewards engine on payouts. If any of those are open issues, worth 20 mins. If everything is humming, I will get out of your way.')],
    [cell("In-house tool or Sheets calling itself a tool (Compass)"),
     cell('Fair. Quick check, what happens when you need to roll out a new contest mid-quarter, how long does that take today?')],
    [cell("Vantage Circle, Workhuman, Reward Gateway (Empuls)"),
     cell('Both are good. Where we win in India is the breadth of the catalogue (gold, local brands, experiences) plus surveys built into the same platform, not a separate Culture Amp. Worth 20 mins to compare.')],
    [cell("Plumm, internal Slack bot (Empuls)"),
     cell('Got it. Most teams move to Empuls when they want milestones, surveys, perks, and global rewards in one place instead of three tools. Open to 20 mins to map yours?')],
]
story.append(make_table(toolmap, col_widths=[170, 290]))
story.append(Paragraph(
    'Always end with: <b>"And when does that contract come up for renewal?"</b> Capture the renewal date in HubSpot, that is the trigger date for re-engagement.',
    styles["Body"]))

story.append(Paragraph('Path C, "send me an email"', styles["H3"]))
story.append(Paragraph(
    '"Done, I will keep it tight. One question first so the email is actually useful for you..."',
    styles["Script"]))
story.append(Paragraph("Compass: How many AEs are you running comp for right now, and is comp the bottleneck or is plan design the bottleneck?", styles["Body"]))
story.append(Paragraph("Empuls: How many FTE are you running R&R for, and is the bigger gap recognition itself or the rewards catalogue?", styles["Body"]))
story.append(Paragraph("Send the email within 15 minutes, reference one thing from the call, attach the relevant 1-pager. Log <b>EMAIL_REQUESTED_FOLLOW_UP</b>.", styles["Instr"]))

story.append(Paragraph('Path D, "not now"', styles["H3"]))
story.append(Paragraph(
    '"Fair. Quick check, is \'not now\' 1 quarter, 2 quarters, or all of 2026? I will note it and only come back when it makes sense."',
    styles["Script"]))
story.append(Paragraph("Capture the timeline. Log <b>NOT_NOW_QX_2026</b> or <b>NOT_NOW_2027</b>.", styles["Instr"]))

story.append(Paragraph('Path E, "wrong person"', styles["H3"]))
story.append(Paragraph(
    '"No problem. Who at {company_name} owns this in 2026? Happy to drop your name when I reach out, or you can intro me, whichever is easier."',
    styles["Script"]))
story.append(Paragraph("Capture the name and email. Log <b>WRONG_PERSON_REROUTED</b>.", styles["Instr"]))

story.append(Paragraph('Path F, hard "no, remove me"', styles["H3"]))
story.append(Paragraph("Acknowledge, do not push back.", styles["Instr"]))
story.append(Paragraph('"Got it, I will mark you off the list. Apologies for the noise."', styles["Script"]))
story.append(Paragraph("Log <b>DNC</b>. Mark in HubSpot, suppress across email and LinkedIn via the unified suppression list.", styles["Instr"]))

# ============================================================
# VOICEMAIL
# ============================================================
story.append(PageBreak())
story.append(Paragraph("6. D8 voicemail (30 seconds, only if D5 went unanswered)", styles["H1"]))

story.append(Paragraph("For Compass (3238358):", styles["H3"]))
story.append(Paragraph(
    '"Hi {first_name}, [SDR name] from Xoxoday again. I sent you a couple of notes last week about Compass, our sales commissions and partner payouts platform. We help SaaS sales orgs in your headcount band move comp off Sheets, cut disputes by 80 percent, and roll out SPIFFs in days, not weeks. If sales comp is on your radar this quarter, I would love 20 minutes. I will drop one final email and then back off. All the best for the quarter."',
    styles["Script"]))

story.append(Paragraph("For Empuls (3238359):", styles["H3"]))
story.append(Paragraph(
    '"Hi {first_name}, [SDR name] from Xoxoday again. I sent you a couple of notes last week about Empuls, our employee engagement and rewards platform. We help SaaS HR teams in your headcount band consolidate R&R into one platform that lives inside Slack, automate milestones, and unlock a global rewards catalogue with a strong India side. If engagement is on your radar this year, I would love 20 minutes. Final email coming, then I will back off. All the best."',
    styles["Script"]))

story.append(Paragraph("If they pick up on the second attempt:", styles["H3"]))
story.append(Paragraph(
    '"Hi {first_name}, [SDR name] from Xoxoday. I will not take more than a minute. I called and emailed earlier about [Compass / Empuls]. The reason I called twice is I genuinely think the platform fits {company_name}\'s setup. Two paths: I can send a 90 second loom that walks through it, or we book 20 minutes later this week. Which is easier?"',
    styles["Script"]))

# ============================================================
# BOOKING
# ============================================================
story.append(Paragraph("7. Booking the meeting (the only outcome that matters)", styles["H1"]))
story.append(Paragraph(
    '"Great, 20 minutes. I will send a Calendly with three slots this week. If none work, just reply with two times. Confirming your email is {email}, correct?"',
    styles["Script"]))
story.append(Paragraph("Then within 15 minutes:", styles["Instr"]))
post = [
    "Send the calendar invite with a tight agenda (3 lines, no deck attached).",
    "Tag the lead in HubSpot as <b>MEETING_BOOKED</b>.",
    "Drop a note to Naitik on the deal record with the 2 discovery questions you got answers to.",
    "Pause Smartlead and HeyReach for that lead via the suppression webhook.",
]
for p in post:
    story.append(Paragraph(f"- {p}", styles["Body"]))

# ============================================================
# OBJECTION BENCH
# ============================================================
story.append(PageBreak())
story.append(Paragraph("8. Objection bench (one-liners, full set)", styles["H1"]))

obj = [
    ("\"We use Excel and it works.\"",
     "Most teams say that until reps stop trusting it. Curious, do reps see their attainment in real time today, or do they ping RevOps every week?"),
    ("\"Spiff or Everstage already pitched us.\"",
     "Both are good products. Where we win is India support, faster plan changes, and the built-in rewards engine on payouts. Worth 20 mins to compare on those three."),
    ("\"Compass is just for internal reps, our pain is partners.\"",
     "Same module runs both. Plan logic for overrides, SPIFFs, lead-reg, tier accelerators applies to partners exactly the same way. Plum handles partner payouts in 100+ countries. Worth 20 mins to map your partner motion."),
    ("\"We are looking at a partner-loyalty tool like Loyalife.\"",
     "Different problem. Loyalife is for long-term, points-based partner programs. If you want quick-cycle SPIFFs and quarterly contests, Compass is the right module. Both can sit inside one Xoxoday account."),
    ("\"Slack shoutouts work fine for us.\"",
     "Most teams say that until eNPS dips. Quick check, do you have a single dashboard that shows who has been recognized this month and who has not?"),
    ("\"Vantage Circle or Workhuman is fine.\"",
     "Both solid. Where we win in India is the catalogue depth (gold, local brands, experiences) plus surveys built in instead of a separate Culture Amp. Worth 20 mins to compare."),
    ("\"Send a deck.\"",
     "I can do better, can I send a 90 second loom of the dashboard? Decks die in a folder."),
    ("\"Budget is locked.\"",
     "Understood. Most pilots we run are paid out of the existing R&R or RevOps efficiency line, not new budget. Worth 15 mins to map that?"),
    ("\"Talk to RevOps / CHRO, not me.\"",
     "Happy to. Can you intro me, or is it better if I drop your name?"),
    ("\"We are too small.\"",
     "We have customers from 150 FTE. Often the smaller you are, the more leverage one consolidated platform gives you."),
    ("\"Email me, I will get back.\"",
     "Sure, sending now. So I send the right thing, what is the one thing about the current setup that bothers you most?"),
]
for title, response in obj:
    story.append(KeepTogether([
        Paragraph(title, styles["Obj"]),
        Paragraph(response, styles["Resp"]),
    ]))

# ============================================================
# DISPOSITION
# ============================================================
story.append(PageBreak())
story.append(Paragraph("9. Disposition codes (log every call in HubSpot)", styles["H1"]))
dispo = [
    [cell("<b>Code</b>"), cell("<b>Meaning</b>"), cell("<b>Next action</b>")],
    [cell("MEETING_BOOKED"), cell("20 min discovery on the calendar"), cell("Pause Smartlead + HeyReach for this lead, hand to Naitik")],
    [cell("LOOM_SENT_NURTURE"), cell("Lead asked for the loom in lieu of a meeting"), cell("Send within 1 hour, follow up D+3")],
    [cell("EMAIL_REQUESTED_FOLLOW_UP"), cell("Lead asked to send an email"), cell("Send within 15 min, follow up D+3")],
    [cell("INTERESTED_NURTURE"), cell("Warm but timing off, no specific date"), cell("Re-engage in 30 days")],
    [cell("NOT_NOW_Q3_2026 / Q4_2026 / 2027"), cell("Future timing"), cell("Auto-task on the future date")],
    [cell("WRONG_PERSON_REROUTED"), cell("Captured the right contact"), cell("Add the new contact, restart the sequence on them")],
    [cell("COMPETITOR_INSTALLED"), cell("Has a tool, capture vendor + renewal date"), cell("Re-engage 90 days before renewal")],
    [cell("NO_ANSWER_LEFT_VOICEMAIL"), cell("D8 voicemail dropped"), cell("Let the email sequence finish, no third dial")],
    [cell("NO_ANSWER_NO_VOICEMAIL"), cell("D5 no-answer, no voicemail dropped"), cell("Try D8 with voicemail")],
    [cell("DNC"), cell("Asked to stop"), cell("Suppress across all channels in HubSpot")],
]
story.append(make_table(dispo, col_widths=[140, 180, 140]))

# ============================================================
# DAILY PLAN
# ============================================================
story.append(Paragraph("10. Daily call plan for the SDR", styles["H1"]))
plan = [
    "<b>Dial windows (Asia/Kolkata):</b> 10:00 to 12:30 and 15:00 to 17:30. Avoid 12:30 to 14:30 lunch and 17:45 traffic-out window.",
    "<b>Daily volume:</b> 10 to 12 dials per SDR, half Compass and half Empuls. Quality over quantity, every call gets a logged disposition.",
    "<b>Two attempts max per lead:</b> D5 first dial, D8 second dial with voicemail. After that, the breakup email (Step 5) carries the close.",
    "<b>Hot routing:</b> any 'yes, book it' goes to Naitik's Calendly the same day. Do not let a warm lead cool off overnight.",
]
for p in plan:
    story.append(Paragraph(f"- {p}", styles["Body"]))

# ============================================================
# NOTES
# ============================================================
story.append(Paragraph("11. Notes for the SDR (read once, internalize)", styles["H1"]))
notes = [
    "The lead has read 2 emails and seen a LinkedIn connection request <b>before</b> you dial. You are not cold, anchor on that.",
    'The email subject they likely opened was either <i>"{first_name}, how is {company_name} running sales incentives this quarter"</i> (Compass) or <i>"{first_name}, how is recognition running at {company_name}"</i> (Empuls). Use it.',
    "Compass = Sales Incentives module of Empuls. Do not pitch it as a separate platform. The 'Compass' name has brand equity, keep it visible.",
    "Customer references that work in India: <b>KPIT, Prodevans, Bahwan CyberTek</b> for Empuls. <b>Pepsico, Capgemini, Aditya Birla Capital</b> for Compass.",
    "No em-dashes or en-dashes in the follow-up email. Use commas or hyphens.",
    "If the prospect asks pricing, say: <i>It depends on headcount and modules. For your band it lands in [X to Y INR per employee per year]. The 20 minute call is where we scope it.</i> Do not fudge the number, hand to Naitik if you do not know it.",
    "Goal: <b>5 to 8 meetings booked</b> from these 49 leads combined, into Naitik's pipeline.",
]
for n in notes:
    story.append(Paragraph(f"- {n}", styles["Body"]))

# ============================================================
# MERGE TAGS
# ============================================================
story.append(Paragraph("Merge tags used in this script", styles["H1"]))
tags = [
    [cell("<b>Tag</b>"), cell("<b>Source</b>"), cell("<b>Example</b>")],
    [cell("{first_name}"), cell("HubSpot"), cell("Vipul")],
    [cell("{company_name}"), cell("HubSpot"), cell("Spectranet")],
    [cell("{email}"), cell("HubSpot"), cell("vipul@spectra.co")],
    [cell("{last_email_subject}"), cell("Smartlead history"), cell("the spreadsheet behind your reps' and partners' payouts")],
    [cell("{company_size_band}"), cell("Computed in HubSpot"), cell("500 to 1,500 FTE SaaS")],
    [cell("[SDR name]"), cell("Hardcoded by SDR"), cell("Priya Menon")],
]
story.append(make_table(tags, col_widths=[140, 140, 180]))

story.append(Spacer(1, 18))
story.append(hr())
story.append(Paragraph("Xoxoday | India Outbound | Internal Use Only", styles["CenterNote"]))

# ============================================================
# BUILD
# ============================================================
outpath = "/Users/naitikchavda/Event Auto push/smartlead-kit/outputs/SDR_Script_Compass_Empuls_INDIA_v1.pdf"
doc = SimpleDocTemplate(
    outpath, pagesize=A4,
    leftMargin=22 * mm, rightMargin=22 * mm,
    topMargin=20 * mm, bottomMargin=20 * mm,
)
doc.build(story)
print(f"Saved: {outpath}")

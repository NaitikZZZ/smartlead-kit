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

story = []

# COVER
story.append(Spacer(1, 60))
story.append(Paragraph("SDR Calling Script", styles["Title2"]))
story.append(Paragraph("HR Leaders at Keka-Using Companies", styles["Title2"]))
story.append(Spacer(1, 10))
story.append(Paragraph("Product: Empuls + Plum | Region: India | Call length: 3-5 min", styles["Sub"]))
story.append(hr())
story.append(Spacer(1, 16))

cover_info = [
    ["Field", "Value"],
    ["Target", "HR leaders at India-based companies using Keka"],
    ["Angle", "Rewards and recognition handled separately from core HR, fragmented stack"],
    ["Call length target", "3 to 5 minutes to qualify"],
    ["CTA", "30 minute discovery meeting"],
    ["Cadence placement", "Day 5 (first dial) + Day 8 (second dial) of 11-day cadence"],
    ["Companion channels", "Smartlead email + HeyReach LinkedIn on same list"],
]
story.append(make_table(cover_info))

# PRE-CALL PREP
story.append(PageBreak())
story.append(Paragraph("Pre-Call Prep (30 seconds)", styles["H1"]))
story.append(Paragraph("Before dialing, pull up:", styles["Body"]))
prep_items = [
    "Prospect name, title, company",
    "LinkedIn profile (check for recent posts, role tenure, team size signals)",
    "Confirm they use Keka (via Apollo tech stack, LinkedIn mentions, or deal history)",
    "Any past email or LinkedIn touches from Smartlead or HeyReach (reference if opened or replied)",
]
for p in prep_items:
    story.append(Paragraph(f"- {p}", styles["Body"]))

# OPENING
story.append(Paragraph("Opening (10 seconds)", styles["H1"]))
story.append(Paragraph("Say:", styles["Instr"]))
story.append(Paragraph('"Hi {FIRST_NAME}, this is [YOUR NAME] from Xoxoday. Have I caught you at a bad time? I will be quick."', styles["Script"]))
story.append(Paragraph("If yes, bad time:", styles["Instr"]))
story.append(Paragraph('"Totally understand. When would be a better 2 minute window today or tomorrow? I will call back then."', styles["Script"]))
story.append(Paragraph("If okay to continue, go to Purpose.", styles["Instr"]))

# PURPOSE
story.append(Paragraph("Purpose (15 seconds)", styles["H1"]))
story.append(Paragraph('"Thanks. I am speaking with a few HR leaders in India on how they are managing engagement and rewards alongside systems like Keka. I wanted to get your perspective."', styles["Script"]))
story.append(Paragraph("Pause. Let them respond.", styles["Instr"]))

# DISCOVERY
story.append(PageBreak())
story.append(Paragraph("Discovery Questions (2 to 3 minutes)", styles["H1"]))
story.append(Paragraph("Work through these in order. Skip any that get answered naturally.", styles["Small"]))

story.append(Paragraph("Q1 - Current state", styles["H3"]))
story.append(Paragraph('"Wanted to understand how you are currently managing rewards and recognition at {COMPANY}?"', styles["Script"]))
story.append(Paragraph("Listen for: manual process, spreadsheets, gift card procurement, another platform, not doing it at all.", styles["Instr"]))

story.append(Paragraph("Q2 - Fragmentation probe", styles["H3"]))
story.append(Paragraph('"In most teams I speak with, this is still handled manually or across different tools. How is it for you?"', styles["Script"]))
story.append(Paragraph("Listen for: HR ops involvement, finance approvals, multiple gift card vendors, employees complaining, missed milestones.", styles["Instr"]))

story.append(Paragraph("Q3 - Pattern recognition (build credibility)", styles["H3"]))
story.append(Paragraph('"Asking this because we are seeing a common pattern with Keka users in India. Core HR processes are well managed, but engagement initiatives like rewards and recognition are still handled separately. This usually increases manual effort and things get missed over time. Is this something you are also experiencing?"', styles["Script"]))
story.append(Paragraph("Listen for: yes/no, specific pain points, scale of the problem.", styles["Instr"]))

story.append(Paragraph("Q4 - Priority probe", styles["H3"]))
story.append(Paragraph('"On a scale of 1 to 10, how much of a priority is improving engagement or recognition for {COMPANY} this year?"', styles["Script"]))
story.append(Paragraph("Listen for: the number, and what they mention as blockers or drivers.", styles["Instr"]))

story.append(Paragraph("Q5 - Stakeholder check (if time permits)", styles["H3"]))
story.append(Paragraph('"Is this something you own, or does it sit with someone else like People Ops or Total Rewards?"', styles["Script"]))
story.append(Paragraph("If not them, ask for the right name. Still warm.", styles["Instr"]))

# PITCH
story.append(PageBreak())
story.append(Paragraph("Pitch (30 seconds)", styles["H1"]))
story.append(Paragraph("Tailor based on what you heard in discovery. Use this core frame:", styles["Small"]))
story.append(Paragraph('"{FIRST_NAME}, based on what you shared, it sounds like [REFLECT BACK THEIR PAIN]. We built Empuls specifically for this. It plugs into Keka, automates peer recognition, service awards, and rewards delivery, and gives employees access to a global catalogue of 10,000+ rewards in 100+ countries without your team touching gift card procurement."', styles["Script"]))
story.append(Paragraph('"Companies like [INSERT 1-2 RELEVANT CUSTOMER NAMES, e.g. Brenntag, Luminous, Freshworks] use it to run engagement for globally distributed teams without adding headcount on the HR side."', styles["Script"]))

# CTA
story.append(Paragraph("CTA (15 seconds)", styles["H1"]))
story.append(Paragraph('"If improving engagement or recognition is something you are looking at, I can walk you through how a few Keka customers are approaching it today. It is a simple 30 minute conversation and you can decide if it is useful. Would you be open to a quick call this week or next?"', styles["Script"]))
story.append(Paragraph("If yes:", styles["Instr"]))
story.append(Paragraph('"Great. I have [X] or [Y] open. Which works better for you?"', styles["Script"]))
story.append(Paragraph("Book the meeting. Confirm email for invite.", styles["Instr"]))
story.append(Paragraph("If hesitant:", styles["Instr"]))
story.append(Paragraph('"No pressure. If it helps, I can send a 2 minute Loom showing how the Keka integration works. Want me to send it?"', styles["Script"]))
story.append(Paragraph("If yes, capture email. Still a win.", styles["Instr"]))

# OBJECTIONS
story.append(PageBreak())
story.append(Paragraph("Objection Handlers", styles["H1"]))

objections = [
    ("Objection 1: We already have a tool for this",
     '"Got it. Which one, if you do not mind me asking? I ask because most teams we speak with are using Vantage Circle, Advantage Club, or Darwinbox, and we often hear about specific limitations around global catalogue coverage or integration depth with Keka. Would be worth a 15 minute comparison to see if Empuls adds anything on top."'),
    ("Objection 2: We do not have budget",
     '"Completely understand. Most of the HR leaders I speak with are not actively shopping. The reason I am calling is to share what peers are doing so that when budget comes up, you are not starting from zero. Worth 20 minutes just to stay informed?"'),
    ("Objection 3: Send me an email",
     '"Happy to. To make it useful, which part is most relevant, the Keka integration, the global rewards catalogue, or the peer recognition workflows? I will send something specific rather than generic."'),
    ("Objection 4: Not the right person",
     '"Appreciate you telling me. Who should I be speaking with? [Capture name]. And would you be open to a quick intro, or should I reach out directly mentioning your name?"'),
    ("Objection 5: We are happy with our current setup",
     '"That is great to hear. Quick question, if your recognition program magically had zero operational overhead tomorrow, what would you do with the time your team gets back? Just curious what the ceiling looks like for your team."'),
    ("Objection 6: Call me back later or next quarter",
     '"Sure, let me book it now so it does not slip. When in [MONTH] works best for you?" (Book the callback. Do not leave it open-ended.)'),
    ("Objection 7: How did you get my number?",
     '"Our team pulls decision maker info when we see companies using Keka, since that is a signal we match with. Not spam, just targeted outreach. Happy to remove you from our list if you prefer."'),
]
for title, response in objections:
    story.append(Paragraph(title, styles["Obj"]))
    story.append(Paragraph(response, styles["Resp"]))

# VOICEMAIL
story.append(PageBreak())
story.append(Paragraph("Voicemail (20 seconds)", styles["H1"]))
story.append(Paragraph("Use if no pickup on first call.", styles["Small"]))
story.append(Paragraph('"Hi {FIRST_NAME}, this is [YOUR NAME] from Xoxoday. I was calling to quickly understand how you are managing rewards and recognition alongside Keka at {COMPANY}. Most HR leaders I speak with in India are running this manually, and I thought you might find it useful to hear how peers are approaching it. I will send you a quick note by email. You can also reach me back at [YOUR NUMBER]. Thanks, {FIRST_NAME}."', styles["Script"]))
story.append(Paragraph("Follow up with email within 10 minutes referencing the voicemail.", styles["Instr"]))

# SECOND CALL
story.append(Paragraph("Second Call (Day 8 in Cadence)", styles["H1"]))
story.append(Paragraph("Only if no pickup on first call.", styles["Small"]))
story.append(Paragraph('"Hi {FIRST_NAME}, [YOUR NAME] from Xoxoday again. I left you a voicemail last week about rewards and recognition alongside Keka. Just wanted to try once more before I stop. Is this a better time?"', styles["Script"]))
story.append(Paragraph("If still no pickup, leave a shorter voicemail and stop calling. Shift to email and LinkedIn only.", styles["Instr"]))

# DISPOSITION
story.append(PageBreak())
story.append(Paragraph("Call Disposition (Log After Every Call)", styles["H1"]))
dispo = [
    ["Outcome", "Action"],
    ["Meeting booked", "Send calendar invite plus 2-line recap email immediately"],
    ["Asked for info", "Send targeted email within 10 minutes"],
    ["Not the right person", "Capture correct name, update HubSpot"],
    ["Call back later", "Book specific callback time in calendar"],
    ["Not interested", "Mark in HubSpot, pause cadence"],
    ["Voicemail", "Log and trigger follow-up email"],
    ["No answer", "Move to next touch in cadence"],
]
story.append(make_table(dispo, col_widths=[150, 310]))

# DO NOT SAY
story.append(Paragraph("Do Not Say", styles["H1"]))
donts = [
    '"I just want to touch base" - sounds generic',
    '"Can I have 15 minutes of your time?" - too much, too early',
    '"We are the best in the market" - unsupported',
    '"Our platform does [feature dump]" - prospects do not care about features',
    'Em dashes or en dashes in any written follow-up',
]
for d in donts:
    story.append(Paragraph(f"- {d}", styles["Body"]))

# MERGE TAGS + CAMPAIGN CONTEXT
story.append(Paragraph("Merge Tag Reference", styles["H1"]))
tags = [
    ["Tag", "Example value"],
    ["{FIRST_NAME}", "Priya"],
    ["{LAST_NAME}", "Sharma"],
    ["{COMPANY}", "ABC Tech"],
    ["{YOUR NAME}", "SDR's own name"],
    ["{YOUR NUMBER}", "SDR's dial-back number"],
]
story.append(make_table(tags, col_widths=[140, 300]))

story.append(Paragraph("Campaign Context", styles["H1"]))
story.append(Paragraph("This script runs alongside:", styles["Body"]))
story.append(Paragraph("- Smartlead email campaign targeting same HR leaders at Keka-using companies", styles["Body"]))
story.append(Paragraph("- HeyReach LinkedIn campaign on the same list", styles["Body"]))
story.append(Paragraph("- Call is Day 5 (first dial) and Day 8 (second dial) in the 11-day cadence", styles["Body"]))
story.append(Spacer(1, 10))
story.append(Paragraph("SDRs should always reference prior email or LinkedIn touches during the call opening when possible. Example: 'I also sent you an email on Monday about the same topic, not sure if you saw it.'", styles["Body"]))

story.append(Spacer(1, 20))
story.append(Paragraph("Xoxoday | GTM and Outbound Team | Internal Use Only", styles["CenterNote"]))

# Build
outpath = "/Users/naitikchavda/Event Auto push/smartlead-kit/outputs/SDR_Calling_Script_Empuls_Keka_HR.pdf"
doc = SimpleDocTemplate(outpath, pagesize=A4,
                        leftMargin=22*mm, rightMargin=22*mm,
                        topMargin=20*mm, bottomMargin=20*mm)
doc.build(story)
print(f"Saved: {outpath}")

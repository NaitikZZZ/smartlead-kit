from pathlib import Path
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle,
    KeepTogether,
)

OUT = Path(__file__).parent / "Plum_Survey_Partners_Cadence.pdf"

styles = getSampleStyleSheet()

H1 = ParagraphStyle(
    "H1", parent=styles["Heading1"],
    fontName="Helvetica-Bold", fontSize=18, leading=22,
    textColor=colors.HexColor("#1F3864"),
    spaceBefore=0, spaceAfter=14,
)
H2 = ParagraphStyle(
    "H2", parent=styles["Heading2"],
    fontName="Helvetica-Bold", fontSize=13, leading=16,
    textColor=colors.HexColor("#2F5496"),
    spaceBefore=18, spaceAfter=8,
)
H3 = ParagraphStyle(
    "H3", parent=styles["Heading3"],
    fontName="Helvetica-Bold", fontSize=10.5, leading=14,
    textColor=colors.HexColor("#333333"),
    spaceBefore=10, spaceAfter=4,
)
META = ParagraphStyle(
    "META", parent=styles["Normal"],
    fontName="Helvetica-Oblique", fontSize=9, leading=12,
    textColor=colors.HexColor("#666666"),
    spaceAfter=6,
)
LABEL = ParagraphStyle(
    "LABEL", parent=styles["Normal"],
    fontName="Helvetica-Bold", fontSize=9.5, leading=12,
    textColor=colors.HexColor("#333333"),
    spaceAfter=2,
)
BODY_MONO = ParagraphStyle(
    "BODY_MONO", parent=styles["Normal"],
    fontName="Courier", fontSize=10, leading=14,
    textColor=colors.HexColor("#111111"),
    spaceAfter=6,
    leftIndent=10, rightIndent=10,
)
NOTE = ParagraphStyle(
    "NOTE", parent=styles["Normal"],
    fontName="Helvetica", fontSize=9, leading=12,
    textColor=colors.HexColor("#555555"),
    spaceAfter=8,
)


def code_block(text, story):
    cell_style = BODY_MONO
    para = Paragraph(text.replace("\n", "<br/>"), cell_style)
    tbl = Table([[para]], colWidths=[6.5 * inch])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F5F7FA")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#D0D7E2")),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 6))


def step(label, subject, body, story, meta=None):
    block = []
    block.append(Paragraph(label, H3))
    if meta:
        block.append(Paragraph(meta, META))
    if subject:
        block.append(Paragraph(f"Subject: <b>{subject}</b>", LABEL))
        block.append(Spacer(1, 2))
    story.append(KeepTogether(block))
    code_block(body, story)


doc = SimpleDocTemplate(
    str(OUT), pagesize=letter,
    leftMargin=0.75 * inch, rightMargin=0.75 * inch,
    topMargin=0.75 * inch, bottomMargin=0.75 * inch,
    title="Plum x Survey Partners - Outbound Cadence",
    author="Xoxoday Global API",
)

story = []

story.append(Paragraph("Plum x Survey Platforms - Outbound Cadence", H1))
story.append(Paragraph(
    "Email, LinkedIn, and Call sequence for partnership outreach to survey "
    "platform Product and BD leaders.",
    NOTE,
))
story.append(Spacer(1, 6))


story.append(Paragraph("Email Sequence", H2))

step(
    "Email 1 - Day 1",
    "Survey response rates",
    "Survey response rates dropped below 15% industry-wide.\n"
    "Most platforms patch this with incentives, but fulfillment breaks at global scale.\n"
    "Plum integrates with Qualtrics, SurveyMonkey, and Typeform today.\n"
    "How is {{company}} handling respondent rewards across regions?",
    story,
    meta="Cold opener. No signature - Smartlead appends at account level.",
)

step(
    "Email 2 - Day 4 (bump)",
    "Re: Survey response rates",
    "Bumping this up.\n"
    "Three reasons panelists churn most often: slow payouts, no local currency, irrelevant rewards.\n"
    "Plum handles all three through one REST endpoint, in 175+ countries.\n"
    "Worth a 15-min look this week?",
    story,
)

step(
    "Email 3 - Day 8 (breakup)",
    "Closing the loop",
    "Closing this loop on my end.\n"
    "If incentivized response rates land back on your roadmap, ping me.\n"
    "If not, no worries.\n"
    "Wish you the best with {{company}}.",
    story,
)


story.append(PageBreak())


story.append(Paragraph("LinkedIn Sequence", H2))
story.append(Paragraph(
    "Runs in parallel with email. Kicks off Day 2 with a connection request.",
    NOTE,
))

step(
    "Connection Request - Day 2",
    None,
    "Hi {{first_name}}, working on rewards and payouts infrastructure for survey "
    "platforms. Would love to compare notes on global respondent incentivization.\n\n"
    "Naitik",
    story,
    meta="Keep under 300 characters. LinkedIn limit applies.",
)

step(
    "DM 1 - Day 3 (or 24h after they accept)",
    None,
    "Thanks for connecting, {{first_name}}.\n\n"
    "Quick context on why I reached out. Plum runs the rewards layer inside "
    "Qualtrics, SurveyMonkey and Typeform. Response rates and panel retention "
    "keep coming up in those conversations.\n\n"
    "Curious how {{company}} is approaching global incentive fulfillment today?\n\n"
    "Naitik",
    story,
)

step(
    "DM 2 - Day 7 (if no reply)",
    None,
    "Hi {{first_name}},\n\n"
    "One stat that usually gets attention: platforms that embed a native rewards "
    "layer typically see 18 to 25% lift in survey completion rates within the "
    "first quarter.\n\n"
    "If that's on your radar, happy to walk through how the API call actually "
    "works. Otherwise will close the loop.\n\n"
    "Naitik",
    story,
    meta="Stat to be validated by Plum Partnerships before send.",
)


story.append(PageBreak())


story.append(Paragraph("Call Cadence", H2))
story.append(Paragraph(
    "Single dial per contact on Day 7. Voicemail if no answer.",
    NOTE,
))

step(
    "Voicemail (15 seconds)",
    None,
    "Hi {{first_name}}, Naitik from Xoxoday Plum.\n\n"
    "We power the rewards layer inside Qualtrics, SurveyMonkey and Typeform. "
    "Sent you an email and a LinkedIn note about a partnership angle for {{company}}.\n\n"
    "If global response rates and panel retention are on your radar, call me "
    "back at {{phone}}. Thanks.",
    story,
)

step(
    "Live Answer - Opener (10 seconds)",
    None,
    "Hi {{first_name}}, Naitik from Xoxoday Plum here.\n\n"
    "Got 30 seconds? I'll tell you why I'm calling and you tell me if it's "
    "worth more time.",
    story,
)

step(
    "Live Answer - Pitch (30 seconds, after they say yes)",
    None,
    "We run the rewards layer that Qualtrics, SurveyMonkey and Typeform use to "
    "pay survey respondents in 175+ countries and 55+ currencies.\n\n"
    "Most platforms tell us their bottleneck isn't the survey, it's global "
    "fulfillment. PayPal plus Amazon gift cards plus local cash, taped together.\n\n"
    "What does {{company}} do today when a panelist in Brazil or Germany "
    "finishes a survey?",
    story,
)

story.append(Paragraph("Common Objections", H3))

obj_data = [
    ["Objection", "Response"],
    [
        "We already have rewards",
        "What's the geographic coverage today? Most clients hit a wall outside US/UK.",
    ],
    [
        "Send me a deck",
        "Will do, but 10 mins on Zoom is faster. What does Thursday look like?",
    ],
    [
        "Not the right person",
        "Got it, who owns partnerships or marketplace integrations there?",
    ],
    [
        "Not a priority right now",
        "Fair. When does the next roadmap planning happen? Worth being on it.",
    ],
    [
        "We built our own",
        "Makes sense. How is it holding up on global payouts and tax compliance?",
    ],
]
obj_tbl = Table(obj_data, colWidths=[2.0 * inch, 4.5 * inch])
obj_tbl.setStyle(TableStyle([
    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2F5496")),
    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
    ("FONTSIZE", (0, 0), (-1, -1), 9.5),
    ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ("TOPPADDING", (0, 0), (-1, -1), 7),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ("ROWBACKGROUNDS", (0, 1), (-1, -1),
     [colors.white, colors.HexColor("#F5F7FA")]),
    ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#D0D7E2")),
]))
story.append(obj_tbl)


doc.build(story)
print(f"wrote {OUT}")

const fs = require("fs");
const path = require("path");
const {
  Document,
  Packer,
  Paragraph,
  TextRun,
  Table,
  TableRow,
  TableCell,
  AlignmentType,
  HeadingLevel,
  BorderStyle,
  WidthType,
  ShadingType,
  PageBreak,
  LevelFormat,
} = require("docx");

const TITLE_BLUE = "1F3864";
const HEADING_BLUE = "2F5496";
const BODY_DARK = "111111";
const META_GREY = "666666";
const BOX_BG = "F5F7FA";
const BOX_BORDER = "D0D7E2";
const TABLE_HEADER_BG = "2F5496";
const TABLE_ALT_BG = "F5F7FA";

const PAGE_W = 12240;
const PAGE_H = 15840;
const MARGIN = 1080;
const CONTENT_W = PAGE_W - MARGIN * 2;

const border = (color) => ({
  style: BorderStyle.SINGLE,
  size: 4,
  color,
});

const paraText = (text, opts = {}) =>
  new Paragraph({
    spacing: { before: opts.before || 0, after: opts.after || 80 },
    alignment: opts.alignment || AlignmentType.LEFT,
    children: [
      new TextRun({
        text,
        font: opts.font || "Arial",
        size: opts.size || 22,
        bold: !!opts.bold,
        italics: !!opts.italics,
        color: opts.color || BODY_DARK,
      }),
    ],
  });

const heading1 = (text) =>
  new Paragraph({
    heading: HeadingLevel.HEADING_1,
    spacing: { before: 0, after: 200 },
    children: [
      new TextRun({
        text,
        font: "Arial",
        size: 36,
        bold: true,
        color: TITLE_BLUE,
      }),
    ],
  });

const heading2 = (text) =>
  new Paragraph({
    heading: HeadingLevel.HEADING_2,
    spacing: { before: 320, after: 160 },
    children: [
      new TextRun({
        text,
        font: "Arial",
        size: 26,
        bold: true,
        color: HEADING_BLUE,
      }),
    ],
  });

const heading3 = (text) =>
  new Paragraph({
    heading: HeadingLevel.HEADING_3,
    spacing: { before: 240, after: 80 },
    children: [
      new TextRun({
        text,
        font: "Arial",
        size: 22,
        bold: true,
        color: "333333",
      }),
    ],
  });

const metaLine = (text) =>
  new Paragraph({
    spacing: { before: 0, after: 100 },
    children: [
      new TextRun({
        text,
        font: "Arial",
        size: 18,
        italics: true,
        color: META_GREY,
      }),
    ],
  });

const subjectLine = (subject) =>
  new Paragraph({
    spacing: { before: 0, after: 60 },
    children: [
      new TextRun({
        text: "Subject: ",
        font: "Arial",
        size: 20,
        bold: true,
        color: "333333",
      }),
      new TextRun({
        text: subject,
        font: "Arial",
        size: 20,
        bold: true,
        color: BODY_DARK,
      }),
    ],
  });

function codeBlock(lines) {
  const paras = lines.map(
    (line, idx) =>
      new Paragraph({
        spacing: { before: 0, after: idx === lines.length - 1 ? 0 : 60 },
        children: [
          new TextRun({
            text: line || " ",
            font: "Courier New",
            size: 20,
            color: BODY_DARK,
          }),
        ],
      })
  );
  const cell = new TableCell({
    width: { size: CONTENT_W, type: WidthType.DXA },
    shading: { fill: BOX_BG, type: ShadingType.CLEAR, color: "auto" },
    borders: {
      top: border(BOX_BORDER),
      bottom: border(BOX_BORDER),
      left: border(BOX_BORDER),
      right: border(BOX_BORDER),
    },
    margins: { top: 160, bottom: 160, left: 200, right: 200 },
    children: paras,
  });
  return new Table({
    width: { size: CONTENT_W, type: WidthType.DXA },
    columnWidths: [CONTENT_W],
    rows: [new TableRow({ children: [cell] })],
  });
}

function step({ label, subject, meta, body }) {
  const out = [heading3(label)];
  if (meta) out.push(metaLine(meta));
  if (subject) out.push(subjectLine(subject));
  out.push(codeBlock(body.split("\n")));
  out.push(paraText("", { after: 120 }));
  return out;
}

function objectionTable(rows) {
  const headerBorder = {
    top: border(TABLE_HEADER_BG),
    bottom: border(TABLE_HEADER_BG),
    left: border(TABLE_HEADER_BG),
    right: border(TABLE_HEADER_BG),
  };
  const cellBorder = {
    top: border(BOX_BORDER),
    bottom: border(BOX_BORDER),
    left: border(BOX_BORDER),
    right: border(BOX_BORDER),
  };
  const col1 = Math.round(CONTENT_W * 0.30);
  const col2 = CONTENT_W - col1;

  const headerCell = (text) =>
    new TableCell({
      width: { size: text === rows[0][0] ? col1 : col2, type: WidthType.DXA },
      shading: { fill: TABLE_HEADER_BG, type: ShadingType.CLEAR, color: "auto" },
      borders: headerBorder,
      margins: { top: 100, bottom: 100, left: 140, right: 140 },
      children: [
        new Paragraph({
          spacing: { before: 0, after: 0 },
          children: [
            new TextRun({
              text,
              font: "Arial",
              size: 19,
              bold: true,
              color: "FFFFFF",
            }),
          ],
        }),
      ],
    });

  const bodyCell = (text, width, alt) =>
    new TableCell({
      width: { size: width, type: WidthType.DXA },
      shading: alt
        ? { fill: TABLE_ALT_BG, type: ShadingType.CLEAR, color: "auto" }
        : undefined,
      borders: cellBorder,
      margins: { top: 100, bottom: 100, left: 140, right: 140 },
      children: [
        new Paragraph({
          spacing: { before: 0, after: 0 },
          children: [
            new TextRun({
              text,
              font: "Arial",
              size: 19,
              color: BODY_DARK,
            }),
          ],
        }),
      ],
    });

  const tableRows = [
    new TableRow({
      tableHeader: true,
      children: [headerCell(rows[0][0]), headerCell(rows[0][1])],
    }),
  ];
  for (let i = 1; i < rows.length; i++) {
    const alt = i % 2 === 0;
    tableRows.push(
      new TableRow({
        children: [bodyCell(rows[i][0], col1, alt), bodyCell(rows[i][1], col2, alt)],
      })
    );
  }

  return new Table({
    width: { size: CONTENT_W, type: WidthType.DXA },
    columnWidths: [col1, col2],
    rows: tableRows,
  });
}

const children = [];

children.push(heading1("Plum x Survey Platforms - Outbound Cadence"));
children.push(
  paraText(
    "Email, LinkedIn, and Call sequence for partnership outreach to survey platform Product and BD leaders.",
    { italics: true, color: META_GREY, size: 20, after: 200 }
  )
);

children.push(heading2("Email Sequence"));

children.push(
  ...step({
    label: "Email 1 - Day 1",
    subject: "Survey response rates",
    meta: "Cold opener. No signature - Smartlead appends at account level.",
    body:
      "Survey response rates dropped below 15% industry-wide.\n" +
      "Most platforms patch this with incentives, but fulfillment breaks at global scale.\n" +
      "Plum integrates with Qualtrics, SurveyMonkey, and Typeform today.\n" +
      "How is {{company}} handling respondent rewards across regions?",
  })
);

children.push(
  ...step({
    label: "Email 2 - Day 4 (bump)",
    subject: "Re: Survey response rates",
    body:
      "Bumping this up.\n" +
      "Three reasons panelists churn most often: slow payouts, no local currency, irrelevant rewards.\n" +
      "Plum handles all three through one REST endpoint, in 175+ countries.\n" +
      "Worth a 15-min look this week?",
  })
);

children.push(
  ...step({
    label: "Email 3 - Day 8 (breakup)",
    subject: "Closing the loop",
    body:
      "Closing this loop on my end.\n" +
      "If incentivized response rates land back on your roadmap, ping me.\n" +
      "If not, no worries.\n" +
      "Wish you the best with {{company}}.",
  })
);

children.push(new Paragraph({ children: [new PageBreak()] }));

children.push(heading2("LinkedIn Sequence"));
children.push(
  paraText(
    "Runs in parallel with email. Kicks off Day 2 with a connection request.",
    { italics: true, color: META_GREY, size: 20, after: 160 }
  )
);

children.push(
  ...step({
    label: "Connection Request - Day 2",
    meta: "Keep under 300 characters. LinkedIn limit applies.",
    body:
      "Hi {{first_name}}, working on rewards and payouts infrastructure for survey platforms. Would love to compare notes on global respondent incentivization.\n\n" +
      "Naitik",
  })
);

children.push(
  ...step({
    label: "DM 1 - Day 3 (or 24h after they accept)",
    body:
      "Thanks for connecting, {{first_name}}.\n\n" +
      "Quick context on why I reached out. Plum runs the rewards layer inside Qualtrics, SurveyMonkey and Typeform. Response rates and panel retention keep coming up in those conversations.\n\n" +
      "Curious how {{company}} is approaching global incentive fulfillment today?\n\n" +
      "Naitik",
  })
);

children.push(
  ...step({
    label: "DM 2 - Day 7 (if no reply)",
    meta: "Stat to be validated by Plum Partnerships before send.",
    body:
      "Hi {{first_name}},\n\n" +
      "One stat that usually gets attention: platforms that embed a native rewards layer typically see 18 to 25% lift in survey completion rates within the first quarter.\n\n" +
      "If that's on your radar, happy to walk through how the API call actually works. Otherwise will close the loop.\n\n" +
      "Naitik",
  })
);

children.push(new Paragraph({ children: [new PageBreak()] }));

children.push(heading2("Call Cadence"));
children.push(
  paraText("Single dial per contact on Day 7. Voicemail if no answer.", {
    italics: true,
    color: META_GREY,
    size: 20,
    after: 160,
  })
);

children.push(
  ...step({
    label: "Voicemail (15 seconds)",
    body:
      "Hi {{first_name}}, Naitik from Xoxoday Plum.\n\n" +
      "We power the rewards layer inside Qualtrics, SurveyMonkey and Typeform. Sent you an email and a LinkedIn note about a partnership angle for {{company}}.\n\n" +
      "If global response rates and panel retention are on your radar, call me back at {{phone}}. Thanks.",
  })
);

children.push(
  ...step({
    label: "Live Answer - Opener (10 seconds)",
    body:
      "Hi {{first_name}}, Naitik from Xoxoday Plum here.\n\n" +
      "Got 30 seconds? I'll tell you why I'm calling and you tell me if it's worth more time.",
  })
);

children.push(
  ...step({
    label: "Live Answer - Pitch (30 seconds, after they say yes)",
    body:
      "We run the rewards layer that Qualtrics, SurveyMonkey and Typeform use to pay survey respondents in 175+ countries and 55+ currencies.\n\n" +
      "Most platforms tell us their bottleneck isn't the survey, it's global fulfillment. PayPal plus Amazon gift cards plus local cash, taped together.\n\n" +
      "What does {{company}} do today when a panelist in Brazil or Germany finishes a survey?",
  })
);

children.push(heading3("Common Objections"));
children.push(
  objectionTable([
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
  ])
);

const doc = new Document({
  creator: "Xoxoday Global API",
  title: "Plum x Survey Partners - Outbound Cadence",
  styles: {
    default: { document: { run: { font: "Arial", size: 22 } } },
    paragraphStyles: [
      {
        id: "Heading1",
        name: "Heading 1",
        basedOn: "Normal",
        next: "Normal",
        quickFormat: true,
        run: { size: 36, bold: true, font: "Arial", color: TITLE_BLUE },
        paragraph: { spacing: { before: 240, after: 200 }, outlineLevel: 0 },
      },
      {
        id: "Heading2",
        name: "Heading 2",
        basedOn: "Normal",
        next: "Normal",
        quickFormat: true,
        run: { size: 26, bold: true, font: "Arial", color: HEADING_BLUE },
        paragraph: { spacing: { before: 320, after: 160 }, outlineLevel: 1 },
      },
      {
        id: "Heading3",
        name: "Heading 3",
        basedOn: "Normal",
        next: "Normal",
        quickFormat: true,
        run: { size: 22, bold: true, font: "Arial", color: "333333" },
        paragraph: { spacing: { before: 240, after: 80 }, outlineLevel: 2 },
      },
    ],
  },
  sections: [
    {
      properties: {
        page: {
          size: { width: PAGE_W, height: PAGE_H },
          margin: { top: MARGIN, right: MARGIN, bottom: MARGIN, left: MARGIN },
        },
      },
      children,
    },
  ],
});

const outPath = path.join(__dirname, "Plum_Survey_Partners_Cadence.docx");
Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync(outPath, buf);
  console.log("wrote " + outPath + " (" + buf.length + " bytes)");
});

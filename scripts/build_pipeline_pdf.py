"""
Builds ABM_Contact_Enrichment_Pipeline.pdf, styled to match the reference
doc (Xoxoday_Complete_Lifecycle_Automation.pdf): purple title page, gray
top-right header on content pages, centered "Page X of Y" footer, numbered
sections, a dot-leader table of contents, and light-gray-header tables.

Two-pass build: first pass renders the story once, recording which page
number each heading landed on (via a zero-size marker flowable); second
pass rebuilds the same content with that data available for the ToC page.
"""
import os
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, Table, TableStyle,
    Preformatted, Flowable, PageBreak, NextPageTemplate, KeepTogether,
)

PURPLE = colors.HexColor('#6D28D9')
GRAY = colors.HexColor('#6B7280')
LIGHT_GRAY = colors.HexColor('#E5E5E5')
BORDER_GRAY = colors.HexColor('#B0B0B0')
DOC_TITLE = 'Xoxoday — ABM Contact Enrichment Pipeline'
OUT_PATH = os.path.join(os.path.dirname(__file__), '..', 'ABM_Contact_Enrichment_Pipeline.pdf')

styles = getSampleStyleSheet()
body_style = ParagraphStyle('Body', parent=styles['Normal'], fontName='Helvetica', fontSize=10, leading=14, spaceAfter=8)
h1_style = ParagraphStyle('H1', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=15, spaceBefore=14, spaceAfter=8, textColor=colors.black)
h2_style = ParagraphStyle('H2', parent=styles['Heading2'], fontName='Helvetica-Bold', fontSize=12, spaceBefore=10, spaceAfter=6, textColor=colors.black)
title_purple = ParagraphStyle('TitlePurple', fontName='Helvetica-Bold', fontSize=30, leading=38, textColor=PURPLE, alignment=TA_CENTER)
title_black = ParagraphStyle('TitleBlack', fontName='Helvetica-Bold', fontSize=17, leading=22, textColor=colors.black, alignment=TA_CENTER, spaceBefore=22)
title_date = ParagraphStyle('TitleDate', fontName='Helvetica', fontSize=10, textColor=GRAY, alignment=TA_CENTER, spaceBefore=8)
toc_heading = ParagraphStyle('TOCHeading', fontName='Helvetica-Bold', fontSize=15, spaceAfter=14)
cell_style = ParagraphStyle('Cell', fontName='Helvetica', fontSize=8.5, leading=11)
cell_header_style = ParagraphStyle('CellHeader', fontName='Helvetica-Bold', fontSize=8.5, leading=11)
pre_style = ParagraphStyle('Pre', fontName='Courier', fontSize=7.5, leading=9.5, textColor=colors.black)


class PageMarker(Flowable):
    """Zero-size flowable that records the page number it lands on."""
    def __init__(self, key, registry):
        Flowable.__init__(self)
        self.key = key
        self.registry = registry

    def wrap(self, availWidth, availHeight):
        return (0, 0)

    def draw(self):
        self.registry[self.key] = self.canv.getPageNumber()


def header_footer(canvas, doc, total_pages=None):
    canvas.saveState()
    page_num = canvas.getPageNumber()
    if page_num > 1:
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(GRAY)
        canvas.drawRightString(letter[0] - 0.75 * inch, letter[1] - 0.6 * inch, DOC_TITLE)
    canvas.setFont('Helvetica', 8)
    canvas.setFillColor(GRAY)
    total = total_pages if total_pages else '?'
    canvas.drawCentredString(letter[0] / 2, 0.5 * inch, f"Page {page_num} of {total}")
    canvas.restoreState()


def make_table(headers, rows, col_widths):
    data = [[Paragraph(h, cell_header_style) for h in headers]]
    for row in rows:
        data.append([Paragraph(str(c), cell_style) for c in row])
    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), LIGHT_GRAY),
        ('GRID', (0, 0), (-1, -1), 0.5, BORDER_GRAY),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
    ]))
    return t


# ---------------------------------------------------------------- content

SECTIONS = [
    ('h1', 's1', '1. Problem Statement', None),
    ('p', None, None,
     "Every outbound list handed to this pipeline starts as a raw export &mdash; a conference attendee sheet, "
     "a target-account list, a company list with job titles attached. None of it is safe to load into Smartlead "
     "or HeyReach as-is: company names are unnormalized, domains are unknown or ambiguous, some fraction of the "
     "list is already a customer, and named contacts have no verified way to reach them."),
    ('p', None, None,
     "Two runs this month illustrate the failure modes a manual process misses. On a 128-row UK/EUR list, "
     "4 companies turned out to be active client relationships that would have been cold-emailed by mistake. "
     "On a 150-row Indonesia/Philippines company list, a short, generic company name (&ldquo;Flip&rdquo;) nearly "
     "resolved to an unrelated Indonesian fintech instead of the intended German HR-tech company &mdash; the "
     "same failure mode a human skimming a spreadsheet has no reliable way to catch."),
    ('p', None, None,
     "This pipeline replaces that manual check with a sequence of stages that never guesses when it isn't "
     "confident &mdash; a wrong-company match or an unverified contact detail is treated as a bug, not an "
     "acceptable miss rate. Ambiguity gets surfaced for a five-second human decision instead of silently resolved."),

    ('h1', 's2', '2. Complete Pipeline Flow', None),
    ('p', None, None,
     "The pipeline is a straight-line waterfall with one fork (named list vs. company-only list) and a persistent "
     "cache layer underneath every stage, so a company or contact resolved once is never re-processed or re-paid for."),
    ('pre', None, None,
     "                    LIST ARRIVES  (CSV or list link)\n"
     "                            |\n"
     "                            v\n"
     "        +----------------------------------+\n"
     "        |  1. SUPPRESSION (Exclusion Check) |   Hunting -> check vs Account Mapping Sheet\n"
     "        |                                    |   Farming -> skip, everyone passes\n"
     "        +-----------------+------------------+\n"
     "                          v\n"
     "        +----------------------------------+\n"
     "        |  2. NORMALIZATION                 |   Clean names + company names\n"
     "        +-----------------+------------------+\n"
     "                          v\n"
     "        +----------------------------------+\n"
     "        |  3. DOMAIN RESOLUTION              |   Cache -> Apollo -> majority-vote ->\n"
     "        |                                    |   employee-count -> flag if unsure\n"
     "        +-----------------+------------------+\n"
     "                          v\n"
     "          Named contacts already? --- YES ------------+\n"
     "                          | NO                          |\n"
     "                          v                              |\n"
     "        +----------------------------------+            |\n"
     "        |  4. PEOPLE DISCOVERY               |            |\n"
     "        |     (Apollo search, free)          |            |\n"
     "        +-----------------+------------------+            |\n"
     "                          +-------------------+-----------+\n"
     "                                              v\n"
     "        +--------------------------------------------+\n"
     "        |  5. EMAIL ENRICHMENT                        |\n"
     "        |     Apollo -> Lusha -> ZeroBounce validate  |\n"
     "        |     (domain-match safety check throughout)  |\n"
     "        +---------------------+------------------------+\n"
     "                              v\n"
     "        +--------------------------------------------+\n"
     "        |  6. PHONE ENRICHMENT (optional, costed)     |\n"
     "        |     Apollo async reveal, cached             |\n"
     "        +---------------------+------------------------+\n"
     "                              v\n"
     "        +--------------------------------------------+\n"
     "        |  7. OUTPUT ASSEMBLY                         |\n"
     "        |     Email / LinkedIn / Calling /            |\n"
     "        |     Needs-Manual-Review                     |\n"
     "        +----------------------------------------------+"),

    ('h1', 's3', '3. Stage Walkthrough', None),
    ('p', None, None, "Each section covers one stage &mdash; the trigger, the exact logic, and the reasoning behind the design decision."),

    ('h2', 's3.1', '3.1 Suppression (Exclusion Check)', None),
    ('p', None, None,
     "Runs first, before anything else touches the list, so no downstream credits get spent on a company we "
     "shouldn't be emailing at all."),
    ('p', None, None,
     "Ask which campaign type this is before running anything. <b>Farming</b> campaigns skip this stage entirely "
     "&mdash; every company passes through. <b>Hunting</b> campaigns check every company against the master "
     "Account Mapping Sheet (Client Name, Domain, Parent Company, Type 1, Parent Company Status), matching in "
     "order: exact domain &rarr; fuzzy client name (legal suffixes stripped) &rarr; fuzzy parent company. A "
     "prospect is <b>OK to reach out</b> only if the matched row's Type 1 status <i>and</i> Parent Company Status "
     "are both <i>Dead</i>. Anything else on a matched row is <b>Excluded</b> &mdash; the conservative read, since "
     "a false exclusion costs one lead, but a false inclusion means cold-emailing an existing customer. No match "
     "at all means it's a genuinely new account and passes through."),
    ('p', None, None, "Output columns: <font face='Courier'>Exclusion Status</font>, <font face='Courier'>Exclusion Reason</font>, <font face='Courier'>Matched Account</font>."),

    ('h2', 's3.2', '3.2 Normalization', None),
    ('p', None, None,
     "Cleans the surviving rows before anything gets searched against an external API &mdash; inconsistent "
     "casing and legal-entity suffixes (&ldquo;Pvt Ltd&rdquo;, &ldquo;Inc.&rdquo;, &ldquo;(P) Ltd&rdquo;) reduce "
     "match quality downstream, so they're stripped here once rather than fought individually at each later stage."),
    ('p', None, None,
     "Splits a Full Name into First/Last (first token &rarr; first name, everything else &rarr; last name). "
     "Strips honorific prefixes and degree/generational suffixes from names. Strips legal-entity suffixes from "
     "company names. Originals are always preserved alongside the cleaned columns, never overwritten."),

    ('h2', 's3.3', '3.3 Domain Resolution', None),
    ('p', None, None,
     "The highest-risk stage in the pipeline &mdash; a wrong domain here means every downstream email search "
     "targets the wrong real company. Never guesses when uncertain."),
    ('p', None, None,
     "Checks the shared cache first (instant, free, and grows with every list run). On a cache miss, searches "
     "Apollo's organization directory by the cleaned company name. If Apollo returns exactly one exact-name "
     "match, accept it. If it returns several, first check whether they already agree on the same domain &mdash; "
     "large companies frequently have duplicate/fragmented org records under an identical display name, and "
     "treating that as ambiguous would falsely block obvious cases (Ernst &amp; Young showed up as 18 "
     "near-duplicate records, all pointing to <font face='Courier'>ey.com</font>). Only when the candidates "
     "genuinely disagree on domain does it fall to employee-count comparison against the source list's headcount "
     "column, and only when <i>that</i> produces a clear winner does it accept automatically. Anything left "
     "&mdash; no employee-count signal, or a real split decision &mdash; is flagged <b>Ambiguous</b> with the "
     "full candidate list, for a human to pick in seconds rather than the pipeline guessing wrong. Zero "
     "exact-name matches at all is flagged <b>Unresolved</b>, which typically means a small/regional company or "
     "a stale legacy brand name that needs a quick web search."),
    ('p', None, None, "Output columns: <font face='Courier'>Resolved Domain</font>, <font face='Courier'>Resolved Company LinkedIn</font>, <font face='Courier'>Resolution Source</font>."),

    ('h2', 's3.4', '3.4 People Discovery', None),
    ('p', None, None,
     "Only runs when the input list is company names without named contacts. Runs before any credits are spent "
     "&mdash; a person-search query against Apollo is free; only revealing a specific person's contact details "
     "costs credits."),
    ('p', None, None,
     "Searches Apollo by company domain plus the target job titles, with a seniority filter (c_suite, vp, head, "
     "director, manager) applied at the query level &mdash; without it, a single page of title-matched results at "
     "a large company gets swamped by hundreds of lower-level hits and the actual decision-maker never surfaces. "
     "Search results come back with an obfuscated last name (e.g. &ldquo;Laura Bu***r&rdquo;) plus flags for "
     "whether Apollo has email/phone data on file &mdash; real names and contact details are revealed in a "
     "separate, credit-costed step. Candidates are ranked by how senior their title is, one distinct seniority "
     "tier covered before doubling up on any tier, up to a configurable cap per company."),

    ('h2', 's3.5', '3.5 Email Enrichment', None),
    ('p', None, None,
     "The core enrichment step, and the one that most needs its own safety net &mdash; a &ldquo;verified&rdquo; "
     "email from any single provider is not proof it belongs to the company you're searching for."),
    ('p', None, None,
     "Calls Apollo's contact match (by Apollo ID when available, otherwise name + domain) and checks the "
     "returned email's domain against the company domain being searched. A match is accepted outright; a known "
     "alias (a confirmed rebrand, an M&amp;A absorption, or a company that genuinely emails from a different "
     "domain than its marketing site) is also accepted; a same-brand name under a different country code (any "
     "large multinational professional-services network) is also accepted. Anything else is held as a "
     "<b>mismatch</b> for manual review rather than trusted or discarded automatically. Contacts Apollo can't "
     "find an email for at all fall to a second waterfall step through Lusha, using the same domain-match check, "
     "and any Lusha hit must additionally pass ZeroBounce validation before it's accepted."),

    ('h2', 's3.6', '3.6 Phone Enrichment', None),
    ('p', None, None,
     "Optional, and meaningfully more expensive than email &mdash; treat this as a deliberate scope decision, "
     "not something to default on for a large list."),
    ('p', None, None,
     "Apollo's phone reveal is asynchronous: it never returns a number in the direct response, only via a "
     "webhook callback seconds later, so this stage needs an internet-facing relay to receive it. Confirmed "
     "through testing: Apollo does not call the webhook at all when it has no phone data &mdash; a missing "
     "callback means &ldquo;nothing on file,&rdquo; not a slow response, so the wait window can stay short. "
     "Every successful reveal is cached (keyed by contact, not by list) so the same person is never paid for "
     "twice across runs, even in a future, unrelated list."),

    ('h2', 's3.7', '3.7 Output Assembly', None),
    ('p', None, None,
     "Splits the fully-enriched list into channel-specific files so each downstream tool only sees what it "
     "needs, plus a bucket for anything that didn't clear the bar. Nothing that fails a check gets silently "
     "dropped &mdash; every non-accepted row lands in the Needs Manual Review file with the reason attached."),

    ('h1', 's4', '4. Script Specification', None),
    ('table', None, None, (
        ['Stage', 'Script', 'Calls', 'Output'],
        [
            ['Suppression', 'abm-exclusion-check skill', '&mdash; (local match)', 'Exclusion Status / Reason / Matched Account'],
            ['Normalization', 'name-company-normalizer skill', '&mdash; (local match)', 'Cleaned First/Last/Company Name'],
            ['Domain Resolution', 'resolve_company_domains.py', 'Apollo Org Search', 'Resolved Domain / LinkedIn / Source'],
            ['People Discovery', 'search_company_contacts_apollo.py', 'Apollo People Search (free)', 'apollo_id / title / persona_tier / has_email'],
            ['Email Enrichment', 'enrich_contacts_apollo.py', 'Apollo People Match', 'email / email_status / linkedin_apollo / note'],
            ['Email Waterfall', 'lusha_waterfall_enrich.py', 'Lusha Search &amp; Enrich + ZeroBounce', 'lusha_email / zerobounce_status / lusha_note'],
            ['Phone Enrichment', 'enrich_phone_apollo.py', 'Apollo Match (async) + webhook.site', 'Phone Number / Type / Confidence / Note'],
            ['Phone Comparison', 'lusha_phone_compare.py', 'Lusha Search &amp; Enrich', 'Apollo vs. Lusha phone side-by-side'],
        ],
        [1.2 * inch, 1.7 * inch, 1.7 * inch, 1.9 * inch],
    )),

    ('h1', 's5', '5. Configuration Reference', None),
    ('p', None, None, "Every knob worth tuning, where it lives, and what changing it actually does."),
    ('table', None, None, (
        ['Stage', 'Parameter', 'Location', 'Default', 'Controls'],
        [
            ['Suppression', 'Campaign type', 'Asked at runtime', '&mdash;', 'Whether exclusion logic applies at all (Farming = skip)'],
            ['Suppression', 'Fuzzy match threshold', 'check_exclusions.py', '0.88', 'How lenient company-name matching is'],
            ['Domain Resolution', 'Shared cache', 'reference/company_domain_cache.csv', 'grows over time', 'Instant, free resolution for any company seen before'],
            ['Domain Resolution', 'Majority-domain threshold', 'resolve_company_domains.py', '&gt;50% of candidates', 'Duplicate records treated as agreement vs. real ambiguity'],
            ['Domain Resolution', 'Employee-count ambiguity gate', 'resolve_company_domains.py', 'gap&gt;0.5, diff&lt;0.15', 'When to flag instead of auto-picking by headcount'],
            ['Domain Resolution', 'Legal-suffix list', 'resolve_company_domains.py', 'Inc/Ltd/Corp/PLC/etc.', 'Which suffixes get stripped before name comparison'],
            ['Domain Resolution', 'Apollo search page size', 'resolve_company_domains.py', '25', 'How many candidates get pulled before giving up'],
            ['People Discovery', 'Target job titles', 'PERSONAS list', '17 HR-function titles', 'Which roles get searched for at each company'],
            ['People Discovery', 'Seniority filter', 'search_company_contacts_apollo.py', 'c_suite, vp, head, director, manager', 'Which seniority levels Apollo returns'],
            ['People Discovery', 'Max contacts per company', 'MAX_PER_COMPANY', '10', 'Contact volume cap per company'],
            ['Email Enrichment', 'Known domain aliases', 'reference/domain_aliases.csv', 'grows over time', 'Which mismatched domains are actually legitimate'],
            ['Email Enrichment', 'Country-variant matching', 'domain_root() function', 'root name &ge;4 chars', 'Auto-accepts same-brand, different-country-TLD emails'],
            ['Email Waterfall', 'Run Lusha at all?', 'Asked at runtime', '&mdash;', 'Whether to spend Lusha credits on Apollo misses'],
            ['Email Waterfall', 'ZeroBounce acceptance', 'lusha_waterfall_enrich.py', 'valid, catch-all', 'How strict validation is before accepting a Lusha email'],
            ['Phone Enrichment', 'Run phone at all?', 'Asked at runtime', 'off by default', 'Cost gate &mdash; phone is ~8x the credit cost of email'],
            ['Phone Enrichment', 'Poll timeout', 'POLL_TIMEOUT', '30s', 'How long to wait for Apollo\'s async webhook callback'],
            ['Phone Enrichment', 'Persistent cache', 'reference/phone_reveal_cache.csv', 'grows over time', 'Never re-pay for a phone number already revealed'],
            ['Phone Enrichment', 'Cache invalidation', 'Manual &mdash; delete the row', 'none automatic', 'No job-change detection; stale numbers cleared by hand'],
        ],
        [0.9 * inch, 1.15 * inch, 1.35 * inch, 1.1 * inch, 2.0 * inch],
    )),

    ('h1', 's6', '6. Technical Implementation', None),
    ('table', None, None, (
        ['Layer', 'Responsibility', 'Technology'],
        [
            ['Orchestrator', 'Decide campaign type, sequence stages, gate costly steps behind explicit go-ahead', 'Agent session (this pipeline)'],
            ['Suppression', 'Match prospects against the master Account Mapping Sheet', 'Python + fuzzy match'],
            ['Normalization', 'Clean names and company names', 'Python'],
            ['Domain Resolution', 'Resolve and cache company domains', 'Apollo Org Search API + persistent CSV cache'],
            ['People Discovery', 'Find named contacts at target companies', 'Apollo People Search API (no cost)'],
            ['Email Enrichment', 'Reveal and validate verified emails', 'Apollo People Match &rarr; Lusha &rarr; ZeroBounce'],
            ['Phone Enrichment', 'Reveal verified mobile numbers', 'Apollo async reveal via webhook relay + cache'],
            ['Output', 'Assemble channel-specific deliverables', 'Python / pandas'],
        ],
        [1.4 * inch, 3.1 * inch, 2.0 * inch],
    )),

    ('h2', 's6.1', '6.1 Enrichment Waterfall Pipeline', None),
    ('table', None, None, (
        ['Step', 'Action', 'Details'],
        [
            ['1. SUPPRESS', 'Check against client list', 'Domain / name / parent-company match, Hunting campaigns only'],
            ['2. CLEAN', 'Normalize names and companies', 'Strip suffixes, split full names'],
            ['3. RESOLVE', 'Find each company\'s domain', 'Cache &rarr; Apollo &rarr; majority-vote &rarr; employee-count &rarr; flag'],
            ['4. DISCOVER', 'Find people, if not already named', 'Apollo search by title + seniority, free'],
            ['5. VERIFY EMAIL', 'Reveal and validate', 'Apollo &rarr; Lusha &rarr; ZeroBounce'],
            ['6. VERIFY PHONE', 'Reveal, optional', 'Apollo webhook reveal, cached per contact'],
            ['7. ASSEMBLE', 'Build deliverables', 'Email / LinkedIn / Calling / Needs Manual Review'],
        ],
        [1.1 * inch, 2.0 * inch, 3.4 * inch],
    )),

    ('h2', 's6.2', '6.2 Environment & API Requirements', None),
    ('table', None, None, (
        ['Requirement', 'Details'],
        [
            ['API keys', 'APOLLO_API_KEY, LUSHA_API_KEY, ZEROBOUNCE_API_KEY, SMARTLEAD_API_KEY, HEYREACH_API_KEY &mdash; all in .env, never printed'],
            ['Reference files', 'company_domain_cache.csv, phone_reveal_cache.csv, domain_aliases.csv &mdash; self-updating, shared across future lists'],
            ['Master data source', 'Account Mapping Sheet, sourced from HubSpot (read-only &mdash; never written back to)'],
            ['Cost model', 'Apollo email &asymp;1 credit/hit &middot; Apollo phone &asymp;8 credits/hit &middot; Lusha &asymp;6 credits/hit &middot; ZeroBounce &asymp;1/check'],
            ['Third-party relay', 'webhook.site &mdash; created fresh per phone-enrichment run, deleted immediately after; no permanent PII storage'],
        ],
        [1.6 * inch, 4.9 * inch],
    )),
]

TOC_ENTRIES = [
    ('s1', '1. Problem Statement'),
    ('s2', '2. Complete Pipeline Flow'),
    ('s3', '3. Stage Walkthrough'),
    ('s3.1', '     3.1 Suppression (Exclusion Check)'),
    ('s3.2', '     3.2 Normalization'),
    ('s3.3', '     3.3 Domain Resolution'),
    ('s3.4', '     3.4 People Discovery'),
    ('s3.5', '     3.5 Email Enrichment'),
    ('s3.6', '     3.6 Phone Enrichment'),
    ('s3.7', '     3.7 Output Assembly'),
    ('s4', '4. Script Specification'),
    ('s5', '5. Configuration Reference'),
    ('s6', '6. Technical Implementation'),
    ('s6.1', '     6.1 Enrichment Waterfall Pipeline'),
    ('s6.2', '     6.2 Environment & API Requirements'),
]


def build_full_story(registry, sections_source):
    """Rebuild the actual content story (used for both passes)."""
    story = []
    story.append(Spacer(1, 2.4 * inch))
    story.append(Paragraph('Xoxoday', title_purple))
    story.append(Paragraph('ABM Contact Enrichment Pipeline', title_black))
    story.append(Paragraph('July 2026', title_date))
    story.append(NextPageTemplate('content'))
    story.append(PageBreak())

    story.append(Paragraph('Table of Contents', toc_heading))
    toc_rows = []
    for key, label in TOC_ENTRIES:
        page = registry.get(key, '')
        dots = '.' * max(3, 90 - len(label))
        toc_rows.append([Paragraph(f"{label} {dots}", ParagraphStyle('toc', fontName='Helvetica', fontSize=9.5, leading=14)), str(page)])
    toc_table = Table(toc_rows, colWidths=[5.6 * inch, 0.5 * inch])
    toc_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('TOPPADDING', (0, 0), (-1, -1), 1),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1),
    ]))
    story.append(toc_table)
    story.append(PageBreak())

    for entry in sections_source:
        kind, key, title, text = entry
        if kind in ('h1', 'h2') and key:
            story.append(PageMarker(key, registry))
        if kind == 'h1':
            story.append(Paragraph(title, h1_style))
        elif kind == 'h2':
            story.append(Paragraph(title, h2_style))
        elif kind == 'p':
            story.append(Paragraph(text, body_style))
        elif kind == 'pre':
            story.append(KeepTogether([Preformatted(text, pre_style), Spacer(1, 8)]))
        elif kind == 'table':
            headers, rows, widths = text
            story.append(make_table(headers, rows, widths))
            story.append(Spacer(1, 10))
    return story


def build_doc(path, registry, total_pages=None):
    doc = BaseDocTemplate(path, pagesize=letter,
                           topMargin=0.9 * inch, bottomMargin=0.8 * inch,
                           leftMargin=0.75 * inch, rightMargin=0.75 * inch)
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id='normal')
    title_template = PageTemplate(id='title', frames=[frame], onPage=lambda c, d: header_footer(c, d, total_pages))
    content_template = PageTemplate(id='content', frames=[frame], onPage=lambda c, d: header_footer(c, d, total_pages))
    doc.addPageTemplates([title_template, content_template])
    story = build_full_story(registry, SECTIONS)
    doc.build(story)
    return doc


def main():
    # Pass 1: render to a throwaway path, recording page numbers per heading.
    registry = {}
    tmp_path = OUT_PATH + '.tmp.pdf'
    doc = build_doc(tmp_path, registry)
    total_pages = doc.page

    # Pass 2: rebuild with correct ToC page numbers and known total for footer.
    build_doc(OUT_PATH, registry, total_pages=total_pages)
    os.remove(tmp_path)
    print(f"Built {OUT_PATH} ({total_pages} pages)")


if __name__ == '__main__':
    main()

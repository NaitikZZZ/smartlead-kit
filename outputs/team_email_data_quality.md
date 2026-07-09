**Subject:** P0 Passive Pipeline - Data Quality Audit Before Campaign Launch (257 leads flagged)

Hi team,

As part of the P0 Passive Pipeline campaign prep (Global API / Plum), we ran a full data quality audit on all 945 leads from the ABM Tracker. The goal was to verify emails, enrich LinkedIn URLs, and pull phone numbers before pushing to Smartlead and HeyReach.

**The good news:** 688 leads (73%) are campaign-ready with verified work emails, and 546 of those are fully loaded across all three channels (email, LinkedIn, phone).

**The concern:** 257 leads (27%) have data quality issues that make them unusable in their current state. I've attached the full breakdown as a CSV (`bad_data_257_for_team_review.csv`) with a `data_issues` column flagging exactly what's wrong per lead.

Here's the summary:

**Email Issues**
- 118 leads have emails that bounce (ZeroBounce validated as invalid)
- 51 leads are flagged as do-not-mail (toxic, disposable, or spam-trap addresses)
- 49 leads only have generic role emails (info@, admin@, connect@, cms@) with no actual person identified
- 23 leads have emails that couldn't be verified at all

**Contact Data Gaps**
- 176 leads have no contact name (first or last)
- 92 leads have no job title
- 192 leads have no LinkedIn profile found across Apollo, Clay, or any enrichment provider

**Why this matters for a passive pipeline:**
These are deals that were created in HubSpot at some point, meaning someone on the team engaged with these accounts. A few patterns that stand out:

1. Deals created against generic emails (info@, admin@) rather than an actual stakeholder. These were never real contacts.
2. Emails that have since bounced, likely because the contact left the company. The deal was never updated.
3. Deals with no contact name or title, making it impossible to personalize outreach or even confirm we're reaching the right person.

**What I'd recommend:**
- For the 118 bounced emails: check if there's a newer contact at the same company in HubSpot or re-enrich via Sales Nav
- For the 49 generic emails: replace with an actual decision maker (Head of Product, CTO, VP Partnerships, etc.)
- For the 176 with no name: these need basic contact identification before they can be used in any outbound motion

**What we're doing in the meantime:**
- The 688 verified leads are being loaded into Smartlead (email campaign) and HeyReach (LinkedIn campaign) across three segments
- 65 of the 257 flagged leads do have a LinkedIn URL, so those will still go into HeyReach even though we can't email them
- The remaining 192 are on hold until the data is cleaned

The attached CSV has every flagged lead with the specific issues listed. Happy to walk through it if useful.

Thanks,
Naitik

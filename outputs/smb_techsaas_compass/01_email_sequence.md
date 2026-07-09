# Compass Email Sequence (Smartlead, single campaign, 5 steps)

> Buyer: VP / Head / Director of Sales at Indian SMB Tech SaaS (200 to 1,800 FTE), covering both direct AE motion and channel/partner motion.
> Tone: blunt, peer-to-peer, India-flavored. No fluff, no AI tells, no em-dashes.
> No sign-off in `email_body`. Smartlead auto-appends the sender signature at the account level.
>
> **Single Smartlead campaign for all 26 leads.** Email body speaks to both AE-comp and partner-payout pain in one frame. The 4 channel-flagged leads still get a slightly different SDR call opener and LinkedIn DM, those touches are manual.

---

## Step 1, Day 0, Problem Hook

A/B/C subject test on the same body. Smartlead distributes equally.

**Subject A:** `{{first_name}}, how is {{company_name}} running sales incentives this quarter`
**Subject B:** `quick one on the {{company_name}} comp + SPIFF stack`
**Subject C:** `{{first_name}}, the spreadsheet behind your reps' and partners' payouts`

```html
<p>Hi {{first_name}},</p>

<p>Most Sales heads I speak to in Indian SaaS run their incentives, AE commissions, partner SPIFFs, contest payouts, and lead-reg bonuses, on a Sheet that one RevOps person owns. It eats 5 to 7 days every month.</p>

<p>The bigger cost is trust. Reps and partners shadow-track their own numbers, escalate disputes, and stop believing accelerators are real.</p>

<p>Compass, the sales incentives module of Empuls, replaces that sheet. Every AE and partner at {{company_name}} sees what they have earned in real time, every plan change goes live in a day, and Finance gets a clean audit trail. Payouts flow through Plum so rewards land in 100+ countries as cash, gift cards, or experiences. Pepsico, Hershey's, Capgemini, and Aditya Birla Capital run on it.</p>

<p>Worth a 20 min look for {{company_name}}? Happy to come prepared with how SaaS teams your size structure plans for both internal reps and channel partners.</p>
```

---

## Step 2, Day 3, Day-in-the-Life

**Subject:** `Re: {{first_name}}, how is {{company_name}} running sales incentives this quarter`

```html
<p>{{first_name}}, bumping this.</p>

<p>To make it concrete, here is what month-end looks like for a 60-rep SaaS team plus 80 active partners after Compass:</p>

<ul>
  <li>RevOps closes the comp + partner-payout run in under 2 hours, not 5 days</li>
  <li>Every AE and partner has a personal dashboard: quota attained, deals counted, accelerator tier, payout to date</li>
  <li>SPIFFs and contests go live in a few clicks, not a week of plan-doc edits</li>
  <li>Disputes drop because reps and partners see the math, not just the output</li>
  <li>Payouts flow straight to Plum, our rewards engine, so anyone in 100+ countries can take it as cash, gift cards, or experiences</li>
</ul>

<p>If even two of those would help {{company_name}}, I would love 20 mins.</p>
```

---

## Step 3, Day 6, Peer Proof

**Subject:** `how 3 Indian SaaS sales orgs cut payout time by 95 percent`

```html
<p>Hey {{first_name}},</p>

<p>Three patterns we see across Indian SaaS teams that have moved their incentives onto Compass:</p>

<p><strong>1. Mid-market SaaS, 400 AEs:</strong> Commission processing dropped from 6 days to 4 hours. Disputes fell 80 percent in two quarters because every rep could see the calc themselves.</p>

<p><strong>2. B2B SaaS with 150 active partners:</strong> Partner SPIFFs and lead-reg bonuses moved off Sheets. Partners now see live dashboards. Channel manager time freed up by 12 hours a week. Partner satisfaction (measured) jumped 30 percent.</p>

<p><strong>3. Series B SaaS, 150 FTE:</strong> Replaced a Spiff.com pilot with Compass for 30 percent less ACV and got the gamification layer (leaderboards, badges, contests) built in for both inside reps and partners.</p>

<p>Worth pulling apart any of these for {{company_name}}? I can keep it to 20 minutes.</p>
```

---

## Step 4, Day 9, Direct CTA

**Subject:** `20 minutes on the {{company_name}} sales incentives stack`

```html
<p>{{first_name}},</p>

<p>I have written a few notes, so let me be direct.</p>

<p>If commissions, SPIFFs, partner payouts, or quota tracking at {{company_name}} are still living in Sheets, I would like 20 mins to:</p>

<ol>
  <li>Map your current plan structure on a whiteboard, inside, field, channel, all of it</li>
  <li>Show a sandbox built around your motion</li>
  <li>Share what 3 SaaS teams in your headcount band are doing</li>
</ol>

<p>If the timing is wrong, just say "later in 2026" and I will park this. No follow-ups.</p>

<p>Pick a slot here: [calendly link] or reply with two times that work.</p>
```

---

## Step 5, Day 11, Breakup

**Subject:** `closing the loop, {{first_name}}`

```html
<p>Hey {{first_name}},</p>

<p>Last note from me on this thread.</p>

<p>If sales incentives ever stop being a once-a-month firefight at {{company_name}}, Compass is here. One module inside Empuls for plans, dashboards, contests, and payouts, covering both internal reps and channel partners. Built for India SaaS sales teams.</p>

<p>I will check back in a quarter. Wishing the team a strong close.</p>
```

---

## Smartlead sequence config (single campaign, ready to POST to /campaigns/{id}/sequences)

```json
{
  "sequences": [
    {
      "seq_number": 1,
      "seq_delay_details": { "delay_in_days": 0 },
      "variant_distribution_type": "MANUALLY_EQUAL",
      "seq_variants": [
        { "subject": "{{first_name}}, how is {{company_name}} running sales incentives this quarter", "email_body": "<p>Hi {{first_name}},</p><p>Most Sales heads I speak to in Indian SaaS run their incentives, AE commissions, partner SPIFFs, contest payouts, and lead-reg bonuses, on a Sheet that one RevOps person owns. It eats 5 to 7 days every month.</p><p>The bigger cost is trust. Reps and partners shadow-track their own numbers, escalate disputes, and stop believing accelerators are real.</p><p>Compass, the sales incentives module of Empuls, replaces that sheet. Every AE and partner at {{company_name}} sees what they have earned in real time, every plan change goes live in a day, and Finance gets a clean audit trail. Payouts flow through Plum so rewards land in 100+ countries as cash, gift cards, or experiences. Pepsico, Hershey's, Capgemini, and Aditya Birla Capital run on it.</p><p>Worth a 20 min look for {{company_name}}? Happy to come prepared with how SaaS teams your size structure plans for both internal reps and channel partners.</p>", "variant_label": "A" },
        { "subject": "quick one on the {{company_name}} comp + SPIFF stack", "email_body": "<p>Hi {{first_name}},</p><p>Most Sales heads I speak to in Indian SaaS run their incentives, AE commissions, partner SPIFFs, contest payouts, and lead-reg bonuses, on a Sheet that one RevOps person owns. It eats 5 to 7 days every month.</p><p>The bigger cost is trust. Reps and partners shadow-track their own numbers, escalate disputes, and stop believing accelerators are real.</p><p>Compass, the sales incentives module of Empuls, replaces that sheet. Every AE and partner at {{company_name}} sees what they have earned in real time, every plan change goes live in a day, and Finance gets a clean audit trail. Payouts flow through Plum so rewards land in 100+ countries as cash, gift cards, or experiences. Pepsico, Hershey's, Capgemini, and Aditya Birla Capital run on it.</p><p>Worth a 20 min look for {{company_name}}? Happy to come prepared with how SaaS teams your size structure plans for both internal reps and channel partners.</p>", "variant_label": "B" },
        { "subject": "{{first_name}}, the spreadsheet behind your reps' and partners' payouts", "email_body": "<p>Hi {{first_name}},</p><p>Most Sales heads I speak to in Indian SaaS run their incentives, AE commissions, partner SPIFFs, contest payouts, and lead-reg bonuses, on a Sheet that one RevOps person owns. It eats 5 to 7 days every month.</p><p>The bigger cost is trust. Reps and partners shadow-track their own numbers, escalate disputes, and stop believing accelerators are real.</p><p>Compass, the sales incentives module of Empuls, replaces that sheet. Every AE and partner at {{company_name}} sees what they have earned in real time, every plan change goes live in a day, and Finance gets a clean audit trail. Payouts flow through Plum so rewards land in 100+ countries as cash, gift cards, or experiences. Pepsico, Hershey's, Capgemini, and Aditya Birla Capital run on it.</p><p>Worth a 20 min look for {{company_name}}? Happy to come prepared with how SaaS teams your size structure plans for both internal reps and channel partners.</p>", "variant_label": "C" }
      ]
    },
    {
      "seq_number": 2,
      "seq_delay_details": { "delay_in_days": 3 },
      "seq_variants": [
        { "subject": "Re: {{first_name}}, how is {{company_name}} running sales incentives this quarter", "email_body": "<p>{{first_name}}, bumping this.</p><p>To make it concrete, here is what month-end looks like for a 60-rep SaaS team plus 80 active partners after Compass:</p><ul><li>RevOps closes the comp + partner-payout run in under 2 hours, not 5 days</li><li>Every AE and partner has a personal dashboard: quota attained, deals counted, accelerator tier, payout to date</li><li>SPIFFs and contests go live in a few clicks, not a week of plan-doc edits</li><li>Disputes drop because reps and partners see the math, not just the output</li><li>Payouts flow straight to Plum, our rewards engine, so anyone in 100+ countries can take it as cash, gift cards, or experiences</li></ul><p>If even two of those would help {{company_name}}, I would love 20 mins.</p>", "variant_label": "A" }
      ]
    },
    {
      "seq_number": 3,
      "seq_delay_details": { "delay_in_days": 3 },
      "seq_variants": [
        { "subject": "how 3 Indian SaaS sales orgs cut payout time by 95 percent", "email_body": "<p>Hey {{first_name}},</p><p>Three patterns we see across Indian SaaS teams that have moved their incentives onto Compass:</p><p><strong>1. Mid-market SaaS, 400 AEs:</strong> Commission processing dropped from 6 days to 4 hours. Disputes fell 80 percent in two quarters because every rep could see the calc themselves.</p><p><strong>2. B2B SaaS with 150 active partners:</strong> Partner SPIFFs and lead-reg bonuses moved off Sheets. Partners now see live dashboards. Channel manager time freed up by 12 hours a week. Partner satisfaction (measured) jumped 30 percent.</p><p><strong>3. Series B SaaS, 150 FTE:</strong> Replaced a Spiff.com pilot with Compass for 30 percent less ACV and got the gamification layer (leaderboards, badges, contests) built in for both inside reps and partners.</p><p>Worth pulling apart any of these for {{company_name}}? I can keep it to 20 minutes.</p>", "variant_label": "A" }
      ]
    },
    {
      "seq_number": 4,
      "seq_delay_details": { "delay_in_days": 3 },
      "seq_variants": [
        { "subject": "20 minutes on the {{company_name}} sales incentives stack", "email_body": "<p>{{first_name}},</p><p>I have written a few notes, so let me be direct.</p><p>If commissions, SPIFFs, partner payouts, or quota tracking at {{company_name}} are still living in Sheets, I would like 20 mins to:</p><ol><li>Map your current plan structure on a whiteboard, inside, field, channel, all of it</li><li>Show a sandbox built around your motion</li><li>Share what 3 SaaS teams in your headcount band are doing</li></ol><p>If the timing is wrong, just say \"later in 2026\" and I will park this. No follow-ups.</p><p>Pick a slot here: [calendly link] or reply with two times that work.</p>", "variant_label": "A" }
      ]
    },
    {
      "seq_number": 5,
      "seq_delay_details": { "delay_in_days": 2 },
      "seq_variants": [
        { "subject": "closing the loop, {{first_name}}", "email_body": "<p>Hey {{first_name}},</p><p>Last note from me on this thread.</p><p>If sales incentives ever stop being a once-a-month firefight at {{company_name}}, Compass is here. One module inside Empuls for plans, dashboards, contests, and payouts, covering both internal reps and channel partners. Built for India SaaS sales teams.</p><p>I will check back in a quarter. Wishing the team a strong close.</p>", "variant_label": "A" }
      ]
    }
  ]
}
```

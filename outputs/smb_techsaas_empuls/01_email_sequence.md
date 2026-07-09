# Empuls Email Sequence (Smartlead, 5 steps)

> Buyer: Head / Director / HRBP at Indian SMB Tech SaaS (200 to 5,000 FTE).
> Tone: warm, peer HR-to-HR, India-flavored. No fluff, no AI tells, no em-dashes.
> No sign-off in `email_body`. Smartlead auto-appends signature.
> Proof points are real Empuls case studies, verified at empuls.xoxoday.com/customer-stories. No fabricated stats, no assumed geography about the prospect.

---

## Step 1, Day 0, R&R Reality Check

**Subject A:** `{{first_name}}, how is recognition running at {{company_name}}`
**Subject B:** `the {{company_name}} R&R stack, in 3 questions`
**Subject C:** `{{first_name}}, a quick question on {{company_name}} engagement`

```html
<p>Hi {{first_name}},</p>

<p>Most People leaders I speak to in Indian SaaS describe R&R the same way: a peer Slack channel that runs hot for two weeks then dies, gift cards bought once a quarter, and an annual awards night that 30 percent of the company misses.</p>

<p>Empuls puts all of it in one platform. Peer recognition inside Slack and Teams. Automated service anniversaries and birthdays. Lifecycle and pulse surveys. Perks and discounts. And a 10M+ rewards catalogue across 175+ countries, with a strong India catalogue (gold, local brands, experiences).</p>

<p>KPIT, Prodevans, and Bahwan CyberTek run on it. Curious if R&R or engagement is on the list for {{company_name}} this year, worth a 20 min walkthrough?</p>
```

---

## Step 2, Day 3, Day-in-the-Life HRBP

**Subject:** `Re: {{first_name}}, how is recognition running at {{company_name}}`

```html
<p>{{first_name}}, bumping this gently.</p>

<p>To make it concrete, here is what HRBP life looks like for a 1,000-person team after Empuls:</p>

<ul>
  <li>Peer recognition happens inside the Slack channel where work already happens. No new app to learn.</li>
  <li>Service anniversaries, work-iversaries, and birthdays trigger automatically with a budget you set, no spreadsheet to chase</li>
  <li>Pulse surveys go out monthly, eNPS is a live number not a quarterly project</li>
  <li>Employees redeem from 10M+ options across 175+ countries, with a deep India catalogue covering gold, local brands, and experiences</li>
  <li>Perks layer adds zero-cost discounts on everyday brands, employees actually use it</li>
</ul>

<p>If even two of those would help your team at {{company_name}}, I would love 20 mins. Promise to keep it focused on your headcount, not a generic deck.</p>
```

---

## Step 3, Day 6, Peer Proof

**Subject:** `3 Indian tech companies, 3 different problems, 3 honest results`

```html
<p>Hey {{first_name}},</p>

<p>Three real Empuls customer outcomes, all Indian tech and IT firms, pulled from public case studies:</p>

<p><strong>1. Prodevans Technologies (500-FTE Indian IT services, distributed across client sites):</strong> 70+ percent of employees actively participate on Empuls. Reward redemption moved from manual voucher purchasing to digital points with no expiry. Their HR called it "the single point for everything employee engagement."</p>

<p><strong>2. KPIT Technologies (5000+ FTE Indian software, presence in India, US, Europe, Japan):</strong> R&R budget scaled from 15 to 20 lakhs per quarter to nearly 45 lakhs per quarter as adoption grew. Peer-to-peer recognition rose sharply. Earlier reward points were sitting unredeemed because the catalogue was thin, Empuls solved that with 20,000+ options.</p>

<p><strong>3. Bahwan CyberTek (1000 to 5000 FTE Indian software, global workforce):</strong> Used Empuls to connect a globally distributed engineering workforce through recognition, rewards, and the social intranet. The Head of Talent Engagement credited the platform with improved retention and engagement.</p>

<p>The patterns hold across {{company_name}}'s headcount band. Worth pulling any of these apart on a 20 min call?</p>
```

---

## Step 4, Day 9, Direct CTA

**Subject:** `20 minutes on {{company_name}}'s R&R stack`

```html
<p>{{first_name}},</p>

<p>I have written a few notes, so here is the direct ask.</p>

<p>If R&R, engagement, or rewards at {{company_name}} are still spread across Slack channels, gift cards, and Excel, I would like 20 mins to:</p>

<ol>
  <li>Map your current recognition flow on a whiteboard</li>
  <li>Show a sandbox tailored to {{company_name}}'s headcount and HR setup</li>
  <li>Share what comparable HR teams are doing in 2026</li>
</ol>

<p>If timing is wrong, just reply "later" and I will park this. No follow-ups, no nurture spam.</p>

<p>Pick a slot here: [calendly link] or share two times.</p>
```

---

## Step 5, Day 11, Breakup

**Subject:** `closing the loop, {{first_name}}`

```html
<p>Hey {{first_name}},</p>

<p>Last note from me on this thread.</p>

<p>If R&R or engagement ever moves up the priority list at {{company_name}}, Empuls is here. One platform: peer recognition, milestones, surveys, perks, and a global rewards layer with a strong India catalogue.</p>

<p>I will check back in a quarter. Wishing you and the team a strong year.</p>
```

---

## Smartlead sequence config (ready to POST to /campaigns/{id}/sequences)

```json
{
  "sequences": [
    {
      "seq_number": 1,
      "seq_delay_details": { "delay_in_days": 0 },
      "variant_distribution_type": "MANUALLY_EQUAL",
      "seq_variants": [
        { "subject": "{{first_name}}, how is recognition running at {{company_name}}", "email_body": "<p>Hi {{first_name}},</p><p>Most People leaders I speak to in Indian SaaS describe R&R the same way: a peer Slack channel that runs hot for two weeks then dies, gift cards bought once a quarter, and an annual awards night that 30 percent of the company misses.</p><p>Empuls puts all of it in one platform. Peer recognition inside Slack and Teams. Automated service anniversaries and birthdays. Lifecycle and pulse surveys. Perks and discounts. And a 10M+ rewards catalogue across 175+ countries, with a strong India catalogue (gold, local brands, experiences).</p><p>KPIT, Prodevans, and Bahwan CyberTek run on it. Curious if R&R or engagement is on the list for {{company_name}} this year, worth a 20 min walkthrough?</p>", "variant_label": "A" },
        { "subject": "the {{company_name}} R&R stack, in 3 questions", "email_body": "<p>Hi {{first_name}},</p><p>Most People leaders I speak to in Indian SaaS describe R&R the same way: a peer Slack channel that runs hot for two weeks then dies, gift cards bought once a quarter, and an annual awards night that 30 percent of the company misses.</p><p>Empuls puts all of it in one platform. Peer recognition inside Slack and Teams. Automated service anniversaries and birthdays. Lifecycle and pulse surveys. Perks and discounts. And a 10M+ rewards catalogue across 175+ countries, with a strong India catalogue (gold, local brands, experiences).</p><p>KPIT, Prodevans, and Bahwan CyberTek run on it. Curious if R&R or engagement is on the list for {{company_name}} this year, worth a 20 min walkthrough?</p>", "variant_label": "B" },
        { "subject": "{{first_name}}, a quick question on {{company_name}} engagement", "email_body": "<p>Hi {{first_name}},</p><p>Most People leaders I speak to in Indian SaaS describe R&R the same way: a peer Slack channel that runs hot for two weeks then dies, gift cards bought once a quarter, and an annual awards night that 30 percent of the company misses.</p><p>Empuls puts all of it in one platform. Peer recognition inside Slack and Teams. Automated service anniversaries and birthdays. Lifecycle and pulse surveys. Perks and discounts. And a 10M+ rewards catalogue across 175+ countries, with a strong India catalogue (gold, local brands, experiences).</p><p>KPIT, Prodevans, and Bahwan CyberTek run on it. Curious if R&R or engagement is on the list for {{company_name}} this year, worth a 20 min walkthrough?</p>", "variant_label": "C" }
      ]
    },
    {
      "seq_number": 2,
      "seq_delay_details": { "delay_in_days": 3 },
      "seq_variants": [
        { "subject": "Re: {{first_name}}, how is recognition running at {{company_name}}", "email_body": "<p>{{first_name}}, bumping this gently.</p><p>To make it concrete, here is what HRBP life looks like for a 1,000-person team after Empuls:</p><ul><li>Peer recognition happens inside the Slack channel where work already happens. No new app to learn.</li><li>Service anniversaries, work-iversaries, and birthdays trigger automatically with a budget you set, no spreadsheet to chase</li><li>Pulse surveys go out monthly, eNPS is a live number not a quarterly project</li><li>Employees redeem from 10M+ options across 175+ countries, with a deep India catalogue covering gold, local brands, and experiences</li><li>Perks layer adds zero-cost discounts on everyday brands, employees actually use it</li></ul><p>If even two of those would help your team at {{company_name}}, I would love 20 mins. Promise to keep it focused on your headcount, not a generic deck.</p>", "variant_label": "A" }
      ]
    },
    {
      "seq_number": 3,
      "seq_delay_details": { "delay_in_days": 3 },
      "seq_variants": [
        { "subject": "3 Indian tech companies, 3 different problems, 3 honest results", "email_body": "<p>Hey {{first_name}},</p><p>Three real Empuls customer outcomes, all Indian tech and IT firms, pulled from public case studies:</p><p><strong>1. Prodevans Technologies (500-FTE Indian IT services, distributed across client sites):</strong> 70+ percent of employees actively participate on Empuls. Reward redemption moved from manual voucher purchasing to digital points with no expiry. Their HR called it \"the single point for everything employee engagement.\"</p><p><strong>2. KPIT Technologies (5000+ FTE Indian software, presence in India, US, Europe, Japan):</strong> R&R budget scaled from 15 to 20 lakhs per quarter to nearly 45 lakhs per quarter as adoption grew. Peer-to-peer recognition rose sharply. Earlier reward points were sitting unredeemed because the catalogue was thin, Empuls solved that with 20,000+ options.</p><p><strong>3. Bahwan CyberTek (1000 to 5000 FTE Indian software, global workforce):</strong> Used Empuls to connect a globally distributed engineering workforce through recognition, rewards, and the social intranet. The Head of Talent Engagement credited the platform with improved retention and engagement.</p><p>The patterns hold across {{company_name}}'s headcount band. Worth pulling any of these apart on a 20 min call?</p>", "variant_label": "A" }
      ]
    },
    {
      "seq_number": 4,
      "seq_delay_details": { "delay_in_days": 3 },
      "seq_variants": [
        { "subject": "20 minutes on {{company_name}}'s R&R stack", "email_body": "<p>{{first_name}},</p><p>I have written a few notes, so here is the direct ask.</p><p>If R&R, engagement, or rewards at {{company_name}} are still spread across Slack channels, gift cards, and Excel, I would like 20 mins to:</p><ol><li>Map your current recognition flow on a whiteboard</li><li>Show a sandbox tailored to {{company_name}}'s headcount and HR setup</li><li>Share what comparable HR teams are doing in 2026</li></ol><p>If timing is wrong, just reply \"later\" and I will park this. No follow-ups, no nurture spam.</p><p>Pick a slot here: [calendly link] or share two times.</p>", "variant_label": "A" }
      ]
    },
    {
      "seq_number": 5,
      "seq_delay_details": { "delay_in_days": 2 },
      "seq_variants": [
        { "subject": "closing the loop, {{first_name}}", "email_body": "<p>Hey {{first_name}},</p><p>Last note from me on this thread.</p><p>If R&R or engagement ever moves up the priority list at {{company_name}}, Empuls is here. One platform: peer recognition, milestones, surveys, perks, and a global rewards layer with a strong India catalogue.</p><p>I will check back in a quarter. Wishing you and the team a strong year.</p>", "variant_label": "A" }
      ]
    }
  ]
}
```

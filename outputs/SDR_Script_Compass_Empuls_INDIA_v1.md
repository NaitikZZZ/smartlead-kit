# SDR Calling Script, Compass + Empuls, India SMB Tech SaaS
**Owner:** Naitik
**Last updated:** 2026-05-06
**Use for:** Phone calls on D5 and D8 of the multi-channel sequence below. Aligned with the live email and LinkedIn copy.

---

## 1. Why this script exists

Two campaigns are running in parallel against Indian SMB Tech SaaS accounts (200 to 5,000 FTE):

| Campaign | Smartlead ID | HeyReach ID | Buyer | Leads | Live opens / sends |
|---|---|---|---|---|---|
| Compass (Sales Incentives module of Empuls) | 3238358 | 414235 | VP / Head / Director of Sales | 25 | 58 / 75 sends across step 1 to 3 |
| Empuls (R&R, engagement, rewards) | 3238359 | 414202 | CHRO / HR Head / HRBP | 24 | 52 / 72 sends across step 1 to 3 |

**What the data is telling us:** ~75 percent open rate, zero replies. Buyers have read the framing, no one has objected, no one has said yes. The phone is the next forcing function. SDR job is to convert "read but silent" into a 20 minute discovery.

**Cadence the lead has already experienced before D5 dial:**

- D1 Email 1 (problem hook), D1 LinkedIn profile visit
- D2 LinkedIn engagement
- D3 Email 2 (day-in-the-life)
- D4 LinkedIn connection request

So when you dial, the lead has seen 2 emails and a connection request from Naitik. Reference that. You are not cold, you are warm.

---

## 2. Pre-call checklist (90 seconds before dialing)

1. Open the lead row in HubSpot, confirm `campaign_id` (3238358 = Compass / Sales, 3238359 = Empuls / HR).
2. Note the `segment` column. For Compass, watch for 4 channel-flagged leads:
   - Vipul Mathur, Spectranet, Sales Head Business WiFi
   - Rakesh Kumar, Atlys, Head of Sales B2B
   - Tejas Shah, Emudhra, Sales Partner
   - Rakesh Banga, Atlys, Head of B2B Channel Sales
3. Check the `last_email_subject` field. Drop that exact phrase in the opener.
4. Glance at LinkedIn for one specific signal (a recent post, a hire, a product launch) you can name in the first 30 seconds.
5. Have the calendar tab open before the dial connects.

---

## 3. The universal opener (15 seconds, both campaigns)

> Hi {{first_name}}, this is [SDR name] calling from Xoxoday. I know I am calling cold, can I borrow 30 seconds to tell you why, and you can decide if it is worth a real conversation?

[Pause. Wait for "yes," "go ahead," silence, or pushback.]

**Why this works:** You are giving them control. Indian sales and HR leaders accept a 30 second ask far more than a "got a minute?"

**If they say "what is this about":**

> A quick note I sent you last week landed on your inbox, subject line was around {{last_email_subject}}. Worth 30 seconds to give you the why?

---

## 4. The pitch fork (choose one based on `campaign_id` + `segment`)

### 4A. Compass, Direct Sales segment (21 of 25 leads)

> Most VP Sales we work with at SaaS firms in your headcount band still run commissions on Sheets. RevOps loses 5 to 7 days every month, reps shadow-track their own numbers, rolling out a new SPIFF takes a week. We built Compass, the sales incentives module inside Empuls, to fix that end to end. Pepsico, Capgemini, and Aditya Birla Capital are on it.

Then ask both:

1. Is comp at {{company_name}} on a tool today, or is it still in Sheets?
2. Is fixing the comp process on the priority list for FY26?

### 4B. Compass, Channel segment (4 leads: Spectranet, Atlys x2, Emudhra)

> Most channel sales leaders we work with at SaaS firms your size are running partner SPIFFs and override commissions on a Sheet shared with 50 to 200 partners. Partners cannot see their own attainment, escalations pile up on the channel manager, and contest payouts take weeks. Compass, the sales incentives module inside Empuls, runs the plan logic. Payouts flow through Plum so partners in India and abroad can take it as cash, gift cards, or experiences in their own country.

Then ask both:

1. How many active partners is {{company_name}} running incentives for today?
2. Where does most of the friction sit, plan rollout, payout, or visibility for partners?

### 4C. Empuls, HR segment (all 24 leads)

> Most People leaders we work with at SaaS firms your size are running R&R across four places: Slack shoutouts, ad-hoc gift cards once a quarter, an Excel sheet for service anniversaries, and one annual awards night that 30 percent of the company misses. We built Empuls to pull all of that into one platform that lives inside Slack or Teams. KPIT, Prodevans, and Bahwan CyberTek run on it.

Then ask both:

1. Is recognition at {{company_name}} on a single tool today, or stitched together?
2. Is engagement or attrition something the team is actively solving for in 2026?

---

## 5. Read the room, then route

Pick the path the prospect signals. Do not stack pitches.

### Path A, "yes, this is a problem for us"

> Got it. Two ways forward. I can either send a 90 second loom that walks you through how a {{company_size_band}} team uses it, or we book 20 minutes later this week and I show you a sandbox built around your motion. Which is easier?

If they take the meeting: jump to Section 7 (booking).
If they take the loom: confirm email, send within the hour, log `LOOM_SENT_NURTURE`.

### Path B, "we already have a tool"

Find out which one, then use the angle below.

| If they have | Open with |
|---|---|
| Spiff, Everstage, Xactly, Performio (Compass) | Most teams that switch to us from those want India-specific support, faster plan rollouts, or the integrated rewards engine on payouts. If any of those are open issues, worth 20 mins. If everything is humming, I will get out of your way. |
| In-house tool or Sheets calling itself a tool (Compass) | Fair. Quick check, what happens when you need to roll out a new contest mid-quarter, how long does that take today? |
| Vantage Circle, Workhuman, Reward Gateway (Empuls) | Both are good. Where we win in India is the breadth of the catalogue (gold, local brands, experiences) plus surveys built into the same platform, not a separate Culture Amp. Worth 20 mins to compare. |
| Plumm, internal Slack bot (Empuls) | Got it. Most teams move to Empuls when they want milestones, surveys, perks, and global rewards in one place instead of three tools. Open to 20 mins to map yours? |

Always end with: **"And when does that contract come up for renewal?"** Capture the renewal date in HubSpot, that is the trigger date for re-engagement.

### Path C, "send me an email"

> Done, I will keep it tight. One question first so the email is actually useful for you: [pick one based on campaign].
>
> Compass: How many AEs are you running comp for right now, and is comp the bottleneck or is plan design the bottleneck?
> Empuls: How many FTE are you running R&R for, and is the bigger gap recognition itself or the rewards catalogue?

Send the email within 15 minutes, reference one thing from the call, attach the relevant 1-pager. Log `EMAIL_REQUESTED_FOLLOW_UP`.

### Path D, "not now"

> Fair. Quick check, is "not now" 1 quarter, 2 quarters, or all of 2026? I will note it and only come back when it makes sense.

Capture the timeline. Log `NOT_NOW_QX_2026` or `NOT_NOW_2027`.

### Path E, "wrong person"

> No problem. Who at {{company_name}} owns this in 2026? Happy to drop your name when I reach out, or you can intro me, whichever is easier.

Capture the name and email. Log `WRONG_PERSON_REROUTED`.

### Path F, hard "no, remove me"

Acknowledge, do not push back.

> Got it, I will mark you off the list. Apologies for the noise.

Log `DNC`. Mark in HubSpot, suppress across email and LinkedIn via the unified suppression list.

---

## 6. D8 voicemail (30 seconds, only if D5 went unanswered)

**For Compass (3238358):**

> Hi {{first_name}}, [SDR name] from Xoxoday again. I sent you a couple of notes last week about Compass, our sales commissions and partner payouts platform. We help SaaS sales orgs in your headcount band move comp off Sheets, cut disputes by 80 percent, and roll out SPIFFs in days, not weeks. If sales comp is on your radar this quarter, I would love 20 minutes. I will drop one final email and then back off. All the best for the quarter.

**For Empuls (3238359):**

> Hi {{first_name}}, [SDR name] from Xoxoday again. I sent you a couple of notes last week about Empuls, our employee engagement and rewards platform. We help SaaS HR teams in your headcount band consolidate R&R into one platform that lives inside Slack, automate milestones, and unlock a global rewards catalogue with a strong India side. If engagement is on your radar this year, I would love 20 minutes. Final email coming, then I will back off. All the best.

**If they pick up on the second attempt:**

> Hi {{first_name}}, [SDR name] from Xoxoday. I will not take more than a minute. I called and emailed earlier about [Compass / Empuls]. The reason I called twice is I genuinely think the platform fits {{company_name}}'s setup. Two paths: I can send a 90 second loom that walks through it, or we book 20 minutes later this week. Which is easier?

---

## 7. Booking the meeting (the only outcome that matters)

> Great, 20 minutes. I will send a Calendly with three slots this week. If none work, just reply with two times. Confirming your email is {{email}}, correct?

Then within 15 minutes:

1. Send the calendar invite with a tight agenda (3 lines, no deck attached).
2. Tag the lead in HubSpot as `MEETING_BOOKED`.
3. Drop a note to Naitik on the deal record with the 2 discovery questions you got answers to.
4. Pause Smartlead and HeyReach for that lead via the suppression webhook.

---

## 8. Objection handlers (one-liners, full bench)

| Objection | Response |
|---|---|
| "We use Excel and it works." | Most teams say that until reps stop trusting it. Curious, do reps see their attainment in real time today, or do they ping RevOps every week? |
| "Spiff or Everstage already pitched us." | Both are good products. Where we win is India support, faster plan changes, and the built-in rewards engine on payouts. Worth 20 mins to compare on those three. |
| "Compass is just for internal reps, our pain is partners." | Same module runs both. Plan logic for overrides, SPIFFs, lead-reg, tier accelerators applies to partners exactly the same way. Plum handles partner payouts in 100+ countries. Worth 20 mins to map your partner motion. |
| "We are looking at a partner-loyalty tool like Loyalife." | Different problem. Loyalife is for long-term, points-based partner programs. If you want quick-cycle SPIFFs and quarterly contests, Compass is the right module. Both can sit inside one Xoxoday account. |
| "Slack shoutouts work fine for us." | Most teams say that until eNPS dips. Quick check, do you have a single dashboard that shows who has been recognized this month and who has not? |
| "Vantage Circle or Workhuman is fine." | Both solid. Where we win in India is the catalogue depth (gold, local brands, experiences) plus surveys built in instead of a separate Culture Amp. Worth 20 mins to compare. |
| "Send a deck." | I can do better, can I send a 90 second loom of the dashboard? Decks die in a folder. |
| "Budget is locked." | Understood. Most pilots we run are paid out of the existing R&R or RevOps efficiency line, not new budget. Worth 15 mins to map that? |
| "Talk to RevOps / CHRO, not me." | Happy to. Can you intro me, or is it better if I drop your name? |
| "We are too small." | We have customers from 150 FTE. Often the smaller you are, the more leverage one consolidated platform gives you. |
| "Email me, I will get back." | Sure, sending now. So I send the right thing, what is the one thing about the current setup that bothers you most? |

---

## 9. Disposition codes (log every call in HubSpot)

| Code | Meaning | Next action |
|---|---|---|
| `MEETING_BOOKED` | 20 min discovery on the calendar | Pause Smartlead + HeyReach for this lead, hand to Naitik |
| `LOOM_SENT_NURTURE` | Lead asked for the loom in lieu of a meeting | Send within 1 hour, follow up D+3 |
| `EMAIL_REQUESTED_FOLLOW_UP` | Lead asked to "send an email" | Send within 15 min, follow up D+3 |
| `INTERESTED_NURTURE` | Warm but timing off, no specific date | Re-engage in 30 days |
| `NOT_NOW_Q3_2026` / `NOT_NOW_Q4_2026` / `NOT_NOW_2027` | Future timing | Auto-task on the future date |
| `WRONG_PERSON_REROUTED` | Captured the right contact | Add the new contact, restart the sequence on them |
| `COMPETITOR_INSTALLED` | Has a tool, capture vendor + renewal date | Re-engage 90 days before renewal |
| `NO_ANSWER_LEFT_VOICEMAIL` | D8 voicemail dropped | Let the email sequence finish, no third dial |
| `NO_ANSWER_NO_VOICEMAIL` | D5 no-answer, no voicemail dropped | Try D8 with voicemail |
| `DNC` | Asked to stop | Suppress across all channels in HubSpot |

---

## 10. Daily call plan for the SDR

- **Dial windows (Asia/Kolkata):** 10:00 to 12:30 and 15:00 to 17:30. Avoid 12:30 to 14:30 lunch and the 17:45 traffic-out window.
- **Daily volume:** 10 to 12 dials per SDR, half Compass and half Empuls. Quality over quantity, every call gets a logged disposition.
- **Two attempts max per lead:** D5 first dial, D8 second dial with voicemail. After that, the breakup email (Step 5) carries the close.
- **Hot routing:** any "yes, book it" goes to Naitik's Calendly the same day. Do not let a warm lead cool off overnight.

---

## 11. Notes for the SDR (read once, internalize)

- The lead has read 2 emails and seen a LinkedIn connection request before you dial. You are not cold, anchor on that.
- The email subject they likely opened was either "{{first_name}}, how is {{company_name}} running sales incentives this quarter" (Compass) or "{{first_name}}, how is recognition running at {{company_name}}" (Empuls). Use it.
- Compass = Sales Incentives module of Empuls. Do not pitch it as a separate platform. The "Compass" name has brand equity, keep it visible.
- Empuls customer references that work in India: KPIT, Prodevans, Bahwan CyberTek. Pepsico/Capgemini/Aditya Birla Capital for Compass.
- No em-dashes or en-dashes when you type the follow-up email. Use commas or hyphens.
- If the prospect goes off-script and asks pricing, say: "It depends on headcount and modules. For your band it lands in [X to Y INR per employee per year]. The 20 minute call is where we scope it." Do not fudge the number, hand to Naitik if you do not know it.
- Goal: 5 to 8 meetings booked from these 49 leads combined, into Naitik's pipeline.

---

## 12. Files referenced

- Compass campaign brief: `outputs/smb_techsaas_compass/00_brief.md`
- Compass email sequence (live): `outputs/smb_techsaas_compass/01_email_sequence.md`
- Compass LinkedIn copy (live): `outputs/smb_techsaas_compass/02_linkedin_sequence.md`
- Empuls campaign brief: `outputs/smb_techsaas_empuls/00_brief.md`
- Empuls email sequence (live): `outputs/smb_techsaas_empuls/01_email_sequence.md`
- Empuls LinkedIn copy (live): `outputs/smb_techsaas_empuls/02_linkedin_sequence.md`

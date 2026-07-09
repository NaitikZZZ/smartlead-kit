# Compass LinkedIn Sequence (HeyReach, single campaign)

> Buyer: VP / Head / Director of Sales at Indian SMB Tech SaaS
> Sender: Naitik (LinkedIn profile)
> No sign-off in any DM body. The body ends on the last content line, same rule as Smartlead emails.
> **Single HeyReach campaign for all 26 leads.** The DM speaks to both AE-comp and partner-payout pain in one frame, mirroring the email approach. Channel-specific framing only happens on SDR calls.

---

## D1, Profile visit

No copy. Sender visits the prospect's profile so the notification fires alongside Email 1. HeyReach > "View profile" action.

---

## D2, Engagement on a recent post

Manual or HeyReach auto-like on the prospect's most recent post. If the post is substantive (a hire, a product launch, a thought piece), drop a 1-line genuine comment. No pitch.

Example:
> Strong point on inside-vs-field handover, {{first_name}}. The compensation side of that handover is where we see most leakage too.

---

## D4, Connection request, no note

Plain connection invite. Mid-market Indian SaaS leaders accept these at higher rates than noted invites.

---

## D7, First DM (if connected) or InMail (if not)

**InMail subject:** `quick question on {{company_name}} sales incentives`

```
Hi {{first_name}},

Caught your profile while mapping Indian SaaS sales orgs in the 200 to 1,500 FTE band.

Most Sales heads here run their incentives, AE commissions, partner SPIFFs, and contest payouts, on Sheets that one RevOps person owns. Reps and partners shadow-track, plan changes take ages.

Compass, the sales incentives module inside Empuls, solves that end to end: real-time dashboards for reps and partners, gamified leaderboards, automated payout via Plum (100+ countries). Pepsico, Capgemini, and Aditya Birla run on it.

Worth a 20 min walkthrough for {{company_name}}, or is comp not on the radar this quarter?
```

---

## D10, Value-add DM

Send only if D7 got opened or any positive signal. Pure asset share, no ask.

```
{{first_name}}, sharing this in case it is useful.

Short read on how SaaS sales orgs in the 100 to 500 rep band are restructuring their 2026 comp plans (accelerators, decelerators, SPIFF cadence): [link to blog or 1-pager].

Not a pitch. If anything in there sparks a conversation, you know where to find me.
```

---

## D13 (post-Smartlead breakup), Soft close

Optional. Only if the email sequence ended with no reply but the connection was accepted.

```
{{first_name}}, last one from my side.

If sales incentives move up the priority list at {{company_name}} later in 2026, Compass is an easy platform to pilot for an Indian SaaS sales team. Happy to ping you when we ship the next India-specific feature.

All the best for the quarter.
```

---

## HeyReach campaign config notes

- **Campaign name:** `Compass_SMBTechSaaS_26leads`
- **Campaign type:** Multi-touch with connection request + 2 DMs
- **Daily limits:** 20 connection invites per sender per day, 50 messages per sender per day
- **Skip rule:** If lead replies on email at any step, pause LinkedIn touches via HeyReach webhook from Smartlead
- **Personalization tokens used:** `{{first_name}}`, `{{company_name}}`
- **Sender:** Naitik's LinkedIn profile
- **Channel handling:** The 4 channel leads (Atlys x2, Spectranet, Emudhra) get the same DM as the rest. Channel-specific opener happens only on SDR call (D5).

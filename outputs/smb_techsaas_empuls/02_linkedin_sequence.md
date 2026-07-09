# Empuls LinkedIn Sequence (HeyReach)

> Buyer: Head / Director / HRBP / VP HR at Indian SMB Tech SaaS
> Sender: Naitik (LinkedIn profile)
> No sign-off in any DM body. The body ends on the last content line, same rule as Smartlead emails.

---

## D1, Profile visit

No copy. Sender visits the prospect's profile so the notification fires alongside Email 1.

---

## D2, Engagement on a recent post

Manual or auto-like on the prospect's most recent post. If the post is substantive (a hire, a culture initiative, a thought piece on engagement), drop a 1-line genuine comment. No pitch.

Example:
> Strong take on the manager-as-coach piece, {{first_name}}. We see the same thing in mid-market SaaS, recognition has to live where work happens, not in a separate portal.

---

## D4, Connection request, no note

Plain connection invite. HR leaders accept these at 35%+ rates when sender bio mentions Xoxoday or a relevant HR-tech brand.

---

## D7, First DM (if connected) or InMail (if not)

**Subject (InMail only):** `quick question on {{company_name}} R&R`

```
Hi {{first_name}},

Caught your profile while mapping HR leaders at Indian SaaS firms in the 200 to 5,000 FTE band.

Most People teams I speak to are running R&R across 4 places: Slack shoutouts, ad-hoc gift cards, an annual awards night, and Excel for service anniversaries.

Empuls pulls all of it into one platform. Peer recognition inside Slack and Teams, automated milestones, surveys, perks, and a 10M+ rewards catalogue across 175+ countries with a strong India catalogue. KPIT, Prodevans, and Bahwan CyberTek run on it.

Worth a 20 min walkthrough for {{company_name}}, or is engagement not on the list this year?
```

---

## D10, Value-add DM

Send only if D7 got opened or any positive signal. Pure asset share, no ask.

```
{{first_name}}, sharing this in case it is useful.

A short read on what 1,000+ Indian SaaS HR leaders said about their 2026 R&R priorities (top 3: peer recognition automation, manager enablement, and global rewards): [link to report or 1-pager].

Not a pitch. If anything in there sparks a conversation, you know where to find me.
```

---

## D13 (post-Smartlead breakup), Soft close

Optional. Only if the email sequence ended with no reply but the connection was accepted.

```
{{first_name}}, last one from my side.

If engagement or R&R becomes a priority later in 2026, Empuls is an easy platform to pilot for an Indian SaaS HR team. Happy to ping you when we ship the next India-focused feature.

All the best for the year.
```

---

## HeyReach campaign config notes

- **Campaign type:** Multi-touch with connection request + 2 DMs
- **Daily limits:** 20 connection invites per sender per day, 50 messages per sender per day
- **Skip rule:** If lead replies on email at any step, pause LinkedIn touches via HeyReach webhook from Smartlead
- **Personalization tokens used:** `{{first_name}}`, `{{company_name}}`
- **Sender:** Naitik's LinkedIn profile. If a female sender is added later, consider routing HRBP-titled leads to her, HR personas reply at higher rates to female senders in India.
- **Single campaign:** all 45 leads go into one HeyReach campaign (`Empuls_HR_45leads`), no segment split needed.

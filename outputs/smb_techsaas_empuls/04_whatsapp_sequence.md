# Empuls WhatsApp Sequence (parked, activate later)

> Activate only when:
> 1. WhatsApp Business API account is opt-in compliant for cold outbound to Indian numbers
> 2. Templates are approved by Meta (utility or marketing category)
> 3. Mobile numbers in `prospects.csv` are validated by Apollo or NumVerify
> 4. Naitik signs off on opt-out language

Until then this layer stays off. Once live, run as overlay on email + LinkedIn cadence.

---

## D6, Light nudge (post Email 2)

```
Hi {{first_name}}, this is Naitik from Xoxoday. Sent you a couple of notes about Empuls, our R&R + engagement platform that consolidates recognition, milestones, surveys, and rewards into Slack or Teams. Worth 20 mins to see if it fits {{company_name}}? Reply STOP to opt out.
```

Meta template category: marketing. Submit for approval as `empuls_intro_in_v1`.

---

## D11, Closer (post breakup email)

```
{{first_name}}, last note. Empuls helps SaaS HR teams cut attrition and lift eNPS by consolidating R&R into one platform with a strong India catalogue. If now is not right, I will park this for next quarter. Reply YES for a 20 min walkthrough, STOP to remove. Thanks.
```

Meta template category: marketing. Submit as `empuls_closer_in_v1`.

---

## Compliance notes

- Only message numbers where mobile is verified (Apollo "Mobile Phone" column populated and country = IN)
- Honor STOP keyword instantly, push to global blocklist (Smartlead + HubSpot `do_not_contact = true`)
- Do not send between 9pm IST and 9am IST
- Cap at 1 inbound + 1 outbound per lead per campaign (2 messages total)
- Track opt-outs in `outputs/smb_techsaas_empuls/whatsapp_optouts.csv`

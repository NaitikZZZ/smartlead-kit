# Compass WhatsApp Sequence (parked, activate later)

> Activate only when:
> 1. WhatsApp Business API account is opt-in compliant for cold outbound to Indian numbers
> 2. Templates are approved by Meta (utility or marketing category)
> 3. Mobile numbers in `prospects.csv` are validated by Apollo or NumVerify
> 4. Naitik signs off on opt-out language

Until then this layer stays off. Once live, run as overlay on the email + LinkedIn cadence, not standalone.

---

## D6, Light nudge (utility template, post Email 2)

```
Hi {{first_name}}, this is Naitik from Xoxoday. Sent you a couple of notes about Compass, our sales commission platform that replaces the comp Sheet for SaaS sales teams. Worth 20 mins to see if it fits {{company_name}}? Reply STOP to opt out.
```

Meta template category: marketing. Submit for approval as `compass_intro_in_v1`.

---

## D11, Closer (post breakup email)

```
{{first_name}}, last note. Compass cuts comp processing time by 95 percent and disputes by 80 percent for SaaS sales teams in your headcount band. If now is not right, I will park this for next quarter. Reply YES if you want a 20 min walkthrough, STOP to remove. Thanks.
```

Meta template category: marketing. Submit as `compass_closer_in_v1`.

---

## Compliance notes

- Only message numbers where mobile is verified (Apollo "Mobile Phone" column populated and country = IN)
- Honor STOP keyword instantly, push to global blocklist (`mcp__smartlead__smartlead_add_lead_to_global_blocklist` for email; mirror to HubSpot `do_not_contact = true`)
- Do not send between 9pm IST and 9am IST
- Cap at 1 inbound + 1 outbound per lead per campaign (2 messages total)
- Track opt-outs in `outputs/smb_techsaas_compass/whatsapp_optouts.csv`

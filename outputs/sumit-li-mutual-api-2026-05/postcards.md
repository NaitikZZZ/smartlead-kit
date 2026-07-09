# Sumit Founder-Led Postcards (Add-on to Sumit LI Mutual Connects Campaign)

Premium physical touch from Sumit personally to top accounts inside his LinkedIn mutual list. **This is not a sales touch.** No pitch, no product mention, no proof points. Just a real card from one connection to another, acknowledging that they have been LinkedIn-connected for a while and have never actually spoken.

Cadence: postcard lands Day -3, Avipsa's LinkedIn DM Day -2, Email 1 Day 0, then the rest of the sequence carries the sales conversation.

---

## 1. Layout spec (matches the Flipkart CHRO Confex postcard style)

Card size: 6 x 4 inches (standard postcard) or A6.

```
+--------------------------------------------------+
|  {{COMPANY_NAME}}                XOXODAY  x  {{LOGO}}  |
|  (large handwritten)                             |
|                                                  |
|  {{MAIN MESSAGE, 2 to 3 handwritten lines}}      |
|                                                  |
|                                                  |
|  +----------------------------------+   +----+   |
|  | [photo]  Best,                   |   |QR  |   |
|  |          Sumit / Founder @       |   |code|   |
|  |          XOXODAY                 |   |    |   |
|  +----------------------------------+   +----+   |
+--------------------------------------------------+
```

Font: handwritten, **Caveat**, **Patrick Hand**, or **Kalam** from Google Fonts. Same casual feel as the Flipkart example.

Accent band: warm orange behind the signature block, same as the example.

---

## 2. Copy (one card, all 378 leads)

The copy is identical across panel, platform, and partner segments. The whole point is relational, not pitched, so segment-specific lines would dilute the feel.

### Primary copy (recommended)

> Top: **{{company_name}}**
>
> Message:
>
> Hi {{first_name}}, we have been connected on LinkedIn for a while but never actually spoken.
> Figured a real note beats another DM.
> Would love a proper chat whenever it suits.
>
> Signature: **Best, Sumit / Founder @ XOXODAY**

### Alternate copy (if you want a slightly warmer variant)

> Top: **{{company_name}}**
>
> Message:
>
> Hi {{first_name}}, we have been LinkedIn-connected a while now.
> Long overdue an actual conversation.
> Let me know if you have a window sometime.
>
> Signature: **Best, Sumit / Founder @ XOXODAY**

Both versions:
- Reference the existing connection without making it transactional.
- No product mention, no proof points, no formal CTA.
- Three short handwritten lines, the format that fits on a 6x4 card.
- Sound like Sumit, not a sales rep writing on his behalf.

---

## 3. Assets needed before print

| Asset | Format | Status |
|---|---|---|
| Sumit's headshot | Square PNG, 500x500 px, professional | NEEDED |
| Xoxoday logo | SVG or transparent PNG | NEEDED |
| Prospect company logos | One per account, 200x200 px | NEEDED |
| QR code target URL | Sumit's LinkedIn profile (recommended) or Calendly | NEEDED |
| Handwritten font | Caveat, Google Fonts, free | Ready |
| Orange accent color | Suggest #F5A742 to match example | Ready |

**QR target recommendation.** For a relational card, Sumit's **LinkedIn profile** is the most natural target. The card says "we are connected, let's talk" and the QR makes that one tap easy. A Calendly link feels too transactional for this touch.

**Logo sourcing.** Clearbit Logo API (`https://logo.clearbit.com/{domain}`) covers most of the 378 companies automatically. For the top 50 priority list, manual sourcing keeps print quality higher.

---

## 4. Production options

| Option | Cost per piece | Speed | Notes |
|---|---|---|---|
| Reachdesk or SendOso | $4 to $8 incl. postage | 2 to 5 days | Personalized, address-aware. Integrates with HubSpot. |
| Local printer + manual mail | $1 to $2 + postage | Slow | Cheapest, admin-heavy. |
| Digital postcard only (image attached to Email 1) | $0 | Instant | Skips physical, lower wow factor. |

Recommendation: send physical postcards to a top 50 to 75 C-suite cut, embed the digital postcard image in Email 1 for the rest.

---

## 5. Top 50 recipient cut

Pull from all three segment CSVs, filter to:
- Job title contains: CEO, Founder, CTO, COO, CRO, CMO, CPO, Chief, President, EVP, SVP
- Status: not "4 InMail Sent" (already moved deeper)
- Priority weighting: Segment 1 panel firms first (highest API fit), then Segment 2 platforms.

Once Naitik confirms the cut, I can generate `postcard_top50.csv` with mailing-address columns reserved. Office addresses are not in the source data, so an Apollo or Clay enrichment pass is needed.

---

## 6. Cadence with postcard added

| Day | Touch | Channel | Sender |
|---|---|---|---|
| -3 | Postcard arrives | Physical mail | Sumit |
| -2 | LinkedIn DM | LinkedIn | Avipsa |
| 0 | Email 1 | Email | Avipsa |
| 3 | Email 2 | Email | Avipsa |
| 6 | Email 3 | Email | Avipsa |
| 9 | Email 4 | Email | Avipsa |
| 11 | Email 5 (breakup) | Email | Avipsa |

The postcard primes warmth at the relationship level. The email sequence (already locked in REVIEW.pdf) carries the actual sales conversation.

---

## 7. Open decisions

1. **Primary vs alternate copy.** Pick one of the two variants above.
2. **QR target.** Sumit's LinkedIn (recommended) or his Calendly.
3. **Top 50 cut.** Confirm the title and segment-weighting criteria above.
4. **Address enrichment.** Approve an Apollo or Clay pass for office addresses (extra credit cost).
5. **Print partner.** Reachdesk, SendOso, or local printer.

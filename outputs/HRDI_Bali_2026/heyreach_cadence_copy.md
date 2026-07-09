# HeyReach cadence copy - HRDI Bali Post Event Thank You

**List:** P0_EVNTS_KSA_IDN_PSTEVNT_Imelda_05Apr2026 (HeyReach list ID `652585`)
**Sender:** Imelda Walla (HeyReach LinkedIn account ID `67762`)
**Leads loaded:** 23 of 29 (6 missing LinkedIn URLs, see `heyreach_missing_linkedin.csv`)

Configure the cadence steps in the HeyReach UI. This file holds the copy.

---

## Recommended cadence (simple, single-touch thank you)

Per the brief: keep it simple, separate sequences will go out for pinpointed follow-ups.

| Day | Step | Action |
|-----|------|--------|
| D1 | Send Connection Request | With note (see below) |
| D3 | DM if connected | Optional warm follow-up (use longer DM body) |

Set the campaign to **skip if already connected** so warm contacts go straight to DM.

---

## Step 1: Connection request note (under 300 chars)

```
Hi {{first_name}}, was at HRDI Summit in Bali last week and wanted to drop a quick thanks for being in the room. The HR director conversations were the sharpest I have heard this year. Hope the trip home was easy.

Imelda
```

Character count: 282

---

## Step 2: DM (for already-connected leads, or after connection accepts)

```
Hi {{first_name}},

Was at HRDI Summit in Bali last week and wanted to drop a quick thanks for being there. The HR director room had more honest debate than most conferences I sit through.

Hope the trip back home was easy.

Imelda
```

---

## HeyReach UI checklist

1. Open list `P0_EVNTS_KSA_IDN_PSTEVNT_Imelda_05Apr2026`
2. Create new campaign linked to this list
3. Assign sender: Imelda Walla
4. Add Step 1 (Connection Request) with the note above
5. Add Step 2 (DM if connected) with the longer message above
6. Settings:
   - Working hours: 09:00 to 18:00 Asia/Jakarta
   - Working days: Mon-Fri
   - Skip if already connected: yes
   - Stop on reply: yes
   - Daily limit per sender: 20 connection requests, 50 messages (LinkedIn caps)
7. Manually look up the 6 missing LinkedIn URLs and add to the list before launching
8. Review and start

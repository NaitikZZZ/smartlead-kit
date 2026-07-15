# Smartlead <-> HeyReach pause sync

Cloudflare Worker that pauses a lead on one platform when they reply on the other.

## How it works

- Smartlead fires `EMAIL_REPLY` -> worker looks up the paired HeyReach campaign and
  pauses that lead there by email.
- HeyReach fires `MESSAGE_REPLY_RECEIVED` / `INMAIL_REPLY_RECEIVED` -> worker looks
  up the paired Smartlead campaign and pauses that lead there by email.
- Pairing is a flat list in `CAMPAIGN_MAP` (see `campaign-map.example.json`) -
  add one entry per email/LinkedIn campaign pair you're running together.

## Known gap

`heyreachPauseLeadByEmail` in `worker.js` calls a HeyReach endpoint
(`HEYREACH_PAUSE_ENDPOINT`, default `/campaign/StopLeadInCampaign`) that was not
confirmed against a live Swagger doc - this repo's local HeyReach docs only cover
whole-campaign pause, not single-lead pause. Check
`https://api.heyreach.io/api/public/index.html` (Swagger, needs your API key) for
the real path before relying on this in production, then override it with the
`HEYREACH_PAUSE_ENDPOINT` secret if it differs. Everything else (Smartlead lookup
and pause, HeyReach->Smartlead direction) uses confirmed endpoints.

## Deploy (you run this, not Claude)

```bash
cd smartlead-kit/webhook-sync
npm install -g wrangler   # if you don't have it
wrangler login

wrangler secret put SMARTLEAD_API_KEY
wrangler secret put HEYREACH_API_KEY
wrangler secret put WEBHOOK_SECRET      # any random string, e.g. `openssl rand -hex 16`
wrangler secret put CAMPAIGN_MAP        # paste the contents of campaign-map.example.json (filled in)

wrangler deploy
```

This gives you a URL like `https://smartlead-heyreach-pause-sync.<you>.workers.dev`.

## Register the webhooks

**Smartlead** (Settings > Webhooks, or via API/MCP
`smartlead_add_or_update_campaign_webhook`):
- URL: `https://<your-worker>.workers.dev/smartlead/<WEBHOOK_SECRET>`
- Event: `EMAIL_REPLY`
- Repeat per Smartlead campaign that has a HeyReach pair.

**HeyReach** (Settings > Webhooks in the HeyReach UI):
- URL: `https://<your-worker>.workers.dev/heyreach/<WEBHOOK_SECRET>`
- Events: `MESSAGE_REPLY_RECEIVED`, `INMAIL_REPLY_RECEIVED`

## Limits

- Matching is by email only. If a HeyReach lead has no `emailAddress` populated,
  the worker can't find the Smartlead counterpart and skips (logged, no error).
- No retry queue - if the target platform's API is briefly down, that one pause
  is dropped. Fine for a "reduce embarrassing double-touches" tool, not built for
  guaranteed delivery.

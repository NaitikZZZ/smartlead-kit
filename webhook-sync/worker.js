/**
 * Cross-platform "stop on reply" relay for Smartlead <-> HeyReach.
 *
 * Problem: a lead can be on the same outreach cadence in both Smartlead (email)
 * and HeyReach (LinkedIn) at once. If they reply on one channel, the other
 * channel keeps sending unless someone pauses it by hand. This worker listens
 * to both platforms' reply webhooks and calls the other platform's pause API
 * for the matching lead.
 *
 * Deploy: `wrangler deploy` from this folder. See README.md for setup.
 *
 * Auth model: each platform's webhook URL includes a random secret path
 * segment (WEBHOOK_SECRET). Neither platform signs payloads in a way this
 * worker verifies, so the secret segment is the only gate - keep it private.
 */

const SMARTLEAD_BASE = "https://server.smartlead.ai/api/v1";
const HEYREACH_BASE = "https://api.heyreach.io/api/public";

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const [, platform, secret] = url.pathname.split("/");

    if (request.method !== "POST") {
      return new Response("ok", { status: 200 });
    }

    if (secret !== env.WEBHOOK_SECRET) {
      return new Response("forbidden", { status: 403 });
    }

    let payload;
    try {
      payload = await request.json();
    } catch {
      return new Response("bad payload", { status: 400 });
    }

    const campaignMap = JSON.parse(env.CAMPAIGN_MAP || "[]");

    try {
      if (platform === "smartlead") {
        await handleSmartleadReply(payload, campaignMap, env);
      } else if (platform === "heyreach") {
        await handleHeyReachReply(payload, campaignMap, env);
      } else {
        return new Response("unknown platform", { status: 404 });
      }
    } catch (err) {
      console.error(err);
      return new Response(`error: ${err.message}`, { status: 500 });
    }

    return new Response("ok", { status: 200 });
  },
};

// Smartlead replied -> pause the matching lead in the paired HeyReach campaign.
async function handleSmartleadReply(payload, campaignMap, env) {
  if (payload.event_type && payload.event_type !== "EMAIL_REPLY") return;

  const email = payload.to_email || payload.lead_email;
  const smartleadCampaignId = payload.campaign_id;
  if (!email || !smartleadCampaignId) return;

  const pair = campaignMap.find((p) => p.smartlead_campaign_id === smartleadCampaignId);
  if (!pair) {
    console.log(`No HeyReach campaign mapped for Smartlead campaign ${smartleadCampaignId}`);
    return;
  }

  await heyreachPauseLeadByEmail(pair.heyreach_campaign_id, email, env);
}

// HeyReach replied -> pause the matching lead in the paired Smartlead campaign.
async function handleHeyReachReply(payload, campaignMap, env) {
  const eventType = payload.eventType || payload.event_type;
  if (eventType && !["MESSAGE_REPLY_RECEIVED", "INMAIL_REPLY_RECEIVED"].includes(eventType)) return;

  const email = payload.lead?.emailAddress || payload.leadEmail;
  const heyreachCampaignId = payload.campaignId || payload.campaign_id;
  if (!heyreachCampaignId) return;

  const pair = campaignMap.find((p) => p.heyreach_campaign_id === heyreachCampaignId);
  if (!pair) {
    console.log(`No Smartlead campaign mapped for HeyReach campaign ${heyreachCampaignId}`);
    return;
  }

  if (!email) {
    // HeyReach only populates emailAddress when it was enriched onto the lead.
    // Without it there's nothing to match against Smartlead's lead-by-email lookup.
    console.log(`HeyReach reply had no email on lead, cannot match to Smartlead campaign ${pair.smartlead_campaign_id}`);
    return;
  }

  await smartleadPauseLeadByEmail(pair.smartlead_campaign_id, email, env);
}

async function smartleadPauseLeadByEmail(campaignId, email, env) {
  const lookup = await fetch(
    `${SMARTLEAD_BASE}/leads/by-email?email=${encodeURIComponent(email)}&api_key=${env.SMARTLEAD_API_KEY}`
  );
  if (!lookup.ok) throw new Error(`Smartlead lead lookup failed: ${lookup.status}`);
  const lead = await lookup.json();
  const leadId = lead.id || lead.lead_id;
  if (!leadId) {
    console.log(`No Smartlead lead found for ${email}`);
    return;
  }

  const pause = await fetch(
    `${SMARTLEAD_BASE}/campaigns/${campaignId}/leads/${leadId}/status?api_key=${env.SMARTLEAD_API_KEY}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: "PAUSED" }),
    }
  );
  if (!pause.ok) throw new Error(`Smartlead pause failed: ${pause.status}`);
  console.log(`Paused Smartlead lead ${leadId} in campaign ${campaignId} (${email})`);
}

// NOTE: HeyReach's public API docs at https://api.heyreach.io/api/public/index.html
// (Swagger) list a per-campaign lead pause/stop action, but the exact path was not
// confirmed against this repo's local docs (docs/heyreach-api-docs.md only lists
// whole-campaign Pause/Resume). Verify the endpoint below in the Swagger UI before
// relying on this - it's the one part of this file that's a best guess, not a
// confirmed contract.
async function heyreachPauseLeadByEmail(campaignId, email, env) {
  const endpoint = env.HEYREACH_PAUSE_ENDPOINT || "/campaign/StopLeadInCampaign";

  const res = await fetch(`${HEYREACH_BASE}${endpoint}`, {
    method: "POST",
    headers: {
      "X-API-Key": env.HEYREACH_API_KEY,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ campaignId, leadEmailAddress: email }),
  });
  if (!res.ok) throw new Error(`HeyReach pause failed: ${res.status} ${await res.text()}`);
  console.log(`Paused HeyReach lead ${email} in campaign ${campaignId}`);
}

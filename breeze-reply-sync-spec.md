# Breeze Build Spec: Smartlead + HeyReach Reply Sync

**Scope:** Contact object only. Phase 1.
**Goal:** When Smartlead or HeyReach reports reply status on a prospect, update the matching HubSpot contact. When a contact is marked Do Not Contact in HubSpot, push suppression back to both platforms.

---

## 0. Prerequisite (verify before building)
The "When a webhook is received" trigger requires **Data Hub (or Operations Hub) Professional or Enterprise**. Confirm the subscription is active in Settings > Account & Billing. If not active, this build is not possible natively and stops here.

## 1. Design summary
- HubSpot is the source. Prospects are created in HubSpot first, then pushed to Smartlead and HeyReach.
- HubSpot holds valid-email contacts only. This invariant stays.
- Every contact carries its **HubSpot Record ID** into both platforms at push time. That Record ID is the single match key on the way back.
- Any inbound webhook that does not match an existing contact is ignored. Intended, not an error (covers LinkedIn-only prospects that never entered HubSpot).
- All properties for this build are prefixed `ABM`.

## 2. Contact properties to create
Create in a property group named `Outbound Sync`. Skip any that already exist.

| Property label | Type | Options / notes |
|---|---|---|
| ABM External Match Key | Single-line text, **unique values required** | Stores the HubSpot Record ID. Both inbound workflows match on this field. |
| ABM Smartlead Reply Status | Dropdown select (single) | Replied, No Reply |
| ABM Smartlead Lead Category | Dropdown select (single) | Interested, Meeting Request, Not Interested, Wrong Person, Do Not Contact, Out of Office, Follow Up Later |
| ABM Smartlead Lead ID | Single-line text | |
| ABM Smartlead Campaign ID | Single-line text | |
| ABM HeyReach Lead Status | Dropdown select (single) | Replied, Connected |
| ABM HeyReach Lead Tag | Dropdown select (single) | Wrong POC, Meeting Scheduled, Interested Leads, Wrong Timing, Time Slot Shared, Meeting Completed, Redirected |

Do not create a HeyReach LinkedIn ID property. Reuse the existing LinkedIn URL field.

Optimization note: if the trigger UI lets you match directly on "Record ID," skip `ABM External Match Key` and match on Record ID instead.

## 3. Import seeding step (in your import tooling, not HubSpot)
- On each **Smartlead** lead, set a custom field `hubspot_record_id` to the contact's HubSpot Record ID.
- On each **HeyReach** lead that exists in HubSpot, set the same field.
- Confirm each platform includes that field in its outbound webhook payload.
- Populate HubSpot `ABM External Match Key` with the same Record ID value.

HeyReach leads with no Record ID (LinkedIn-only, no-email) arrive with no key and do not sync. By design.

## 4. Workflow A: Smartlead Reply Sync (inbound)
- **Type:** Contact-based workflow.
- **Trigger:** When a webhook is received. Content type `application/json`. Match on `ABM External Match Key`.
- **Actions:** Set `ABM Smartlead Reply Status`, `ABM Smartlead Lead Category`, `ABM Smartlead Lead ID`, `ABM Smartlead Campaign ID`.
- **Unmatched payload:** no action. Intended.

## 5. Workflow B: HeyReach Status Sync (inbound)
- **Type:** Contact-based workflow.
- **Trigger:** When a webhook is received. Content type `application/json`. Match on `ABM External Match Key`.
- **Actions:** Set `ABM HeyReach Lead Status`, `ABM HeyReach Lead Tag`.
- **Unmatched payload:** no action. Intended.

## 6. Workflow C: Suppression push-back (outbound, native Send a webhook)
Purpose: when a contact is marked Do Not Contact, tell both platforms to stop messaging them. (If the outbound is meant to do something else, say so and this section changes.)
- **Type:** Contact-based workflow.
- **Trigger:** `ABM Smartlead Lead Category` is any of [Do Not Contact], OR contact is set as unsubscribed / non-marketing. Keep it to Do Not Contact for Phase 1 to limit scope.
- **Action 1 - Send a webhook to Smartlead:**
  - Method: POST. URL: Smartlead's stop-lead / add-to-blocklist endpoint.
  - Auth: inline in the request header. Paste the Smartlead API key into the header value in the action config. Do not use the HubSpot secrets vault (native Send a webhook does not read it).
  - Body: include the contact's Record ID and `ABM Smartlead Lead ID`.
- **Action 2 - Send a webhook to HeyReach:**
  - Method: POST. URL: HeyReach's stop-lead-in-campaign endpoint.
  - Auth: inline header. Paste the HeyReach API key into the header value.
  - Body: include the contact's Record ID / LinkedIn identifier.

Native Send a webhook keeps the API key inside the action config, not the secrets vault, so no named secrets are created for this build.

## 7. Test / done criteria
- Inbound: a payload with a known Record ID enrolls the contact and updates the mapped properties. Unknown key does nothing (expected).
- Inbound: HeyReach leads without a Record ID produce no change (expected).
- Outbound: marking a test contact Do Not Contact fires both Send a webhook actions and returns 2xx from each platform.
- All three workflows show successful enrollment in history for matched records.

## 8. Phase 2 (later)
Revisit the Project (0-970) version once Contact build is stable. If inbound triggers aren't supported there, use a "Contact updates copy to associated Project" pattern instead.

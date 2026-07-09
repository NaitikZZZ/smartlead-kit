"""End-to-end Smartlead deploy for the SMB Tech SaaS campaigns.

Runs against two pre-created campaigns (Compass and Empuls) and:
1. Saves the 5-step sequence
2. Attaches 4 India-coded sender mailboxes
3. Sets an IST schedule (Mon-Fri, 09:00 to 18:00)
4. Uploads prospects from outputs/<campaign>/prospects.csv
5. Leaves both campaigns in DRAFTED state, manual launch via UI

Usage:
  SMARTLEAD_API_KEY=... python3 outputs/deploy_smb_techsaas.py

Idempotent: safe to re-run. Skip-on-409 logic for already-attached inboxes and duplicate leads.
"""
from __future__ import annotations

import csv
import os
import sys
import time
from pathlib import Path
from typing import Any

import urllib.parse
import urllib.request
import urllib.error
import json

API_BASE = "https://server.smartlead.ai/api/v1"
API_KEY = os.environ.get("SMARTLEAD_API_KEY") or sys.exit("Set SMARTLEAD_API_KEY")

KIT = Path("/Users/naitikchavda/Event Auto push/smartlead-kit")
OUT = KIT / "outputs"

CAMPAIGNS = {
    "compass": {
        "id": 3238358,
        "leads_csv": OUT / "smb_techsaas_compass" / "prospects.csv",
        # All 26 leads onboard day 1, max India inbox load for speed.
        "max_new_leads_per_day": 26,
        # 8 India-coded sales-flavored inboxes. Ashwin Ganesh is reserved
        # for reseller partnership campaigns only, see outputs/smartlead_inbox_routing_rules.md
        "inbox_ids": [
            16832001,  # pavitra.mishra@planwithxoxoday.com
            16832054,  # avni.sharma@insightswithxoxoday.com
            16831996,  # vanya.shah@xoxodaycorporatehub.com
            16831934,  # aarohi.desai@xoxoday-global.com
            16832055,  # eesha.mehta@progresswithxoxoday.com
            16831947,  # mahira.kapoor@progresswithxoxoday.com
            16831960,  # navisha.rathi@planwithxoxoday.com
            16832028,  # diya.nair@elevatewithxoxoday.com
        ],
    },
    "empuls": {
        "id": 3238359,
        "leads_csv": OUT / "smb_techsaas_empuls" / "prospects.csv",
        # All 45 leads onboard day 1, max India female-sender load for HR replies.
        "max_new_leads_per_day": 45,
        # 13 India-coded female senders. HR personas reply at higher rates to female senders in India.
        "inbox_ids": [
            16833694,  # ritu.sharma@xoxodaysystems.com
            16833695,  # riya.mehta@workwithxoxoday.com
            16833699,  # sneha.nair@xoxodaylabs.com
            16833664,  # anika.sharma@workwithxoxoday.com
            16833671,  # divya.iyer@xoxodaysystems.com
            16833663,  # aishwarya.mehta@xoxodaysystems.com
            16833678,  # kavya.rao@workwithxoxoday.com
            16833677,  # isha.kapoor@evolvewithxoxoday.com
            16833682,  # meera.shah@evolvewithxoxoday.com
            16833688,  # neha.verma@evolvewithxoxoday.com
            16833700,  # tanya.gupta@xoxodaylabs.com
            16832002,  # aisha.hassan@xoxoday-group.com
            16831984,  # arisha.mansoor@xoxodayinternational.com
        ],
    },
}

# ---------- Sequences ----------

COMPASS_BODY_1 = (
    "<p>Hi {{first_name}},</p>"
    "<p>Most Sales heads I speak to in Indian SaaS run their incentives, AE commissions, partner SPIFFs, contest payouts, and lead-reg bonuses, on a Sheet that one RevOps person owns. It eats 5 to 7 days every month.</p>"
    "<p>The bigger cost is trust. Reps and partners shadow-track their own numbers, escalate disputes, and stop believing accelerators are real.</p>"
    "<p>Compass, the sales incentives module of Empuls, replaces that sheet. Every AE and partner at {{company_name}} sees what they have earned in real time, every plan change goes live in a day, and Finance gets a clean audit trail. Payouts flow through Plum so rewards land in 100+ countries as cash, gift cards, or experiences. Pepsico, Hershey's, Capgemini, and Aditya Birla Capital run on it.</p>"
    "<p>Worth a 20 min look for {{company_name}}? Happy to come prepared with how SaaS teams your size structure plans for both internal reps and channel partners.</p>"
)

COMPASS_SEQUENCE = [
    {
        "seq_number": 1,
        "seq_delay_details": {"delay_in_days": 0},
        "variant_distribution_type": "MANUAL_EQUAL",
        "seq_variants": [
            {"variant_label": "A", "subject": "{{first_name}}, how is {{company_name}} running sales incentives this quarter", "email_body": COMPASS_BODY_1},
            {"variant_label": "B", "subject": "quick one on the {{company_name}} comp + SPIFF stack", "email_body": COMPASS_BODY_1},
            {"variant_label": "C", "subject": "{{first_name}}, the spreadsheet behind your reps' and partners' payouts", "email_body": COMPASS_BODY_1},
        ],
    },
    {
        "seq_number": 2,
        "seq_delay_details": {"delay_in_days": 3},
        "variant_distribution_type": "MANUAL_EQUAL",
        "seq_variants": [{
            "variant_label": "A",
            "subject": "Re: {{first_name}}, how is {{company_name}} running sales incentives this quarter",
            "email_body": (
                "<p>{{first_name}}, bumping this.</p>"
                "<p>To make it concrete, here is what month-end looks like for a 60-rep SaaS team plus 80 active partners after Compass:</p>"
                "<ul>"
                "<li>RevOps closes the comp + partner-payout run in under 2 hours, not 5 days</li>"
                "<li>Every AE and partner has a personal dashboard: quota attained, deals counted, accelerator tier, payout to date</li>"
                "<li>SPIFFs and contests go live in a few clicks, not a week of plan-doc edits</li>"
                "<li>Disputes drop because reps and partners see the math, not just the output</li>"
                "<li>Payouts flow straight to Plum, our rewards engine, so anyone in 100+ countries can take it as cash, gift cards, or experiences</li>"
                "</ul>"
                "<p>If even two of those would help {{company_name}}, I would love 20 mins.</p>"
            ),
        }],
    },
    {
        "seq_number": 3,
        "seq_delay_details": {"delay_in_days": 3},
        "variant_distribution_type": "MANUAL_EQUAL",
        "seq_variants": [{
            "variant_label": "A",
            "subject": "how 3 Indian SaaS sales orgs cut payout time by 95 percent",
            "email_body": (
                "<p>Hey {{first_name}},</p>"
                "<p>Three patterns we see across Indian SaaS teams that have moved their incentives onto Compass:</p>"
                "<p><strong>1. Mid-market SaaS, 400 AEs:</strong> Commission processing dropped from 6 days to 4 hours. Disputes fell 80 percent in two quarters because every rep could see the calc themselves.</p>"
                "<p><strong>2. B2B SaaS with 150 active partners:</strong> Partner SPIFFs and lead-reg bonuses moved off Sheets. Partners now see live dashboards. Channel manager time freed up by 12 hours a week. Partner satisfaction (measured) jumped 30 percent.</p>"
                "<p><strong>3. Series B SaaS, 150 FTE:</strong> Replaced a Spiff.com pilot with Compass for 30 percent less ACV and got the gamification layer (leaderboards, badges, contests) built in for both inside reps and partners.</p>"
                "<p>Worth pulling apart any of these for {{company_name}}? I can keep it to 20 minutes.</p>"
            ),
        }],
    },
    {
        "seq_number": 4,
        "seq_delay_details": {"delay_in_days": 3},
        "variant_distribution_type": "MANUAL_EQUAL",
        "seq_variants": [{
            "variant_label": "A",
            "subject": "20 minutes on the {{company_name}} sales incentives stack",
            "email_body": (
                "<p>{{first_name}},</p>"
                "<p>I have written a few notes, so let me be direct.</p>"
                "<p>If commissions, SPIFFs, partner payouts, or quota tracking at {{company_name}} are still living in Sheets, I would like 20 mins to:</p>"
                "<ol>"
                "<li>Map your current plan structure on a whiteboard, inside, field, channel, all of it</li>"
                "<li>Show a sandbox built around your motion</li>"
                "<li>Share what 3 SaaS teams in your headcount band are doing</li>"
                "</ol>"
                "<p>If the timing is wrong, just say \"later in 2026\" and I will park this. No follow-ups.</p>"
                "<p>Pick a slot here: [calendly link] or reply with two times that work.</p>"
            ),
        }],
    },
    {
        "seq_number": 5,
        "seq_delay_details": {"delay_in_days": 2},
        "variant_distribution_type": "MANUAL_EQUAL",
        "seq_variants": [{
            "variant_label": "A",
            "subject": "closing the loop, {{first_name}}",
            "email_body": (
                "<p>Hey {{first_name}},</p>"
                "<p>Last note from me on this thread.</p>"
                "<p>If sales incentives ever stop being a once-a-month firefight at {{company_name}}, Compass is here. One module inside Empuls for plans, dashboards, contests, and payouts, covering both internal reps and channel partners. Built for India SaaS sales teams.</p>"
                "<p>I will check back in a quarter. Wishing the team a strong close.</p>"
            ),
        }],
    },
]

EMPULS_BODY_1 = (
    "<p>Hi {{first_name}},</p>"
    "<p>Most People leaders I speak to in Indian SaaS describe R&R the same way: a peer Slack channel that runs hot for two weeks then dies, gift cards bought once a quarter, and an annual awards night that 30 percent of the company misses.</p>"
    "<p>Empuls puts all of it in one platform. Peer recognition inside Slack and Teams. Automated service anniversaries and birthdays. Lifecycle and pulse surveys. Perks and discounts. And a 10M+ rewards catalogue across 175+ countries, with a strong India catalogue (gold, local brands, experiences).</p>"
    "<p>KPIT, Prodevans, and Bahwan CyberTek run on it. Curious if R&R or engagement is on the list for {{company_name}} this year, worth a 20 min walkthrough?</p>"
)

EMPULS_SEQUENCE = [
    {
        "seq_number": 1,
        "seq_delay_details": {"delay_in_days": 0},
        "variant_distribution_type": "MANUAL_EQUAL",
        "seq_variants": [
            {"variant_label": "A", "subject": "{{first_name}}, how is recognition running at {{company_name}}", "email_body": EMPULS_BODY_1},
            {"variant_label": "B", "subject": "the {{company_name}} R&R stack, in 3 questions", "email_body": EMPULS_BODY_1},
            {"variant_label": "C", "subject": "{{first_name}}, a quick question on {{company_name}} engagement", "email_body": EMPULS_BODY_1},
        ],
    },
    {
        "seq_number": 2,
        "seq_delay_details": {"delay_in_days": 3},
        "variant_distribution_type": "MANUAL_EQUAL",
        "seq_variants": [{
            "variant_label": "A",
            "subject": "Re: {{first_name}}, how is recognition running at {{company_name}}",
            "email_body": (
                "<p>{{first_name}}, bumping this gently.</p>"
                "<p>To make it concrete, here is what HRBP life looks like for a 1,000-person team after Empuls:</p>"
                "<ul>"
                "<li>Peer recognition happens inside the Slack channel where work already happens. No new app to learn.</li>"
                "<li>Service anniversaries, work-iversaries, and birthdays trigger automatically with a budget you set, no spreadsheet to chase</li>"
                "<li>Pulse surveys go out monthly, eNPS is a live number not a quarterly project</li>"
                "<li>Employees redeem from 10M+ options across 175+ countries, with a deep India catalogue covering gold, local brands, and experiences</li>"
                "<li>Perks layer adds zero-cost discounts on everyday brands, employees actually use it</li>"
                "</ul>"
                "<p>If even two of those would help your team at {{company_name}}, I would love 20 mins. Promise to keep it focused on your headcount, not a generic deck.</p>"
            ),
        }],
    },
    {
        "seq_number": 3,
        "seq_delay_details": {"delay_in_days": 3},
        "variant_distribution_type": "MANUAL_EQUAL",
        "seq_variants": [{
            "variant_label": "A",
            "subject": "3 Indian tech companies, 3 different problems, 3 honest results",
            "email_body": (
                "<p>Hey {{first_name}},</p>"
                "<p>Three real Empuls customer outcomes, all Indian tech and IT firms, pulled from public case studies:</p>"
                "<p><strong>1. Prodevans Technologies (500-FTE Indian IT services, distributed across client sites):</strong> 70+ percent of employees actively participate on Empuls. Reward redemption moved from manual voucher purchasing to digital points with no expiry. Their HR called it \"the single point for everything employee engagement.\"</p>"
                "<p><strong>2. KPIT Technologies (5000+ FTE Indian software, presence in India, US, Europe, Japan):</strong> R&R budget scaled from 15 to 20 lakhs per quarter to nearly 45 lakhs per quarter as adoption grew. Peer-to-peer recognition rose sharply. Earlier reward points were sitting unredeemed because the catalogue was thin, Empuls solved that with 20,000+ options.</p>"
                "<p><strong>3. Bahwan CyberTek (1000 to 5000 FTE Indian software, global workforce):</strong> Used Empuls to connect a globally distributed engineering workforce through recognition, rewards, and the social intranet. The Head of Talent Engagement credited the platform with improved retention and engagement.</p>"
                "<p>The patterns hold across {{company_name}}'s headcount band. Worth pulling any of these apart on a 20 min call?</p>"
            ),
        }],
    },
    {
        "seq_number": 4,
        "seq_delay_details": {"delay_in_days": 3},
        "variant_distribution_type": "MANUAL_EQUAL",
        "seq_variants": [{
            "variant_label": "A",
            "subject": "20 minutes on {{company_name}}'s R&R stack",
            "email_body": (
                "<p>{{first_name}},</p>"
                "<p>I have written a few notes, so here is the direct ask.</p>"
                "<p>If R&R, engagement, or rewards at {{company_name}} are still spread across Slack channels, gift cards, and Excel, I would like 20 mins to:</p>"
                "<ol>"
                "<li>Map your current recognition flow on a whiteboard</li>"
                "<li>Show a sandbox tailored to {{company_name}}'s headcount and HR setup</li>"
                "<li>Share what comparable HR teams are doing in 2026</li>"
                "</ol>"
                "<p>If timing is wrong, just reply \"later\" and I will park this. No follow-ups, no nurture spam.</p>"
                "<p>Pick a slot here: [calendly link] or share two times.</p>"
            ),
        }],
    },
    {
        "seq_number": 5,
        "seq_delay_details": {"delay_in_days": 2},
        "variant_distribution_type": "MANUAL_EQUAL",
        "seq_variants": [{
            "variant_label": "A",
            "subject": "closing the loop, {{first_name}}",
            "email_body": (
                "<p>Hey {{first_name}},</p>"
                "<p>Last note from me on this thread.</p>"
                "<p>If R&R or engagement ever moves up the priority list at {{company_name}}, Empuls is here. One platform: peer recognition, milestones, surveys, perks, and a global rewards layer with a strong India catalogue.</p>"
                "<p>I will check back in a quarter. Wishing you and the team a strong year.</p>"
            ),
        }],
    },
]

SEQUENCES = {"compass": COMPASS_SEQUENCE, "empuls": EMPULS_SEQUENCE}

# ---------- HTTP helper ----------

def _req(method: str, path: str, body: dict | None = None) -> dict:
    qs = urllib.parse.urlencode({"api_key": API_KEY})
    url = f"{API_BASE}{path}?{qs}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    req.add_header(
        "User-Agent",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read().decode()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        return {"_error": True, "_status": e.code, "_body": body}


def save_sequence(campaign_id: int, sequence: list[dict]) -> dict:
    return _req("POST", f"/campaigns/{campaign_id}/sequences", {"sequences": sequence})


def attach_inbox(campaign_id: int, email_account_ids: list[int]) -> dict:
    return _req("POST", f"/campaigns/{campaign_id}/email-accounts", {"email_account_ids": email_account_ids})


def set_schedule(campaign_id: int, max_new_leads_per_day: int) -> dict:
    return _req("POST", f"/campaigns/{campaign_id}/schedule", {
        "timezone": "Asia/Kolkata",
        "days_of_the_week": [1, 2, 3, 4, 5],
        "start_hour": "09:00",
        "end_hour": "18:00",
        "min_time_btw_emails": 10,
        "max_new_leads_per_day": max_new_leads_per_day,
    })


def upload_leads(campaign_id: int, leads: list[dict]) -> dict:
    return _req("POST", f"/campaigns/{campaign_id}/leads", {
        "lead_list": leads,
        "settings": {"ignore_duplicate_leads_in_other_campaign": False},
    })


def load_leads(csv_path: Path) -> list[dict]:
    out = []
    with csv_path.open() as f:
        for row in csv.DictReader(f):
            email = (row.get("email") or "").strip()
            if not email or "@" not in email:
                continue
            out.append({
                "first_name": row.get("first_name", "").strip(),
                "last_name": row.get("last_name", "").strip(),
                "email": email,
                "company_name": row.get("company_name", "").strip(),
                "phone_number": (row.get("phone_number") or "").strip(),
                "website": (row.get("website") or "").strip(),
                "location": (row.get("location") or "").strip(),
                "linkedin_profile": (row.get("linkedin_profile") or "").strip(),
                "custom_fields": {
                    "job_title": row.get("job_title", "").strip(),
                    "tier": row.get("tier", "").strip(),
                    "segment": row.get("segment", "").strip(),
                    "personalized_line": row.get("personalized_line", "").strip(),
                },
            })
    return out


def _fmt(r: dict) -> str:
    if not r.get("_error"):
        return "OK"
    body = (r.get("_body") or "")[:240]
    return f"FAIL {r.get('_status')} {body}"


def main() -> int:
    for label, cfg in CAMPAIGNS.items():
        cid = cfg["id"]
        print(f"\n=== {label.upper()} (campaign {cid}) ===")

        r = save_sequence(cid, SEQUENCES[label])
        print(f"  [1/4] save_sequence -> {_fmt(r)}")

        r = attach_inbox(cid, cfg["inbox_ids"])
        print(f"  [2/4] attach_inbox  -> {_fmt(r)}")

        r = set_schedule(cid, cfg["max_new_leads_per_day"])
        print(f"  [3/4] set_schedule  -> {_fmt(r)}")

        leads = load_leads(cfg["leads_csv"])
        for i in range(0, len(leads), 400):
            batch = leads[i:i + 400]
            r = upload_leads(cid, batch)
            print(f"  [4/4] upload {len(batch)} leads (batch {i // 400 + 1}) -> {_fmt(r)}")
            if r.get("upload_count") is not None:
                print(f"        uploaded={r.get('upload_count')} duplicate={r.get('already_added_to_campaign')} unsubscribed={r.get('unsubscribed_leads')} invalid={r.get('invalid_emails_count')}")
            time.sleep(1)

    print("\nDone. Both campaigns left in DRAFTED state. Review in Smartlead UI before launching.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

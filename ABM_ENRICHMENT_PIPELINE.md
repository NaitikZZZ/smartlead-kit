# Xoxoday — ABM Contact Enrichment Pipeline

*Reference documentation. Last updated from the UK/EUR and Indonesia/Philippines pipeline runs.*

## Table of Contents
1. Problem Statement
2. Complete Pipeline Flow
3. Stage Walkthrough
   - 3.1 Suppression (Exclusion Check)
   - 3.2 Normalization
   - 3.3 Domain Resolution
   - 3.4 People Discovery
   - 3.5 Email Enrichment
   - 3.6 Phone Enrichment
   - 3.7 Output Assembly
4. Script Specification
5. Configuration Reference
6. Technical Implementation
   - 6.1 Enrichment Waterfall Pipeline
   - 6.2 Environment & API Requirements

---

## 1. Problem Statement

Every outbound list handed to this pipeline starts as a raw export — a conference attendee sheet, a target-account list, a company list with job titles attached. None of it is safe to load into Smartlead or HeyReach as-is: company names are unnormalized, domains are unknown or ambiguous, some fraction of the list is already a customer, and named contacts have no verified way to reach them.

Two runs this month illustrate the failure modes a manual process misses. On a 128-row UK/EUR list, 4 companies turned out to be active client relationships that would have been cold-emailed by mistake. On a 150-row Indonesia/Philippines company list, the same generic-name problem that let "Flip" resolve to an unrelated Indonesian fintech instead of the intended German HR-tech company appeared repeatedly — short or common company names silently match the wrong real company more often than expected, and a human skimming a spreadsheet has no way to catch it without checking every row by hand.

This pipeline replaces that manual check with a sequence of stages that never guesses when it isn't confident — a wrong-company match or an unverified contact detail is treated as a bug, not an acceptable miss rate. Ambiguity gets surfaced for a five-second human decision instead of silently resolved.

---

## 2. Complete Pipeline Flow

The pipeline is a straight-line waterfall with one fork (named list vs. company-only list) and a persistent cache layer underneath every stage, so a company or contact resolved once is never re-processed or re-paid for.

```
                              LIST ARRIVES
                          (CSV or list link)
                                  │
                                  ▼
                    ┌─────────────────────────┐
                    │  1. SUPPRESSION          │  Hunting → check vs Account Mapping Sheet
                    │     (Exclusion Check)    │  Farming → skip, everyone passes
                    └────────────┬─────────────┘
                                  ▼
                    ┌─────────────────────────┐
                    │  2. NORMALIZATION        │  Clean names + company names
                    └────────────┬─────────────┘
                                  ▼
                    ┌─────────────────────────┐
                    │  3. DOMAIN RESOLUTION    │  Cache → Apollo → majority-vote →
                    │                          │  employee-count → flag if unsure
                    └────────────┬─────────────┘
                                  ▼
                    Named contacts already? ──── YES ──────────┐
                                  │ NO                          │
                                  ▼                              │
                    ┌─────────────────────────┐                │
                    │  4. PEOPLE DISCOVERY     │                │
                    │     (Apollo search,      │                │
                    │      free, no reveal)    │                │
                    └────────────┬─────────────┘                │
                                  └──────────────┬───────────────┘
                                                  ▼
                    ┌─────────────────────────────────────────┐
                    │  5. EMAIL ENRICHMENT                     │
                    │     Apollo → Lusha → ZeroBounce validate │
                    │     (domain-match safety check throughout)│
                    └────────────────────┬──────────────────────┘
                                          ▼
                    ┌─────────────────────────────────────────┐
                    │  6. PHONE ENRICHMENT (optional, costed)  │
                    │     Apollo async reveal, cached          │
                    └────────────────────┬──────────────────────┘
                                          ▼
                    ┌─────────────────────────────────────────┐
                    │  7. OUTPUT ASSEMBLY                      │
                    │     Email / LinkedIn / Calling /         │
                    │     Needs-Manual-Review                  │
                    └───────────────────────────────────────────┘
```

---

## 3. Stage Walkthrough

Each section covers one stage — the trigger, the exact logic, and the reasoning behind the design decision.

### 3.1 Suppression (Exclusion Check)

Runs first, before anything else touches the list, so no downstream credits get spent on a company we shouldn't be emailing at all.

Ask which campaign type this is before running anything. **Farming** campaigns skip this stage entirely — every company passes through. **Hunting** campaigns check every company against the master Account Mapping Sheet (Client Name, Domain, Parent Company, Type 1, Parent Company Status), matching in order: exact domain → fuzzy client name (legal suffixes stripped) → fuzzy parent company. A prospect is **OK to reach out** only if the matched row's Type 1 status *and* Parent Company Status are both `Dead`. Anything else on a matched row is **Excluded** — the conservative read, since a false exclusion costs one lead, but a false inclusion means cold-emailing an existing customer. No match at all means it's a genuinely new account and passes through.

Output columns: `Exclusion Status`, `Exclusion Reason`, `Matched Account`.

### 3.2 Normalization

Cleans the surviving rows before anything gets searched against an external API — inconsistent casing and legal-entity suffixes ("Pvt Ltd", "Inc.", "(P) Ltd") reduce match quality downstream, so they're stripped here once rather than fought individually at each later stage.

Splits a Full Name into First/Last (first token → first name, everything else → last name). Strips honorific prefixes and degree/generational suffixes from names. Strips legal-entity suffixes from company names. Originals are always preserved alongside the cleaned columns, never overwritten.

### 3.3 Domain Resolution

The highest-risk stage in the pipeline — a wrong domain here means every downstream email search targets the wrong real company. Never guesses when uncertain.

Checks the shared cache first (instant, free, and grows with every list run). On a cache miss, searches Apollo's organization directory by the cleaned company name. If Apollo returns exactly one exact-name match, accept it. If it returns several, first check whether they already agree on the same domain — large companies frequently have duplicate/fragmented org records under an identical display name, and treating that as ambiguous would falsely block obvious cases (Ernst & Young showed up as 18 near-duplicate records, all pointing to `ey.com`). Only when the candidates genuinely disagree on domain does it fall to employee-count comparison against the source list's headcount column, and only when *that* produces a clear winner does it accept automatically. Anything left — no employee-count signal, or a real split decision — is flagged **Ambiguous** with the full candidate list, for a human to pick in seconds rather than the pipeline guessing wrong. Zero exact-name matches at all is flagged **Unresolved**, which typically means a small/regional company or a stale legacy brand name that needs a quick web search.

Output columns: `Resolved Domain`, `Resolved Company LinkedIn`, `Resolution Source`.

### 3.4 People Discovery

Only runs when the input list is company names without named contacts. Runs before any credits are spent — a person-search query against Apollo is free; only revealing a specific person's contact details costs credits.

Searches Apollo by company domain plus the target job titles, with a seniority filter (`c_suite`, `vp`, `head`, `director`, `manager`) applied at the query level — without it, a single page of title-matched results at a large company gets swamped by hundreds of lower-level hits and the actual decision-maker never surfaces. Search results come back with an obfuscated last name (e.g. "Laura Bu\*\*\*r") plus flags for whether Apollo has email/phone data on file — real names and contact details are revealed in a separate, credit-costed step. Candidates are ranked by how senior their title is, one distinct seniority tier covered before doubling up on any tier, up to a configurable cap per company.

### 3.5 Email Enrichment

The core enrichment step, and the one that most needs its own safety net — a "verified" email from any single provider is not proof it belongs to the company you're searching for.

Calls Apollo's contact match (by Apollo ID when available, otherwise name + domain) and checks the returned email's domain against the company domain being searched. A match is accepted outright; a known alias (a confirmed rebrand, an M&A absorption, or a company that genuinely emails from a different domain than its marketing site) is also accepted; a same-brand name under a different country code (any large multinational professional-services network) is also accepted. Anything else is held as a **mismatch** for manual review rather than trusted or discarded automatically. Contacts Apollo can't find an email for at all fall to a second waterfall step through Lusha, using the same domain-match check, and any Lusha hit must additionally pass ZeroBounce validation before it's accepted.

### 3.6 Phone Enrichment

Optional, and meaningfully more expensive than email — treat this as a deliberate scope decision, not something to default on for a large list.

Apollo's phone reveal is asynchronous: it never returns a number in the direct response, only via a webhook callback seconds later, so this stage needs an internet-facing relay to receive it. Confirmed through testing: Apollo does not call the webhook at all when it has no phone data — a missing callback means "nothing on file," not a slow response, so the wait window can stay short. Every successful reveal is cached (keyed by contact, not by list) so the same person is never paid for twice across runs, even in a future, unrelated list.

### 3.7 Output Assembly

Splits the fully-enriched list into channel-specific files so each downstream tool only sees what it needs, plus a bucket for anything that didn't clear the bar. Nothing that fails a check gets silently dropped — every non-accepted row lands in the Needs Manual Review file with the reason attached.

---

## 4. Script Specification

| Stage | Script | Calls | Output |
|---|---|---|---|
| Suppression | `abm-exclusion-check` skill | — (local match, no API) | Exclusion Status / Reason / Matched Account |
| Normalization | `name-company-normalizer` skill | — (local match, no API) | Cleaned First/Last/Company Name |
| Domain Resolution | `scripts/resolve_company_domains.py` | Apollo Org Search | Resolved Domain / LinkedIn / Source |
| People Discovery | `scripts/search_company_contacts_apollo.py` | Apollo People Search (free) | apollo_id / title / persona_tier / has_email / has_direct_phone |
| Email Enrichment | `scripts/enrich_contacts_apollo.py` | Apollo People Match | email / email_status / linkedin_apollo / note |
| Email Waterfall (fallback) | `scripts/lusha_waterfall_enrich.py` | Lusha Search & Enrich + ZeroBounce | lusha_email / zerobounce_status / lusha_note |
| Phone Enrichment | `scripts/enrich_phone_apollo.py` | Apollo People Match (async reveal) + webhook.site | Phone Number / Type / Confidence / Note |
| Phone comparison (diagnostic) | `scripts/lusha_phone_compare.py` | Lusha Search & Enrich | Side-by-side Apollo vs. Lusha phone results |

---

## 5. Configuration Reference

Every knob worth tuning, where it lives, and what changing it actually does.

| Stage | Parameter | Location | Default | Controls |
|---|---|---|---|---|
| Suppression | Campaign type | Asked at runtime | — | Whether exclusion logic applies at all (Farming = skip) |
| Suppression | Fuzzy match threshold | `check_exclusions.py` | 0.88 | How lenient company-name matching is before flagging "no match" |
| Domain Resolution | Shared cache | `reference/company_domain_cache.csv` | grows over time | Instant, free resolution for any company seen before |
| Domain Resolution | Majority-domain threshold | `resolve_company_domains.py` | >50% of candidates | When duplicate org records are treated as agreement vs. real ambiguity |
| Domain Resolution | Employee-count ambiguity gate | `resolve_company_domains.py` | gap > 0.5 and gap-difference < 0.15 | When to flag instead of auto-picking the closest headcount match |
| Domain Resolution | Legal-suffix list | `resolve_company_domains.py` (`_LEGAL_SUFFIX_RE`) | Inc/Ltd/Corp/PLC/GmbH/Co/(P) Ltd, etc. | Which suffixes get stripped before name comparison |
| Domain Resolution | Apollo search page size | `resolve_company_domains.py` | 25 | How many candidates get pulled before giving up |
| People Discovery | Target job titles | `search_company_contacts_apollo.py` (`PERSONAS`) | 17 HR-function titles | Which roles get searched for at each company |
| People Discovery | Seniority filter | `search_company_contacts_apollo.py` | c_suite, vp, head, director, manager | Which seniority levels Apollo returns at all |
| People Discovery | Max contacts per company | `search_company_contacts_apollo.py` (`MAX_PER_COMPANY`) | 10 | Contact volume cap, applied after seniority-tier ranking |
| Email Enrichment | Known domain aliases | `reference/domain_aliases.csv` | grows over time | Which "mismatched" domains are actually legitimate (rebrands, M&A, dual-domain) |
| Email Enrichment | Country-variant matching | `enrich_contacts_apollo.py` (`domain_root`) | root name ≥ 4 chars | Auto-accepts same-brand, different-country-TLD emails (e.g. Deloitte UK vs. US) |
| Email Waterfall | Run Lusha at all? | Asked at runtime | — | Whether to spend Lusha credits on Apollo's misses |
| Email Waterfall | ZeroBounce acceptance statuses | `lusha_waterfall_enrich.py` | `valid`, `catch-all` | How strict the validation gate is before accepting a Lusha email |
| Phone Enrichment | Run phone at all? | Asked at runtime | off by default | Cost gate — phone is ~8x the credit cost of email |
| Phone Enrichment | Poll timeout | `enrich_phone_apollo.py` (`POLL_TIMEOUT`) | 30s | How long to wait for Apollo's async webhook callback |
| Phone Enrichment | Persistent cache | `reference/phone_reveal_cache.csv` | grows over time | Never re-pay for a phone number already revealed |
| Phone Enrichment | Cache invalidation | Manual — delete the row | none automatic | No job-change detection; stale numbers must be cleared by hand |

---

## 6. Technical Implementation

| Layer | Responsibility | Technology |
|---|---|---|
| Orchestrator | Decide campaign type, sequence stages, gate any costly step behind an explicit go-ahead | Agent session (this pipeline) |
| Suppression | Match prospects against the master Account Mapping Sheet | Python + fuzzy match |
| Normalization | Clean names and company names | Python |
| Domain Resolution | Resolve and cache company domains | Apollo Org Search API + persistent CSV cache |
| People Discovery | Find named contacts at target companies | Apollo People Search API (no cost) |
| Email Enrichment | Reveal and validate verified emails | Apollo People Match → Lusha → ZeroBounce waterfall |
| Phone Enrichment | Reveal verified mobile numbers | Apollo async reveal via webhook relay + persistent cache |
| Output | Assemble channel-specific deliverables | Python / pandas |

### 6.1 Enrichment Waterfall Pipeline

| Step | Action | Details |
|---|---|---|
| 1. SUPPRESS | Check against client list | Domain / name / parent-company match, Hunting campaigns only |
| 2. CLEAN | Normalize names and companies | Strip suffixes, split full names |
| 3. RESOLVE | Find each company's domain | Cache → Apollo → majority-vote → employee-count → flag if unsure |
| 4. DISCOVER | Find people, if not already named | Apollo search by title + seniority, free |
| 5. VERIFY EMAIL | Reveal and validate | Apollo → Lusha → ZeroBounce |
| 6. VERIFY PHONE | Reveal, optional | Apollo webhook reveal, cached per contact |
| 7. ASSEMBLE | Build deliverables | Email / LinkedIn / Calling / Needs Manual Review |

### 6.2 Environment & API Requirements

| Requirement | Details |
|---|---|
| API keys | `APOLLO_API_KEY`, `LUSHA_API_KEY`, `ZEROBOUNCE_API_KEY`, `SMARTLEAD_API_KEY`, `HEYREACH_API_KEY` — all in `.env`, never printed to chat or committed |
| Reference files | `company_domain_cache.csv`, `phone_reveal_cache.csv`, `domain_aliases.csv` — self-updating, shared across every future list |
| Master data source | Account Mapping Sheet, sourced from HubSpot (read-only — never written back to) |
| Cost model | Apollo email ≈ 1 credit/hit · Apollo phone ≈ 8 credits/hit · Lusha ≈ 6 credits/hit (email or phone) · ZeroBounce ≈ 1 validation/check |
| Third-party relay | webhook.site — created fresh per phone-enrichment run, deleted immediately after; no permanent storage of contact data on a third-party service |

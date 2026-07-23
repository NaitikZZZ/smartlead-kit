# Apollo Prospect Search (HubSpot Project without List)

When a HubSpot Project is loaded but has **no target account list linked**, the system now offers to use Apollo to **find prospects automatically** based on project properties and your input.

---

## Workflow

### 1. Load HubSpot Project (No List)
- Project loaded but no spreadsheet/webpage linked
- System asks: "Use Apollo to find prospects based on HubSpot properties?"

### 2. Enter Company Names
You provide the companies you want to target:
```
Company names to search: Acme Corp, TechCo Inc, StartUp Labs
```
System resolves these to domains (via Apollo).

### 3. Describe Your ICP (Ideal Customer Profile) ✨ NEW
Instead of asking for individual filters, describe your ideal customer in natural language:

```
What's your Ideal Customer Profile (ICP)?

Example input:
"VP or Head of HR at mid-size tech companies (100-500 employees) 
in the US and Europe. Should be on LinkedIn with public profiles.
Focus on VC-backed startups scaling to Series B/C."
```

Claude automatically extracts:
- **Job titles:** VP HR, Head of People, CHRO, etc.
- **Regions:** US, Europe
- **Company size:** 100-500 employees
- **Industry hints:** (used for manual filtering)

### 3b. Confirm & Override (Optional)
Claude shows you the extracted filters:
```
Job Titles: VP of HR, Head of People, Chief People Officer
Regions: US, Europe
Employee Size: 100-500
```

- **Proceed:** Use these filters
- **Override:** Manually adjust regions, titles, or size

### 4. Apollo Searches Companies
System:
1. Resolves company names to domains
2. Searches Apollo for each domain with your filters
3. Returns prospects matching region + job title + employee size

---

## Example Scenarios

### Scenario A: HR/People Leaders (ICP-based) ✨ NEW
```
Companies: Acme Corp, TechCo Inc, StartUp Labs

ICP Description:
"VP or Head of HR at mid-market US tech companies (100-500 employees).
Should be on LinkedIn. Open to recognizing/rewarding employees."

Claude extracts:
  → Job Titles: VP of HR, Head of People, Chief People Officer
  → Regions: US
  → Employee Size: 100-500

Result: Finds HR leaders matching all criteria
```

### Scenario B: Sales Leaders (Manual filters)
```
Companies: GlobalCorp, InternationalCo
Region: US, Europe, India
Employee Size: [blank = all sizes]
Job Titles: VP Sales, CRO, Head of Revenue
```
→ Finds sales leaders across multiple regions

### Scenario C: Engineering Leaders, Global
```
Companies: TechCorp
Region: [blank = Global]
Employee Size: 200+
Job Titles: VP Engineering, CTO, Head of Infrastructure
```
→ Finds engineering leaders worldwide, any size

---

## ICP Parsing (Claude-Powered) ✨ NEW

When you describe your ICP in natural language, Claude:

1. **Reads your description**
   ```
   "VP or Head of HR at mid-size B2B SaaS companies (100-500 employees)
    in US and UK. Focus on companies in growth/scaling phase."
   ```

2. **Extracts structured filters**
   ```json
   {
     "job_titles": ["VP of HR", "Head of People", "Chief People Officer"],
     "regions": ["US", "UK"],
     "employee_size": "100-500",
     "reasoning": "Extracted from ICP description"
   }
   ```

3. **Shows you what was extracted**
   ```
   Claude found:
   Job Titles: VP of HR, Head of People, Chief People Officer
   Regions: US, UK
   Employee Size: 100-500
   
   Proceed with these filters?
   ```

4. **Lets you confirm or override**
   - ✅ Proceed: Use extracted filters
   - ❌ Override: Manually adjust regions, titles, or size

### What Claude Understands in ICP

The ICP parser can extract:
- **Job titles:** VP, Head of, Director, Manager, C-level
- **Regions:** US, UK, Europe, APAC, India, Canada, Australia
- **Company size:** 1-10, 11-50, 51-200, 201-500, 501-1000, 1001+
- **Growth stage:** Early-stage, Series A, Series B, Growth-stage, Enterprise
- **Industry:** Tech, B2B, SaaS, Healthcare, Finance, etc.
- **Characteristics:** VC-backed, profitable, IPO candidates, etc.

### Example ICP Descriptions

**Example 1: HR/Recognition**
```
"VP or Head of HR at mid-market SaaS companies (100-500 employees) 
in US and Europe. Companies scaling and need employee recognition solutions."

→ Extracts: VP/Head of HR, US/Europe, 100-500 employees
```

**Example 2: Sales/Revenue**
```
"CRO or VP Sales at enterprise software companies ($100M+ ARR) 
in North America. Need sales commission automation."

→ Extracts: CRO/VP Sales, US/Canada, 500+ employees
```

**Example 3: DevOps/Infrastructure**
```
"VP Engineering or Head of Infrastructure at fast-growing Series B/C 
tech startups in US with 50-200 employees. Using modern cloud stack."

→ Extracts: VP/Head Engineering, US, 50-200 employees
```

---

## Behind the Scenes: Apollo Logic

### Current Implementation
1. **Heuristic Detection** (~1 second, free)
   - Scan each prospect for keyword matches
   - Rank by persona tier (VP > Head > Manager > etc.)
   - Prefer candidates with email address
   - Select up to N candidates per company

2. **Priority Order** (which filters apply first)
   ```
   1. Region filter (person_locations)
   2. Job title filter (person_titles)
   3. Seniority filter (person_seniorities: c_suite, vp, head, director, manager)
   4. Employee size (via company info)
   ```

3. **Default Personas** (if not overridden)
   ```
   - Chief Human Resources Officer / Chief People Officer
   - VP of HR / Director of HR
   - Head of Employee Experience / Engagement / Rewards
   - Head of Compensation / Benefits
   - HR Business Partner
   - Director/Manager People Operations
   ```

### Cost
- **Search:** Free (returns obfuscated previews)
- **Enrichment:** Paid only for selected prospects
  - Email reveal: ~1 credit per person
  - Full fields: ~1 credit per person
  - Phone: ~1 credit per person

---

## Why This Approach?

### When to Use Apollo Search
- ✅ You know target companies but not specific contacts
- ✅ You want to filter by region/job title/company size
- ✅ You want Apollo to handle the discovery (they have the latest LinkedIn data)
- ✅ You prefer not to maintain a manual contact list

### When to Upload a CSV Instead
- ✅ You already have a contact list
- ✅ You want to enrich existing contacts (don't need discovery)
- ✅ You have non-standard data (not from Apollo/LinkedIn)
- ✅ You need exact control over which contacts to include

---

## Next Steps (After Apollo Search)

After Apollo finds prospects:
1. **Email Reveal:** Unlock email addresses (paid)
2. **Phone Reveal:** Get phone numbers (paid)
3. **Segmentation:** Auto-segment by intent
4. **Exclusion Check:** Remove existing clients
5. **Copy Generation:** Email + LinkedIn sequences
6. **Deploy:** Smartlead + HeyReach campaigns
7. **Export:** HubSpot upload

---

## Troubleshooting

### "Could not resolve domains for companies"
- Check company names are correct and publicly listed
- Try alternative company names (legal name vs. common name)
- Use company website domain if known (e.g., "acme.com")

### "No prospects found for a company"
- Region filter too strict (change to Global)
- Job titles don't match (adjust personas)
- Company too small/large (change employee size filter)
- Company may not have LinkedIn presence for Apollo to index

### High cost / too many results
- Narrow the filter: specific regions, specific job titles, smaller employee size
- Use fewer company targets
- Adjust candidates per company in config

---

**Added:** When HubSpot Project has no linked list, ask to use Apollo to find prospects instead
**Configuration:** Region, employee size, job titles all customizable per run
**Cost:** Search free, enrichment paid only for selected prospects

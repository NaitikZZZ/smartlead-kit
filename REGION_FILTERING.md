# Apollo Region Filtering

When searching for contacts via Apollo in Step 4 (People Discovery), you can now filter by geographic region.

## How It Works

During the Apollo search, you'll be asked:
```
Filter by region? (comma-separated: US, UK, India, Europe, APAC, Global, etc.) Blank = Global
```

**Default:** Global (no region filter)

## Supported Regions

Apollo supports filtering by person location (where they are based, not company HQ):

Common regions:
- `US` - United States
- `UK` - United Kingdom  
- `India` - India
- `Europe` - Europe
- `APAC` - Asia-Pacific
- `Global` - No filter (default)

You can also use:
- Country names: `Canada`, `Australia`, `Germany`, `France`, etc.
- Multi-region: `US, UK, India` (comma-separated)

## Examples

**Just US contacts:**
```
Filter by region? → US
```

**US + India:**
```
Filter by region? → US, India
```

**Europe only:**
```
Filter by region? → Europe
```

**Global (default):**
```
Filter by region? → [leave blank]
```

## Notes

- **Person location**, not company location: Filters by where the contact is physically based, not where the company HQ is
- **Case-insensitive**: Both "US" and "us" work
- **Whitespace handled**: Leading/trailing spaces are trimmed automatically
- **No filter = Global**: If you leave it blank, Apollo searches globally across all locations

## Behind the Scenes

The region filter is passed to Apollo's `person_locations` parameter in the People Search API. Apollo matches against contact location data from LinkedIn and other sources.

Example API call:
```python
payload = {
    'q_organization_domains_list': [domain],
    'person_titles': ['VP', 'Head of', ...],
    'person_locations': ['US', 'India'],  # ← Region filter
    'page': 1,
    'per_page': 50,
}
```

## Impact on Credits

Region filtering **does not cost extra credits**. The Apollo search step is always free (it returns obfuscated previews). Only the subsequent email/phone reveals cost credits.

---

**Added:** Step 4 (People Discovery) now always asks for region preference
**Default behavior:** Global search (no region filter) when blank

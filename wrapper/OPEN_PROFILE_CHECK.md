# Open profile check

Teammates paste a Sales Navigator search link on the "Open profile check" page and later download two lists (open profile, not open) plus a summary. Sign-in uses the existing per-person passwords, and each check is stamped with the signed-in name.

## How it works

- **This site** is the intake and results layer: `app/routes/open_profile.py` (API) and `frontend/src/components/OpenProfileCheck.tsx` (page). Job records and events live in Upstash Redis (`opc:*` keys). Result files live in Vercel Blob (`opc/<job>/...`), stored in parts of at most 3 MB because Vercel functions cannot accept or return bodies over about 4.5 MB. The page stitches the parts back into one file in the browser.
- **The work itself** (split the search, import into Waalaxy through Chrome, export, merge by Premium) is done by a worker machine that has Chrome, Sales Navigator and Waalaxy signed in. It polls this site outward, so nothing connects in to it. It uses `open_profile_app/worker_cli.py` from the nac_outbound_kit repo with `OPEN_PROFILE_HOSTED=1`.
- Checks run one at a time. If the worker is off, checks stay "In line" and nothing is lost.

## To deploy

1. Add `OPEN_PROFILE_WORKER_TOKEN` in Vercel (any long random string). The worker routes reject every request while it is unset.
2. Give the same value to the worker machine as `WORKER_TOKEN`, with `OPEN_PROFILE_APP_URL` set to this site.
3. Redis, Blob and `APP_USERS` are already configured for the wrapper and are reused as they are.

## Notes

- Open profile means LinkedIn Premium. That is a proxy, so the page says "likely open".
- Waalaxy skips leads already in the account, so coverage can be below 100%. The page shows the percentage found.
- Tests: `wrapper/backend/.venv/bin/python3 wrapper/backend/tests/test_open_profile.py`. They force the in-memory fallback, because a local `.env` can point at the live Redis.

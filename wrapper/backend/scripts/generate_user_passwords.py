"""Generates one random password per person and prints the APP_USERS value
(SHA-256 hashes only) to paste into the backend env. Plain passwords print
once, to this terminal only, to hand to each person - they are not saved.

Usage: python3 scripts/generate_user_passwords.py "Name One" "Name Two" ...
"""
import hashlib
import json
import secrets
import sys

names = sys.argv[1:]
if not names:
    sys.exit(__doc__)

users, passwords = {}, {}
for name in names:
    pw = "ab-" + secrets.token_urlsafe(24)
    users[hashlib.sha256(pw.encode()).hexdigest()] = name
    passwords[name] = pw

print("Passwords (give each person their own, then clear your terminal):")
for name, pw in passwords.items():
    print(f"  {name}: {pw}")
print("\nAPP_USERS value (set in the backend env, e.g. Vercel):")
print(json.dumps(users))

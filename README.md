# intelx-toolkit

A generic CLI for the [Intelligence X](https://intelx.io) API, scoped to
what a free/community-tier API key is actually allowed to do.

Self-contained: everything needed lives in this directory, including a
vendored copy of the API client (see "Why `intelxapi.py` is vendored"
below), so it can be moved anywhere on its own.

## Background

This started as part of a project (`mailhunter`) trying to convert a
Phonebook-search email harvester to use the official `intelx` client
instead of hand-rolled `requests` calls against `phonebook.cz`. That
investigation found:

- The `intelx` PyPI package (0.8.1) is broken: its wheel installs
  `__init__.py` / `intelxapi.py` / `intelx_identity.py` flat into
  `site-packages` instead of inside an `intelx/` package directory, so
  `pip install intelx` + `from intelx import intelx` never actually works.
  The real class lives at `intelxapi.intelx`.
- The free tier lives on a **different host**, `free.intelx.io`, not the
  `2.intelx.io` the SDK defaults to and the old script hardcoded.
- `intelxapi.py` builds URLs as `self.API_ROOT + url` with no separator, so
  a `base_url` with a trailing slash (an easy thing to paste into `.env`,
  and how this project's `.env` had it) produces a double slash like
  `https://free.intelx.io//intelligent/search`. GET endpoints tolerate
  that, but **POST endpoints reject it with `HTTP 405 Method Not
  Allowed`** — this cost real debugging time, since a 405 there looks
  exactly like "this endpoint isn't on your plan." `ixtool.py` strips the
  trailing slash defensively; watch for this if you touch `intelxapi.py`
  or `INTELX_URL` directly.
- With that fixed, `/phonebook/search` (OSINT email harvesting) returns a
  clean **`HTTP 401 Unauthorized`** — distinct from the double-slash 405 —
  confirming Phonebook genuinely **is not included on a free/community-tier
  key**, even though the key itself is otherwise valid and working.
- What the free tier *does* include (confirmed via `ixtool.py capabilities`,
  and by actually spending a credit on a live search): `/intelligent/search`
  (+ `/result`, `/terminate`), `/file/preview`, `/file/read`, `/file/view`,
  and `/item/selector/list/human` (+ `/export`).

This tool wraps that confirmed-working surface generically, instead of
being hard-coded to one lookup like the original script was.

## Setup

```bash
uv sync                       # or: pip install -r <(uv export)  /  pip install python-dotenv requests
cp .env.sample .env
# edit .env and set INTELX_TOKEN
```

## Usage

```bash
# See exactly what your key can do (run this first)
uv run ixtool.py capabilities
uv run ixtool.py capabilities --raw     # full raw JSON

# Intelligent Search (the main confirmed-working search endpoint)
uv run ixtool.py search "someone@example.com"
uv run ixtool.py search "example.com" --buckets web.public,leaks.public --maxresults 50
uv run ixtool.py search "example.com" -o results.json

# File operations, once you have a storage/system ID from a search result
uv run ixtool.py preview <sid> --ctype 1 --mediatype 9
uv run ixtool.py view <sid> --ctype 1 --mediatype 9
uv run ixtool.py read <system_id> out.bin --bucket <bucket>

# Human-readable selectors for a document
uv run ixtool.py selectors <document_id>

# Anything else your key has credits for but doesn't have a subcommand yet
uv run ixtool.py raw GET /item/selector/list/export --param id=<id> --param f=0
```

`search` accepts any "strong selector" per Intelligence X's rules: email
address, domain (wildcards like `*.example.com` ok), URL, IPv4/IPv6,
CIDR, phone number, Bitcoin address, MAC address, IPFS hash, UUID,
storage/system ID, simhash, credit card number, IBAN. Generic/soft terms
are rejected by the API.

## Why `intelxapi.py` is vendored

Rather than depend on the broken `intelx` PyPI package, this directory
vendors `intelxapi.py` verbatim (see the header comment in that file). It
only needs `requests`, so it drops in standalone with nothing else from
that package required.

## Error codes

| HTTP status | Meaning here |
|---|---|
| 401 | Invalid credentials |
| 402 | Rate limited / out of credits / endpoint not on your plan |
| 403 | IP blacklisted, or endpoint not enabled for your key |
| 405 | Usually a `base_url` trailing-slash bug on a POST endpoint (see above), not a real permission error |

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

MailHunter is a single-file OSINT CLI that enumerates email addresses for a domain via Intelligence X's phonebook service. Educational/defensive-use tool (see the legal disclaimer in README.md).

## Commands

Dependencies are managed with `uv` (`pyproject.toml` + `uv.lock`, Python 3.14 pinned in `.python-version`).

```bash
uv sync                              # install/refresh .venv
uv run hunt.py -d example.com        # search a domain, print results
uv run hunt.py -d example.com -o out # append results to out.txt
```

There is no test suite, linter, or formatter configured in this repo — don't invent commands for them.

## Environment

`hunt.py` calls `load_dotenv()` at import and reads two variables from `.env`:

- `INTELX_TOKEN` — Intelligence X API key
- `INTELX_URL` — API base, `https://2.intelx.io:443` (was hardcoded until recently; now required or every request URL becomes `None/...`)

Note the inconsistency: `example_search.py` reads `INTELX_KEY` / `INTELX_BASE_URL` instead, and `.env.sample` only lists `INTELX_TOKEN`. Keep `.env.sample` in sync when touching env handling.

## Architecture

`hunt.py` is the whole tool. Everything else is scaffolding: `main.py` is the untouched `uv init` stub, and `example_search.py` is a scratch snippet demonstrating the official `intelx` SDK.

**The tool does not use the `intelx` SDK** despite the import at the top of `hunt.py` (currently unused). It talks to the phonebook endpoints directly with `requests`, using a module-level `headers` dict that impersonates a browser on `https://phonebook.cz` (Origin/Referer/Sec-Fetch-*). Changing those headers can get requests rejected.

The search is a two-call handshake, which explains the odd signatures:

1. `fetch_token(domain)` — POSTs to `/phonebook/search?k=<token>` and returns the **raw response body** (a JSON string containing a search `id`), despite the `-> dict` annotation.
2. `get_query_results(token)` — pulls `["id"]` out of that string and GETs `/phonebook/search/result?k=<token>&id=<id>&limit=1000000`, returning the raw body again.
3. `parse_results(data, args)` — `json.loads`, reads `['selectors'][*]['selectorvalue']`, then either writes to `args.output + '.txt'` (append mode) or prints. With no `-o` and more than 30 results, it drops into an interactive `input()` prompt chain asking whether to save/print — keep that in mind for any non-interactive or scripted use.

HTTP error handling lives in the two fetch functions and is fail-fast via `sys.exit`: 401 invalid credentials, 402 rate/daily limit, 403 blacklisted IP. Any new API call should map the same three codes.

The open TODO (README and end of `hunt.py`) is credential-leak lookup against additional sources.

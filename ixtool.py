#!/usr/bin/env python3
"""
ixtool - a generic CLI for the Intelligence X API.

Covers what a free/community-tier API key actually has credits for, per
`ixtool.py capabilities`: Intelligent Search, file preview/view/read, and
human-readable selector listing. Phonebook search (OSINT email harvesting)
is NOT included on that tier - see README.md for details - so it isn't
wired up here.

Uses the vendored intelxapi.py in this same directory (see the comment at
the top of that file for why it's vendored instead of pip-installed).
"""
import os
import sys
import json
import argparse

from dotenv import load_dotenv
from intelxapi import intelx


def get_client() -> intelx:
    load_dotenv()
    token = os.getenv('INTELX_TOKEN')
    base_url = os.getenv('INTELX_URL')  # optional; SDK defaults to https://2.intelx.io
    if not token:
        sys.exit('❗ INTELX_TOKEN is not set. Copy .env.sample to .env and add your API key.')
    if base_url:
        # intelxapi.py does `self.API_ROOT + url`, so a trailing slash here
        # produces a double slash (e.g. https://host//intelligent/search),
        # which the API rejects with 405 on POST endpoints. Strip it.
        base_url = base_url.rstrip('/')
    return intelx(api_key=token, base_url=base_url)


def exit_for_status(status: int) -> None:
    messages = {
        400: 'Bad request.',
        401: 'Invalid credentials.',
        402: 'Rate limited, out of credits, or this endpoint is not included in your plan.',
        403: 'Forbidden - your IP may be blacklisted, or this endpoint is not enabled for your key.',
        404: 'Not found.',
        405: 'Method not allowed for this endpoint on your plan/key (e.g. Phonebook on a free key).',
    }
    sys.exit(f'❗ Request failed: HTTP {status} - {messages.get(status, "unexpected status.")}')


# --------------------------------------------------------------- capabilities

def cmd_capabilities(client: intelx, args) -> None:
    info = client.GET_CAPABILITIES()
    if isinstance(info, int):
        exit_for_status(info)

    if args.raw:
        print(json.dumps(info, indent=2))
        return

    print("🔑 Enabled paths (credit allocation > 0):")
    for path, meta in info.get('paths', {}).items():
        if meta.get('CreditMax', 0) > 0:
            print(f"  {path:<32} {meta['Credit']}/{meta['CreditMax']} credits"
                  f" (resets every {meta['CreditReset']}h)")
    print(f"\nConcurrent searches: {info.get('searchesactive', 0)}/{info.get('maxconcurrentsearches', 0)}")
    print(f"Full-access buckets: {', '.join(info.get('buckets', [])) or '(none)'}")
    print(f"Preview-only buckets: {', '.join(info.get('preview', [])) or '(none)'}")
    print(f"Redacted buckets: {', '.join(info.get('redacted', [])) or '(none)'}")


# --------------------------------------------------------------- search

def cmd_search(client: intelx, args) -> None:
    buckets = args.buckets.split(',') if args.buckets else []
    result = client.search(
        args.term,
        maxresults=args.maxresults,
        buckets=buckets,
        timeout=args.timeout,
        datefrom=args.datefrom or "",
        dateto=args.dateto or "",
        sort=args.sort,
        media=args.media,
    )
    records = result.get('records', [])
    print(f"\n🔍 {len(records)} record(s) found.")

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as fh:
            json.dump(records, fh, indent=2)
        print(f"✅ Saved to {args.output}")
        return

    for r in records[:args.limit_print]:
        label = r.get('name') or r.get('date') or r.get('systemid')
        print(f"- [{r.get('bucket')}] {label} (xscore={r.get('xscore')}) systemid={r.get('systemid')}")
    if len(records) > args.limit_print:
        print(f"...and {len(records) - args.limit_print} more. Use -o/--output to save all as JSON.")


# --------------------------------------------------------------- file ops

def cmd_preview(client: intelx, args) -> None:
    print(client.FILE_PREVIEW(args.ctype, args.mediatype, args.format, args.sid,
                               bucket=args.bucket, e=args.escape, lines=args.lines))


def cmd_view(client: intelx, args) -> None:
    print(client.FILE_VIEW(args.ctype, args.mediatype, args.sid, bucket=args.bucket, escape=args.escape))


def cmd_read(client: intelx, args) -> None:
    ok = client.FILE_READ(args.id, type=args.type, bucket=args.bucket, filename=args.filename)
    if ok:
        print(f"✅ Saved to {args.filename}")


def cmd_selectors(client: intelx, args) -> None:
    print(json.dumps(client.selectors(args.document), indent=2))


# --------------------------------------------------------------- raw passthrough

def cmd_raw(client: intelx, args) -> None:
    """
    Escape hatch for any endpoint that shows up in `capabilities` but doesn't
    have a dedicated subcommand yet (e.g. /item/selector/list/export).
    """
    params = dict(kv.split('=', 1) for kv in (args.param or []))
    body = json.loads(args.json) if args.json else None
    if args.method.upper() == 'GET':
        r = client._get(args.path, params=params)
    else:
        r = client._post(args.path, json=body)
    print(f"HTTP {r.status_code}")
    try:
        print(json.dumps(r.json(), indent=2))
    except ValueError:
        print(r.text)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog='ixtool', description='Generic CLI for the Intelligence X API')
    sub = parser.add_subparsers(dest='command', required=True)

    p = sub.add_parser('capabilities', help="Show what this API key can actually do")
    p.add_argument('--raw', action='store_true', help='Print the full raw JSON response')
    p.set_defaults(func=cmd_capabilities)

    p = sub.add_parser('search', help='Run an Intelligent Search')
    p.add_argument('term', help='Strong selector: email, domain, IP, URL, hash, etc.')
    p.add_argument('--buckets', help='Comma-separated bucket list (default: all you have access to)')
    p.add_argument('--maxresults', type=int, default=100)
    p.add_argument('--timeout', type=int, default=5)
    p.add_argument('--datefrom', help='e.g. "2020-01-01 00:00:00"')
    p.add_argument('--dateto', help='e.g. "2020-02-02 23:59:59"')
    p.add_argument('--sort', type=int, default=4, help='0=none 1=score-asc 2=score-desc 3=date-asc 4=date-desc')
    p.add_argument('--media', type=int, default=0, help='Media type filter, 0=all (see intelxapi.py docstring)')
    p.add_argument('--limit-print', type=int, default=30, dest='limit_print')
    p.add_argument('-o', '--output', help='Save all records as JSON to this file instead of printing')
    p.set_defaults(func=cmd_search)

    p = sub.add_parser('preview', help="Preview a file's contents by storage ID")
    p.add_argument('sid', help='Storage ID')
    p.add_argument('--ctype', type=int, required=True)
    p.add_argument('--mediatype', type=int, required=True)
    p.add_argument('--format', type=int, default=0, help='0=text 1=picture')
    p.add_argument('--bucket', default='')
    p.add_argument('--escape', type=int, default=0)
    p.add_argument('--lines', type=int, default=8)
    p.set_defaults(func=cmd_preview)

    p = sub.add_parser('view', help="View a file's full contents by storage ID")
    p.add_argument('sid', help='Storage ID')
    p.add_argument('--ctype', type=int, required=True)
    p.add_argument('--mediatype', type=int, required=True)
    p.add_argument('--bucket', default='')
    p.add_argument('--escape', type=int, default=0)
    p.set_defaults(func=cmd_view)

    p = sub.add_parser('read', help='Download a file to disk by system ID')
    p.add_argument('id', help='System ID')
    p.add_argument('filename', help='Local filename to save as')
    p.add_argument('--type', type=int, default=0, help='0=raw binary 1=content-disposition')
    p.add_argument('--bucket', default='', help='Bucket (required by most items)')
    p.set_defaults(func=cmd_read)

    p = sub.add_parser('selectors', help='List human-readable selectors for a document')
    p.add_argument('document', help='Document/system ID')
    p.set_defaults(func=cmd_selectors)

    p = sub.add_parser('raw', help='Advanced: call any endpoint directly')
    p.add_argument('method', choices=['GET', 'POST', 'get', 'post'])
    p.add_argument('path', help='e.g. /item/selector/list/export')
    p.add_argument('--param', action='append', help='key=value, repeatable (GET query params)')
    p.add_argument('--json', help='JSON body string (POST)')
    p.set_defaults(func=cmd_raw)

    return parser


def main() -> None:
    args = build_parser().parse_args()
    client = get_client()
    args.func(client, args)


if __name__ == '__main__':
    main()

from __future__ import annotations

import importlib
import inspect
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path.cwd()
SCRAPER = ROOT / "scraper"
for p in [str(ROOT), str(SCRAPER)]:
    if p not in sys.path:
        sys.path.insert(0, p)

OUT = ROOT / "debug_output" / "investigate_tournament_pipeline"
OUT.mkdir(parents=True, exist_ok=True)


def clean(s: Any) -> str:
    return " ".join(str(s or "").split()).strip()


def norm(s: Any) -> str:
    return clean(s).lower()


def write(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content or "", encoding="utf-8")


def html_to_text(html: str) -> str:
    try:
        from bs4 import BeautifulSoup
        return BeautifulSoup(html or "", "html.parser").get_text("\n")
    except Exception:
        return html or ""


def context_snippets(text: str, query: str, ctx: int = 6) -> list[list[str]]:
    lines = [clean(x) for x in (text or "").splitlines() if clean(x)]
    q = norm(query)
    snippets = []
    for i, line in enumerate(lines):
        if q in norm(line):
            snippets.append(lines[max(0, i - ctx): min(len(lines), i + ctx + 1)])
    return snippets


def call_fetch(fetch_func, player_id: str, max_periods: int | None):
    sig = inspect.signature(fetch_func)
    print(f"fetch_all_periods_html signature: {sig}")

    kwargs = {}
    args = []

    for name, param in sig.parameters.items():
        lname = name.lower()
        if lname in {"player_id", "userid", "user_id"}:
            kwargs[name] = player_id
        elif "max" in lname and "period" in lname and max_periods is not None:
            kwargs[name] = max_periods
        elif lname in {"progress_callback", "callback"}:
            kwargs[name] = None
        elif "headless" in lname:
            kwargs[name] = True
        elif param.default is inspect._empty and param.kind in (param.POSITIONAL_ONLY, param.POSITIONAL_OR_KEYWORD):
            # If required and no mapping found, assume first required positional is player_id.
            if not args and "player" in lname or not args:
                args.append(player_id)
            else:
                raise RuntimeError(f"Required fetch parameter not mapped: {name}")

    try:
        return fetch_func(*args, **kwargs)
    except TypeError as e:
        print(f"First fetch call failed: {e}")
        print("Retry with positional player_id only...")
        if max_periods is not None:
            try:
                return fetch_func(player_id, max_periods=max_periods)
            except Exception as e2:
                print(f"Retry with max_periods failed: {e2}")
        return fetch_func(player_id)


def try_parse_tournaments(scraper_v2, html: str, player_id: str, period_label: str):
    if not hasattr(scraper_v2, "parse_tournament_section"):
        return {"ok": False, "error": "parse_tournament_section not found"}

    func = scraper_v2.parse_tournament_section
    sig = inspect.signature(func)
    print(f"parse_tournament_section signature: {sig}")

    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html or "", "html.parser")
    except Exception:
        soup = html

    # Try a few common call styles.
    attempts = []
    attempts.append((soup, player_id, period_label))
    attempts.append((soup, player_id))
    attempts.append((soup,))
    attempts.append((html, player_id, period_label))
    attempts.append((html, player_id))
    attempts.append((html,))

    for args in attempts:
        try:
            result = func(*args)
            return {"ok": True, "args_len": len(args), "result": result}
        except TypeError:
            continue
        except Exception as e:
            return {"ok": False, "error": repr(e), "args_len": len(args)}

    return {"ok": False, "error": "No compatible call style found", "signature": str(sig)}


def summarize_matches(matches: Any, query: str):
    out = []
    if not isinstance(matches, list):
        return out
    q = norm(query)
    interesting_fields = [
        "partner_name", "opp1_name", "opp2_name", "tournament_name", "competition_name",
        "reeks_name", "score", "result", "round_text", "match_type", "period_label",
    ]
    for m in matches:
        if not isinstance(m, dict):
            continue
        hay = " | ".join(str(m.get(f, "")) for f in interesting_fields)
        if q in norm(hay):
            out.append({k: m.get(k) for k in interesting_fields + ["partner_user_id", "match_date", "tournament_date_start"]})
    return out


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Onderzoek pipeline: fetch HTML -> bevat query -> parser output.")
    ap.add_argument("player_id")
    ap.add_argument("query", help="Bijv. 'Joris Verlee'")
    ap.add_argument("--max-periods", type=int, default=4, help="Aantal recentste periodes ophalen voor diagnose")
    args = ap.parse_args()

    print("=" * 90)
    print("INVESTIGATE TOURNAMENT PIPELINE")
    print(f"ROOT: {ROOT}")
    print(f"PLAYER_ID: {args.player_id}")
    print(f"QUERY: {args.query}")
    print(f"MAX_PERIODS: {args.max_periods}")
    print("=" * 90)

    fpp = importlib.import_module("fetch_period_playwright")
    sv2 = importlib.import_module("scraper_v2")

    if not hasattr(fpp, "fetch_all_periods_html"):
        print("ERROR: fetch_all_periods_html not found in fetch_period_playwright")
        return 2

    periods = call_fetch(fpp.fetch_all_periods_html, args.player_id, args.max_periods)
    print(f"FETCH RESULT TYPE: {type(periods)}")
    if not isinstance(periods, list):
        print(repr(periods)[:1000])
        return 2

    summary = []
    any_query_in_html = False
    any_query_in_parser = False

    for idx, item in enumerate(periods, start=1):
        if not isinstance(item, dict):
            continue
        label = clean(item.get("label") or item.get("period_label") or item.get("period") or f"period_{idx}")
        status = item.get("status")
        html = item.get("html") or ""
        text = html_to_text(html)
        contains = norm(args.query) in norm(text)
        any_query_in_html = any_query_in_html or contains

        safe = re.sub(r"[^A-Za-z0-9_-]+", "_", label)[:90]
        html_path = OUT / f"{idx:02d}_{safe}.html"
        txt_path = OUT / f"{idx:02d}_{safe}.txt"
        write(html_path, html)
        write(txt_path, text)

        snippets = context_snippets(text, args.query)
        if snippets:
            write(OUT / f"{idx:02d}_{safe}_snippets.json", json.dumps(snippets, ensure_ascii=False, indent=2))

        parse_info = try_parse_tournaments(sv2, html, args.player_id, label)
        parsed_count = None
        parsed_hits = []
        parse_error = None
        if parse_info.get("ok"):
            result = parse_info.get("result")
            if isinstance(result, tuple):
                # often parsers return (matches, extra)
                matches = next((x for x in result if isinstance(x, list)), [])
            else:
                matches = result
            parsed_count = len(matches) if isinstance(matches, list) else None
            parsed_hits = summarize_matches(matches, args.query)
            any_query_in_parser = any_query_in_parser or bool(parsed_hits)
            write(OUT / f"{idx:02d}_{safe}_parsed.json", json.dumps(matches, ensure_ascii=False, indent=2, default=str))
        else:
            parse_error = parse_info.get("error")

        row = {
            "idx": idx,
            "label": label,
            "status": status,
            "html_len": len(html),
            "text_len": len(text),
            "query_in_html": contains,
            "snippets": len(snippets),
            "parsed_tournament_count": parsed_count,
            "query_in_parsed_tournaments": bool(parsed_hits),
            "parse_error": parse_error,
            "html_file": str(html_path),
            "text_file": str(txt_path),
        }
        summary.append(row)

        print("-" * 90)
        print(f"{idx}. {label}")
        print(f"status={status} html_len={len(html)} query_in_html={contains} parsed_tournaments={parsed_count} query_in_parsed={bool(parsed_hits)}")
        if snippets:
            print(f"SNIPPETS FILE: {OUT / f'{idx:02d}_{safe}_snippets.json'}")
        if parsed_hits:
            print("PARSED HITS:")
            print(json.dumps(parsed_hits, ensure_ascii=False, indent=2, default=str))
        if parse_error:
            print(f"PARSE ERROR: {parse_error}")

    write(OUT / "summary.json", json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    print("=" * 90)
    print(f"QUERY IN ANY FETCHED HTML: {any_query_in_html}")
    print(f"QUERY IN ANY PARSED TOURNAMENT: {any_query_in_parser}")
    print(f"SUMMARY: {OUT / 'summary.json'}")
    print("=" * 90)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from playwright.sync_api import sync_playwright

BASE = "https://www.tennisenpadelvlaanderen.be"
OUT_DIR = Path("debug_output") / "manual_padel_capture"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def clean(s: str) -> str:
    return " ".join(str(s or "").split()).strip()


def save(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content or "", encoding="utf-8")


def main():
    import argparse

    ap = argparse.ArgumentParser(description="Open TPV pagina zichtbaar. Klik zelf Padel/periode, druk Enter, script dumpt de echte pagina.")
    ap.add_argument("player_id")
    ap.add_argument("query", nargs="?", default="Joris Verlee")
    args = ap.parse_args()

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    url = f"{BASE}/dashboard/resultaten?userId={quote(str(args.player_id))}&tab=padel&tspid=80&tdpid=80&ppid=79&tscid=80&pcid=79"

    print("=" * 90)
    print("MANUAL PADEL CAPTURE")
    print("1) Browser opent nu zichtbaar.")
    print("2) Klik manueel op de Padel-tab.")
    print("3) Kies eventueel de juiste periode waar het tornooi met Joris staat.")
    print("4) Controleer visueel dat Joris Verlee zichtbaar is op de pagina.")
    print("5) Ga terug naar deze PowerShell en druk Enter.")
    print("=" * 90)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=30000)

        input("Druk Enter nadat je Padel/juiste periode manueel hebt geopend en Joris zichtbaar is... ")

        try:
            page.wait_for_load_state("networkidle", timeout=4000)
        except Exception:
            pass

        html = page.content()
        body = page.locator("body").inner_text(timeout=8000)
        found = args.query.lower() in body.lower()

        prefix = f"{args.player_id}_{stamp}"
        html_path = OUT_DIR / f"{prefix}.html"
        txt_path = OUT_DIR / f"{prefix}.txt"
        state_path = OUT_DIR / f"{prefix}_state.json"

        save(html_path, html)
        save(txt_path, body)

        state = {
            "url": page.url,
            "title": page.title(),
            "query": args.query,
            "query_found_in_body": found,
            "html_path": str(html_path),
            "text_path": str(txt_path),
            "body_length": len(body),
            "local_storage": page.evaluate("() => Object.fromEntries(Object.entries(localStorage))"),
            "session_storage": page.evaluate("() => Object.fromEntries(Object.entries(sessionStorage))"),
            "cookies": context.cookies(),
            "links": page.evaluate(r"""
                () => Array.from(document.querySelectorAll('a')).slice(0, 200).map(a => ({
                    text: (a.innerText || a.textContent || '').replace(/\s+/g, ' ').trim(),
                    href: a.href || a.getAttribute('href')
                }))
            """),
            "buttons": page.evaluate(r"""
                () => Array.from(document.querySelectorAll('button,[role=button],input[type=button],input[type=submit]')).slice(0, 200).map(b => ({
                    text: (b.innerText || b.value || b.textContent || '').replace(/\s+/g, ' ').trim(),
                    id: b.id,
                    cls: (b.className || '').toString(),
                    role: b.getAttribute('role'),
                    type: b.getAttribute('type')
                }))
            """),
            "selects": page.evaluate(r"""
                () => Array.from(document.querySelectorAll('select')).map((s, idx) => ({
                    index: idx,
                    id: s.id,
                    name: s.name,
                    value: s.value,
                    selectedText: s.options[s.selectedIndex] ? s.options[s.selectedIndex].text : '',
                    options: Array.from(s.options).map(o => ({value: o.value, text: o.text, selected: o.selected}))
                }))
            """),
        }
        save(state_path, json.dumps(state, ensure_ascii=False, indent=2, default=str))

        print("=" * 90)
        print(f"CURRENT URL: {page.url}")
        print(f"QUERY FOUND IN BODY: {found}")
        print(f"HTML: {html_path}")
        print(f"TEXT: {txt_path}")
        print(f"STATE: {state_path}")
        print("=" * 90)

        browser.close()


if __name__ == "__main__":
    main()

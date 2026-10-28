#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Optional live browser check; start launch.py first. Requires playwright."""
import argparse
from pathlib import Path
import sys
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'vendor/backtalk'))
from backtalk.board import dispatch


def main():
    from playwright.sync_api import sync_playwright
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8794)
    parser.add_argument('--browser', help='Path to an installed Chromium executable')
    args = parser.parse_args()
    base = f'http://127.0.0.1:{args.port}'
    with sync_playwright() as p:
        options = {'headless': True, 'args': ['--no-sandbox', '--enable-webgl',
                   '--use-gl=angle', '--use-angle=swiftshader',
                   '--enable-unsafe-swiftshader']}
        if args.browser:
            options['executable_path'] = args.browser
        browser = p.chromium.launch(**options)
        try:
            page = browser.new_page(viewport={'width': 1280, 'height': 900})
            # Use the host's configured TLS trust and HTTPS proxy for CDN
            # resources. Verification remains enabled; no browser cert bypass.
            def verified_cdn(route):
                with urlopen(route.request.url, timeout=20) as response:
                    route.fulfill(status=response.status, body=response.read(),
                                  headers={'Content-Type': response.headers.get(
                                      'Content-Type', 'application/javascript'),
                                           'Access-Control-Allow-Origin': '*'})
            page.route('https://cdn.jsdelivr.net/**', verified_cdn)
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(base + '/stage.html?camera=0', wait_until='domcontentloaded')
            page.wait_for_function('!document.getElementById("boot")')
            dispatch(['board:show Demo assembly'], base)
            page.wait_for_function(
                'document.querySelector(".modelcard canvas")?.width > 300')
            dispatch(['board:disassemble'], base)
            page.wait_for_function('''async () =>
                (await (await fetch('/state')).json()).items.some(
                    i => i.type === 'model' && i.ex === 1)''')
            dispatch(['board:assemble'], base)
            page.wait_for_function('''async () =>
                (await (await fetch('/state')).json()).items.filter(
                    i => i.type === 'model').every(i => !i.ex)''')
            # Save a visual artifact for checking model appearance.
            output = ROOT / '.runtime'
            output.mkdir(exist_ok=True)
            page.screenshot(path=str(output / 'browser-smoke.png'))
            if errors:
                raise RuntimeError('; '.join(errors))
            print('Passed: model canvas initialized; disassemble and assemble reached the live scene; no JavaScript errors.')
        finally:
            browser.close()


if __name__ == '__main__':
    main()

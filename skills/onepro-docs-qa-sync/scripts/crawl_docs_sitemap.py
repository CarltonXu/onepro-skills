#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import ssl
import time
import urllib.parse
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET


def _fetch(url: str, timeout: int = 60) -> bytes:
    # Prefer per-language header if configured; otherwise fall back to a generic Accept-Language.
    # This helps when the site uses locale negotiation besides path prefix.
    accept_lang = os.environ.get("DOCS_ACCEPT_LANGUAGE", "").strip()
    accept_lang_en = os.environ.get("DOCS_ACCEPT_LANGUAGE_EN", "").strip()
    accept_lang_zh = os.environ.get("DOCS_ACCEPT_LANGUAGE_ZH", "").strip()
    if "/zh/" in url and accept_lang_zh:
        accept_lang = accept_lang_zh
    if "/zh/" not in url and accept_lang_en:
        accept_lang = accept_lang_en
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "onepro-docs-qa-sync/1.0 (+internal-automation)",
            **({"Accept-Language": accept_lang} if accept_lang else {}),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout, context=ssl._create_unverified_context()) as resp:
        return resp.read()

def _fetch_safe(url: str, timeout: int = 60) -> tuple[bytes | None, dict]:
    """
    Return (body, meta). On errors, body is None and meta includes error info.
    """
    try:
        return _fetch(url, timeout=timeout), {"ok": True}
    except urllib.error.HTTPError as e:
        return None, {"ok": False, "error": "http", "code": getattr(e, "code", None), "url": url}
    except urllib.error.URLError as e:
        return None, {"ok": False, "error": "url", "reason": str(getattr(e, "reason", e)), "url": url}
    except Exception as e:
        return None, {"ok": False, "error": "exception", "reason": str(e), "url": url}


def _safe_filename(url: str) -> str:
    h = hashlib.sha1(url.encode("utf-8")).hexdigest()
    return f"{h}.html"


def _parse_sitemap_xml(xml_bytes: bytes) -> tuple[list[str], list[str]]:
    root = ET.fromstring(xml_bytes)
    ns = ""
    if root.tag.startswith("{"):
        ns = root.tag.split("}")[0] + "}"

    urls: list[str] = []
    sitemaps: list[str] = []

    if root.tag == f"{ns}sitemapindex":
        for sm in root.findall(f"{ns}sitemap"):
            loc = sm.findtext(f"{ns}loc")
            if loc:
                sitemaps.append(loc.strip())
    elif root.tag == f"{ns}urlset":
        for u in root.findall(f"{ns}url"):
            loc = u.findtext(f"{ns}loc")
            if loc:
                urls.append(loc.strip())
    else:
        raise ValueError(f"Unknown sitemap root tag: {root.tag}")

    return urls, sitemaps


def _rewrite_url(url: str, host_from: str | None, host_to: str | None, scheme_to: str | None) -> str:
    parsed = urllib.parse.urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return url

    netloc = parsed.netloc
    if host_to:
        if host_from:
            if parsed.netloc == host_from:
                netloc = host_to
        else:
            netloc = host_to

    scheme = parsed.scheme
    if scheme_to:
        scheme = scheme_to

    if scheme == parsed.scheme and netloc == parsed.netloc:
        return url

    return urllib.parse.urlunparse((scheme, netloc, parsed.path, parsed.params, parsed.query, parsed.fragment))

def _strip_lang_prefix(path: str, lang_prefix: str) -> str:
    p = path or "/"
    if not p.startswith("/"):
        p = "/" + p
    needle = f"/{lang_prefix}/"
    if p == f"/{lang_prefix}":
        return "/"
    if p.startswith(needle):
        return "/" + p[len(needle) :]
    return p


def _add_lang_prefix(path: str, lang_prefix: str) -> str:
    p = path or "/"
    if not p.startswith("/"):
        p = "/" + p
    needle = f"/{lang_prefix}/"
    if p == "/":
        return needle
    if p.startswith(needle) or p == f"/{lang_prefix}":
        return p if p.endswith("/") or "." in p.rsplit("/", 1)[-1] else p + "/"
    return f"/{lang_prefix}" + (p if p.startswith("/") else "/" + p)


def _apply_lang_mode(url: str, mode: str, lang_prefix: str = "zh") -> list[str]:
    """
    mode:
      - en: ensure no /zh prefix
      - zh: ensure /zh prefix
      - both: emit both variants
    """
    parsed = urllib.parse.urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return [url]

    en_path = _strip_lang_prefix(parsed.path, lang_prefix=lang_prefix)
    zh_path = _add_lang_prefix(en_path, lang_prefix=lang_prefix)

    def build(pth: str) -> str:
        return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, pth, parsed.params, parsed.query, parsed.fragment))

    if mode == "en":
        return [build(en_path)]
    if mode == "zh":
        return [build(zh_path)]
    # both
    out = [build(en_path), build(zh_path)]
    # Dedup while preserving order.
    seen = set()
    out2 = []
    for u in out:
        if u in seen:
            continue
        seen.add(u)
        out2.append(u)
    return out2


def main() -> int:
    parser = argparse.ArgumentParser(description="Crawl docs pages from a sitemap.xml into a local snapshot.")
    parser.add_argument("--sitemap", required=True, help="Sitemap URL (e.g. https://docs.oneprocloud.com/sitemap.xml)")
    parser.add_argument("--out", required=True, help="Output directory (will be created if missing)")
    parser.add_argument(
        "--rewrite-host-from",
        help="Rewrite sitemap <loc> host when it points to an unreachable domain (e.g. vuepress-theme-hope-docs-demo.netlify.app)",
    )
    parser.add_argument("--rewrite-host-to", help="Target host after rewrite (e.g. docs.oneprocloud.com)")
    parser.add_argument("--rewrite-scheme-to", choices=["http", "https"], help="Rewrite scheme to http/https")
    parser.add_argument(
        "--lang",
        choices=["en", "zh", "both"],
        default="en",
        help="Which language variant to crawl. Assumes Chinese uses '/zh/' prefix and English has no '/zh/'.",
    )
    parser.add_argument("--lang-prefix", default="zh", help="Language path prefix used for Chinese (default: zh)")
    parser.add_argument(
        "--accept-language",
        help="Set DOCS_ACCEPT_LANGUAGE header for this crawl (e.g. en-US,en;q=0.9 or zh-CN,zh;q=0.9).",
    )
    parser.add_argument(
        "--accept-language-en",
        help="Set DOCS_ACCEPT_LANGUAGE_EN (used when URL is NOT under /zh/). Example: en-US,en;q=0.9",
    )
    parser.add_argument(
        "--accept-language-zh",
        help="Set DOCS_ACCEPT_LANGUAGE_ZH (used when URL is under /zh/). Example: zh-CN,zh;q=0.9",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Abort on the first fetch error (default: skip errors and continue).",
    )
    parser.add_argument(
        "--max-errors",
        type=int,
        default=200,
        help="Stop crawling after this many fetch errors (default: 200). Use 0 for unlimited.",
    )
    parser.add_argument("--max-urls", type=int, default=5000, help="Safety limit")
    parser.add_argument("--sleep", type=float, default=0.2, help="Seconds to sleep between page fetches")
    args = parser.parse_args()

    if args.accept_language:
        os.environ["DOCS_ACCEPT_LANGUAGE"] = args.accept_language
    if args.accept_language_en:
        os.environ["DOCS_ACCEPT_LANGUAGE_EN"] = args.accept_language_en
    if args.accept_language_zh:
        os.environ["DOCS_ACCEPT_LANGUAGE_ZH"] = args.accept_language_zh

    out_dir = os.path.abspath(args.out)
    pages_dir = os.path.join(out_dir, "pages")
    os.makedirs(pages_dir, exist_ok=True)

    seen_sitemaps: set[str] = set()
    seen_urls: set[str] = set()
    rewritten_pages = 0
    rewritten_sitemaps = 0
    fetch_errors: list[dict] = []

    sitemap_queue = [_rewrite_url(args.sitemap, args.rewrite_host_from, args.rewrite_host_to, args.rewrite_scheme_to)]
    url_list: list[str] = []

    while sitemap_queue:
        sm_url = sitemap_queue.pop(0)
        if sm_url in seen_sitemaps:
            continue
        seen_sitemaps.add(sm_url)

        xml_bytes, meta = _fetch_safe(sm_url)
        if xml_bytes is None:
            fetch_errors.append({**meta, "kind": "sitemap"})
            print(f"[WARN] sitemap fetch failed: {meta}")
            if args.fail_fast:
                raise RuntimeError(f"sitemap fetch failed: {meta}")
            if args.max_errors and len(fetch_errors) >= args.max_errors:
                break
            continue
        urls, nested = _parse_sitemap_xml(xml_bytes)
        for u in urls:
            u2 = _rewrite_url(u, args.rewrite_host_from, args.rewrite_host_to, args.rewrite_scheme_to)
            if u2 != u:
                rewritten_pages += 1
            for u3 in _apply_lang_mode(u2, mode=args.lang, lang_prefix=args.lang_prefix):
                if u3 not in seen_urls:
                    seen_urls.add(u3)
                    url_list.append(u3)
        for n in nested:
            n2 = _rewrite_url(n, args.rewrite_host_from, args.rewrite_host_to, args.rewrite_scheme_to)
            if n2 != n:
                rewritten_sitemaps += 1
            if n2 not in seen_sitemaps:
                sitemap_queue.append(n2)

        if len(url_list) >= args.max_urls:
            url_list = url_list[: args.max_urls]
            break

    manifest = {
        "version": 1,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "sitemap_url": args.sitemap,
        "rewrite": {
            "host_from": args.rewrite_host_from,
            "host_to": args.rewrite_host_to,
            "scheme_to": args.rewrite_scheme_to,
            "rewritten_pages": rewritten_pages,
            "rewritten_sitemaps": rewritten_sitemaps,
        },
        "lang": {
            "mode": args.lang,
            "prefix": args.lang_prefix,
            "accept_language": os.environ.get("DOCS_ACCEPT_LANGUAGE", ""),
            "accept_language_en": os.environ.get("DOCS_ACCEPT_LANGUAGE_EN", ""),
            "accept_language_zh": os.environ.get("DOCS_ACCEPT_LANGUAGE_ZH", ""),
        },
        "fetch_errors": fetch_errors,
        "items": [],
    }

    for idx, url in enumerate(url_list, start=1):
        fn = _safe_filename(url)
        path = os.path.join(pages_dir, fn)
        if not os.path.exists(path):
            body, meta = _fetch_safe(url)
            if body is None:
                fetch_errors.append({**meta, "kind": "page"})
                # EN<->ZH mapping can legitimately produce 404s; skip and continue.
                code = meta.get("code")
                if code == 404:
                    print(f"[SKIP 404] {url}")
                else:
                    print(f"[WARN] page fetch failed: {meta}")
                if args.fail_fast:
                    raise RuntimeError(f"page fetch failed: {meta}")
                if args.max_errors and len(fetch_errors) >= args.max_errors:
                    break
                continue
            with open(path, "wb") as f:
                f.write(body)
            time.sleep(max(args.sleep, 0.0))

        parsed = urllib.parse.urlparse(url)
        manifest["items"].append(
            {
                "url": url,
                "path": os.path.relpath(path, out_dir),
                "host": parsed.netloc,
                "path_url": parsed.path,
            }
        )

        if idx % 200 == 0:
            print(f"[{idx}/{len(url_list)}] fetched...")

    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"Snapshot written to: {out_dir}")
    print(f"Pages: {len(url_list)}")
    if rewritten_pages or rewritten_sitemaps:
        print(f"Rewrites: pages={rewritten_pages} sitemaps={rewritten_sitemaps}")
    if fetch_errors:
        print(f"Fetch errors: {len(fetch_errors)} (see manifest.json: fetch_errors)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Research connectors with article text, OpenAlex abstracts/open PDFs, and diagnostics."""
import html
import re
import requests
from bs4 import BeautifulSoup

HEADERS = {"User-Agent": "PresentationBot/1.0 (personal educational project)"}
TIMEOUT = 18
SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def clean_text(value):
    return BeautifulSoup(html.unescape(value or ""), "html.parser").get_text(" ", strip=True)


def fetch_page_text(url, max_chars=9000):
    try:
        r = SESSION.get(url, timeout=TIMEOUT)
        r.raise_for_status()
        ctype = r.headers.get("content-type", "").lower()
        if "pdf" in ctype or url.lower().split("?")[0].endswith(".pdf"):
            return ""
        soup = BeautifulSoup(r.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript", "form"]):
            tag.decompose()
        root = soup.find("article") or soup.find("main") or soup.body or soup
        paragraphs = [p.get_text(" ", strip=True) for p in root.find_all(["p", "h2", "h3", "li"])]
        return re.sub(r"\s+", " ", " ".join(p for p in paragraphs if len(p) > 35)).strip()[:max_chars]
    except Exception:
        return ""


def wikipedia_search(query, language="en", limit=4):
    r = SESSION.get(f"https://{language}.wikipedia.org/w/api.php", params={"action":"query","list":"search","srsearch":query,"format":"json","srlimit":limit}, timeout=TIMEOUT)
    r.raise_for_status()
    out = []
    for item in r.json().get("query", {}).get("search", []):
        title = item.get("title", "")
        url = f"https://{language}.wikipedia.org/wiki/" + requests.utils.quote(title.replace(" ", "_"), safe="()_,-")
        text = fetch_page_text(url, 8500) or clean_text(item.get("snippet", ""))
        out.append({"title":title,"url":url,"text":text,"source_type":"encyclopedia","read_status":"full page" if len(text)>1200 else "snippet/partial"})
    return out


def reconstruct_abstract(index):
    if not isinstance(index, dict): return ""
    words = {}
    for word, positions in index.items():
        for position in positions: words[position] = word
    return " ".join(words[pos] for pos in sorted(words))


def fetch_pdf_text(url, max_chars=9000):
    try:
        from pypdf import PdfReader
        from io import BytesIO
        r = SESSION.get(url, timeout=TIMEOUT)
        r.raise_for_status()
        data = r.content
        if len(data)>18_000_000 or not data[:1024].lstrip().startswith(b"%PDF"): return ""
        reader = PdfReader(BytesIO(data))
        chunks=[]
        for page in reader.pages[:25]:
            text=page.extract_text() or ""
            if text: chunks.append(text)
            if sum(map(len,chunks))>=max_chars: break
        return re.sub(r"\s+", " ", " ".join(chunks)).strip()[:max_chars]
    except Exception:
        return ""


def openalex_search(query, limit=5):
    r=SESSION.get("https://api.openalex.org/works",params={"search":query,"per-page":limit,"select":"id,display_name,publication_year,doi,primary_location,abstract_inverted_index,open_access"},timeout=TIMEOUT)
    r.raise_for_status(); out=[]
    for item in r.json().get("results",[]):
        loc=item.get("primary_location") or {}; oa=item.get("open_access") or {}
        pdf_url=oa.get("oa_url") if isinstance(oa,dict) else None
        url=loc.get("landing_page_url") or pdf_url or item.get("doi") or item.get("id")
        if not url: continue
        abstract=reconstruct_abstract(item.get("abstract_inverted_index"))
        full=fetch_pdf_text(pdf_url) if pdf_url else ""
        pieces=[f"Publication year: {item.get('publication_year') or 'not specified'}."]
        if abstract: pieces.append("Abstract: "+abstract)
        if full: pieces.append("Extracted open-access PDF text: "+full)
        text=" ".join(pieces)
        out.append({"title":item.get("display_name") or "Research paper","url":url,"text":text,"source_type":"academic","read_status":"open PDF and abstract" if full else "abstract" if abstract else "metadata only"})
    return out


def wikimedia_images(query, limit=4):
    r=SESSION.get("https://commons.wikimedia.org/w/api.php",params={"action":"query","generator":"search","gsrsearch":f"filetype:bitmap {query}","gsrnamespace":6,"gsrlimit":limit,"prop":"imageinfo","iiprop":"url|extmetadata","iiurlwidth":1400,"format":"json"},timeout=TIMEOUT)
    r.raise_for_status(); out=[]
    for page in (r.json().get("query",{}).get("pages",{}) or {}).values():
        info=(page.get("imageinfo") or [{}])[0]; meta=info.get("extmetadata") or {}
        def val(k): return clean_text((meta.get(k) or {}).get("value", ""))
        image_url=info.get("thumburl") or info.get("url")
        if image_url: out.append({"title":page.get("title","Wikimedia image"),"url":info.get("descriptionurl") or info.get("url") or image_url,"image_url":image_url,"text":f"Creator: {val('Artist') or 'not listed'}. License: {val('LicenseShortName') or 'check source page'}.","license":val("LicenseShortName") or "Check source page","source_type":"image","read_status":"image metadata"})
    return out


def _query_variants(topic):
    """Build progressively broader search queries for long or very specific topics."""
    topic = re.sub(r"\s+", " ", (topic or "").strip())
    variants = []
    if topic:
        variants.append(topic)

    simplified = re.sub(
        r"^(почему|как|что такое|расскажи о|расскажите о|подготовь презентацию о|презентация о|why|how|what is|tell me about|make a presentation about)\s+",
        "",
        topic,
        flags=re.I,
    ).strip(" .,:;!?")
    if simplified and simplified.casefold() not in {v.casefold() for v in variants}:
        variants.append(simplified)

    # A long sentence often returns no results; try its main keywords as a fallback.
    words = re.findall(r"[A-Za-zА-Яа-яЁё0-9][A-Za-zА-Яа-яЁё0-9'-]*", simplified or topic)
    stop_words = {
        "the", "and", "for", "with", "from", "about", "into", "that", "this",
        "что", "как", "для", "или", "это", "при", "над", "под", "его", "её",
        "презентация", "презентацию", "сделай", "создай", "расскажи", "подготовь",
    }
    keywords = [word for word in words if word.casefold() not in stop_words]
    if len(keywords) > 7:
        broad = " ".join(keywords[:7])
        if broad.casefold() not in {v.casefold() for v in variants}:
            variants.append(broad)

    # Avoid duplicate calls while preserving the most specific query first.
    unique = []
    seen = set()
    for variant in variants:
        key = variant.casefold()
        if key and key not in seen:
            seen.add(key)
            unique.append(variant)
    return unique[:3]


def collect_sources(topic, diagnostics=None):
    diagnostics = diagnostics if diagnostics is not None else []
    results = []
    seen = set()
    cyrillic = bool(re.search(r"[А-Яа-яЁё]", topic))
    langs = ("ru", "en") if cyrillic else ("en", "ru")

    for query in _query_variants(topic):
        # Stop querying once enough usable text sources have been collected.
        readable_count = sum(
            1 for item in results
            if item.get("source_type") != "image" and len(item.get("text", "")) >= 250
        )
        if readable_count >= 6:
            break

        connectors = [
            (f"Wikipedia {langs[0]}", lambda q=query: wikipedia_search(q, langs[0], 4)),
            (f"Wikipedia {langs[1]}", lambda q=query: wikipedia_search(q, langs[1], 3)),
            ("OpenAlex", lambda q=query: openalex_search(q, 5)),
            ("Wikimedia Commons", lambda q=query: wikimedia_images(q, 3)),
        ]
        for name, fn in connectors:
            try:
                items = fn()
                diagnostics.append(f"{name} [{query[:70]}]: {len(items)} results")
                for item in items:
                    key = item.get("image_url") if item.get("source_type") == "image" else item.get("url")
                    if key and key not in seen:
                        seen.add(key)
                        results.append(item)
            except Exception as exc:
                diagnostics.append(f"{name} [{query[:45]}]: {type(exc).__name__}: {exc}")

    results.sort(
        key=lambda item: (
            item.get("source_type") == "image",
            len(item.get("text", "")) < 500,
        )
    )
    text_results = [item for item in results if item.get("source_type") != "image"]
    image_results = [item for item in results if item.get("source_type") == "image"]
    # Keep image results alongside evidence text instead of truncating them away.
    return text_results[:12] + image_results[:6]

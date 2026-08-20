#!/usr/bin/env python3
"""
Build Public Pages — generates rich, human-readable, AI-crawlable HTML pages
from JSON schema files in this repository.
"""
import sys, os, json, re, glob
from urllib.parse import quote_plus
from datetime import datetime, date

# ═══════════════════════════════════════
# Utilities
# ═══════════════════════════════════════
def esc(s):
    if not isinstance(s, str): return ''
    return s.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace('"','&quot;')

def slugify(text):
    if not text: return 'item'
    text = re.sub(r'[^a-zA-Z0-9\s-]', '', str(text))
    text = re.sub(r'[\s]+', '-', text.strip().lower())
    return text or 'item'

def load_json(pattern):
    files = sorted(glob.glob(pattern, recursive=True))
    results = []
    for fp in files:
        try:
            with open(fp, encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    results.extend(data)
                else:
                    results.append(data)
        except Exception:
            pass
    return results

def count_files(directory):
    if not os.path.isdir(directory): return 0
    return len(glob.glob(os.path.join(directory, '**', '*.json'), recursive=True))

def _first(*vals):
    for v in vals:
        if isinstance(v, str) and v.strip(): return v.strip()
        if isinstance(v, (int, float)): return str(v)
    return ''

def _as_list(val):
    if val is None: return []
    if isinstance(val, list): return [str(x).strip() for x in val if str(x).strip()]
    if isinstance(val, str) and val.strip(): return [s.strip() for s in val.split(',') if s.strip()]
    return []

def _title_from_filename(path):
    base = os.path.splitext(os.path.basename(path))[0]
    return base.replace('-', ' ').replace('_', ' ').strip().title()

def _is_placeholder(text):
    if not isinstance(text, str) or not text.strip(): return True
    t = text.strip().lower()
    return t in {'service','unnamed service','untitled','n/a','na','tbd'} or bool(re.fullmatch(r'(service|item|entry)\s*\d+', t))

def _guess_title(obj, filename, kind=''):
    if not isinstance(obj, dict): return _title_from_filename(filename)
    keys = {'service':['title','service_name','name','headline','offering','practice_area','label','category'],
            'award':['title','award_name','name','certification_name','certification']
           }.get(kind, ['title','name','headline','label'])
    candidate = _first(*(obj.get(k) for k in keys))
    if _is_placeholder(candidate): return _title_from_filename(filename)
    return candidate

def _guess_desc(obj):
    return _first(obj.get('description'), obj.get('summary'), obj.get('details'), obj.get('body'), obj.get('content'), obj.get('answer'))

def _guess_price(obj):
    return _first(obj.get('price'), obj.get('price_range'), obj.get('starting_price'), obj.get('cost'), obj.get('fee')) or 'Contact for pricing'

def _bullets(obj):
    feats = _as_list(obj.get('features') or obj.get('benefits') or obj.get('highlights'))
    specs = _as_list(obj.get('specialties') or obj.get('capabilities'))
    areas = _as_list(obj.get('service_areas') or obj.get('areas'))
    out = (feats[:3] or specs[:3])
    if areas: out.append('Service areas: ' + ', '.join(areas[:5]))
    seen = set()
    return [b for b in out if b.lower() not in seen and not seen.add(b.lower())][:4]

# ═══════════════════════════════════════
# Config
# ═══════════════════════════════════════
TODAY = date.today().isoformat()
YEAR = date.today().year

manifest = {}
# Prefer the canonical publishing-manifest.json; fall back to legacy manifest.json.
for _mf in ('data/publishing-manifest.json', 'publishing-manifest.json', 'manifest.json'):
    if os.path.exists(_mf):
        with open(_mf) as f:
            manifest = json.load(f)
        break

_client = manifest.get('client', {}) if isinstance(manifest.get('client'), dict) else {}
BIZ = _client.get('name') or manifest.get('businessName', 'Just Work Comp Law')
WEBSITE = _client.get('canonicalUrl') or manifest.get('canonicalUrl', '') or manifest.get('websiteUrl', 'https://justworkcomplaw.com/')
PHONE = _client.get('phone') or manifest.get('phone', '')
EMAIL = _client.get('email') or manifest.get('email', '')
MANIFEST_LOCATIONS = _client.get('locations') or manifest.get('locations', []) or []
SERVICES = _client.get('services') or manifest.get('services', [])
CITIES = _client.get('cities') or manifest.get('cities', [])
VERTICAL = (_client.get('vertical') or manifest.get('vertical') or 'legal').lower()
PAGES_URL = (_client.get('pagesUrl') or manifest.get('pagesUrl') or 'https://aiovisibilityhub.github.io/just-work-comp-law-ai-schemas-8s40/') or (WEBSITE or '')
if PAGES_URL and not PAGES_URL.endswith('/'): PAGES_URL += '/'

def title_case(s):
    return ' '.join(w.capitalize() for w in s.split()) if s else ''

# ─── Vertical-aware terminology sanitizer ───
# When the business vertical isn't legal, strip attorney/lawyer/legal
# terminology so non-legal sites read as generic business sites.
_LEGAL_TERM_MAP = [
    (re.compile(r'\bAttorneys?\b'), 'Team Member'),
    (re.compile(r'\bLawyers?\b'), 'Team Member'),
    (re.compile(r'\battorneys?\b'), 'team member'),
    (re.compile(r'\blawyers?\b'), 'team member'),
    (re.compile(r'\blegal help\b', re.I), 'services'),
    (re.compile(r'\blegal services\b', re.I), 'services'),
    (re.compile(r'\blegal team\b', re.I), 'team'),
    (re.compile(r'\blegal advice\b', re.I), 'guidance'),
    (re.compile(r'\blegal representation\b', re.I), 'professional representation'),
    (re.compile(r'\bLaw Firm\b'), 'Business'),
    (re.compile(r'\blaw firm\b', re.I), 'business'),
    (re.compile(r'\bcase types?\b', re.I), 'services'),
    (re.compile(r'\bpractice areas?\b', re.I), 'service areas'),
]

def sanitize_vertical(text):
    if VERTICAL == 'legal':
        return text
    out = text
    for pattern, repl in _LEGAL_TERM_MAP:
        out = pattern.sub(repl, out)
    # Fix plural after substitution
    out = re.sub(r'(\d+)\s+team member\b', r'\1 team members', out, flags=re.I)
    out = re.sub(r'our team member\b', 'our team members', out, flags=re.I)
    return out

# ═══════════════════════════════════════
# HTML Shell
# ═══════════════════════════════════════
PAGES = [('index.html','Home'),('about.html','About'),('services.html','Services'),
         ('reviews.html','Reviews'),('faqs.html','FAQs'),('articles.html','Articles'),
         ('web-pages.html','Web Pages'),
         ('awards.html','Awards'),('contact.html','Contact')]

# Track which pages will be built (pre-scanned for data)
BUILT_PAGES = set()

def _prescan_pages():
    """Pre-scan to determine which pages have data before building any."""
    BUILT_PAGES.add('index.html')  # always built
    BUILT_PAGES.add('about.html')  # always built (has fallback content)
    if os.path.isdir('faqs') and glob.glob('faqs/**/*.json', recursive=True):
        BUILT_PAGES.add('faqs.html')
    if os.path.isdir('help') and (glob.glob('help/**/*.json', recursive=True) or glob.glob('help/**/*.md', recursive=True)):
        BUILT_PAGES.add('articles.html')
    if os.path.isdir('webpages') and (glob.glob('webpages/**/*.json', recursive=True) or glob.glob('webpages/**/*.html', recursive=True)):
        BUILT_PAGES.add('web-pages.html')

    BUILT_PAGES.add('contact.html')  # always built (has fallback content)
    if os.path.isdir('services') and glob.glob('services/**/*.json', recursive=True):
        BUILT_PAGES.add('services.html')
    if os.path.isdir('reviews') and glob.glob('reviews/*.json'):
        BUILT_PAGES.add('reviews.html')
    if os.path.isdir('awards') and glob.glob('awards/*.json'):
        BUILT_PAGES.add('awards.html')

def nav(current):
    items = []
    for fn, lb in PAGES:
        if fn not in BUILT_PAGES:
            continue
        if fn == current:
            items.append(f'<li><strong>{esc(lb)}</strong></li>')
        else:
            items.append(f'<li><a href="{fn}" style="color:white;text-decoration:none;">{esc(lb)}</a></li>')
    return '<nav style="background:#2c3e50;padding:1rem;margin-bottom:2rem;"><ul style="list-style:none;display:flex;gap:2rem;margin:0;padding:0;flex-wrap:wrap;justify-content:center;">' + ''.join(items) + '</ul></nav>'

SPEAKABLE = {
    '@type': 'SpeakableSpecification',
    'cssSelector': ['h1', '.section p', '.card p', '.speakable'],
    'xpath': ['/html/head/title', '/html/body//h1'],
}

def page_url(filename):
    base = PAGES_URL if PAGES_URL.endswith('/') else PAGES_URL + '/'
    return base + ('' if filename == 'index.html' else filename)

def breadcrumb_ld(filename, title):
    base = PAGES_URL if PAGES_URL.endswith('/') else PAGES_URL + '/'
    items = [{'@type': 'ListItem', 'position': 1, 'name': 'Home', 'item': base}]
    if filename != 'index.html':
        items.append({'@type': 'ListItem', 'position': 2, 'name': title, 'item': page_url(filename)})
    return {'@context': 'https://schema.org', '@type': 'BreadcrumbList', 'itemListElement': items}

def webpage_ld(filename, title, desc):
    url = page_url(filename)
    return {
        '@context': 'https://schema.org',
        '@type': 'WebPage',
        '@id': url + '#webpage',
        'url': url,
        'name': title,
        'description': desc,
        'inLanguage': 'en-US',
        'datePublished': TODAY,
        'dateModified': TODAY,
        'isPartOf': {'@type': 'WebSite', 'name': BIZ, 'url': WEBSITE or url},
        'publisher': {'@type': 'Organization', 'name': BIZ, 'url': WEBSITE or url},
        'speakable': SPEAKABLE,
    }

def jsonld_block(obj):
    return '<script type="application/ld+json">\n' + json.dumps(obj, indent=2, ensure_ascii=False) + '\n</script>'

def page_shell(title, content, desc='', extra_ld=None, filename='index.html'):
    if not desc: desc = f'{BIZ} — {title}'
    url = page_url(filename)
    canonical = WEBSITE or url
    blocks = [webpage_ld(filename, title, desc), breadcrumb_ld(filename, title)]
    for extra in (extra_ld or []):
        if extra: blocks.append(extra)
    ld_html = '\n'.join(jsonld_block(b) for b in blocks)
    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<meta name="robots" content="index, follow, max-snippet:-1, max-image-preview:large, max-video-preview:-1">
<meta name="author" content="{esc(BIZ)}">
<link rel="canonical" href="{esc(canonical)}" />
<link rel="alternate" type="text/html" href="{esc(url)}" />
<link rel="sitemap" type="application/xml" href="{esc(PAGES_URL)}ai-sitemap.xml" />
<meta property="og:title" content="{esc(title)}" />
<meta property="og:description" content="{esc(desc)}" />
<meta property="og:type" content="website" />
<meta property="og:url" content="{esc(canonical)}" />
<meta property="og:site_name" content="{esc(BIZ)}" />
<meta property="og:locale" content="en_US" />
<meta name="twitter:card" content="summary_large_image" />
<meta name="twitter:title" content="{esc(title)}" />
<meta name="twitter:description" content="{esc(desc)}" />
<meta name="dcterms.modified" content="{TODAY}" />
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,sans-serif;max-width:900px;margin:0 auto;padding:20px;line-height:1.7}}
h1,h2,h3{{color:#2c3e50}}
a{{color:#3498db;text-decoration:none}}
a:hover{{text-decoration:underline}}
.page-header{{background:#ecf0f1;padding:2rem;border-radius:8px;margin-bottom:2rem;text-align:center}}
.card{{border:1px solid #eee;padding:1.5rem;border-radius:8px;margin:2rem 0}}
.badge{{background:#3498db;color:white;padding:0.25rem 0.5rem;border-radius:4px;font-size:0.9em}}
address{{font-style:normal;margin:1rem 0;padding:1rem;background:#f8f8f8;border-left:3px solid #333}}
blockquote{{border-left:3px solid #3498db;margin:0;padding:.5rem 1rem;background:#f0f4f8;font-style:italic}}
.breadcrumbs{{font-size:.9rem;color:#7f8c8d;margin-bottom:1rem}}
</style>
{ld_html}
</head><body>
{nav(current_page)}
<nav class="breadcrumbs" aria-label="Breadcrumb"><a href="index.html">Home</a>{'' if filename == 'index.html' else ' &rsaquo; <span>' + esc(title) + '</span>'}</nav>
<div class="page-header"><h1>{esc(title)}</h1></div>
{content}
<footer style="margin-top:4rem;padding-top:2rem;border-top:1px solid #eee;text-align:center;color:#7f8c8d;">
<p>&copy; {YEAR} {esc(BIZ)} &mdash; AI Schema Repository &middot; Last updated: {TODAY}</p>
</footer>
</body></html>"""

def org_ld():
    org = {
        '@context': 'https://schema.org',
        '@type': 'Organization',
        'name': BIZ,
        'url': WEBSITE or PAGES_URL,
    }
    if PHONE: org['telephone'] = PHONE
    if EMAIL: org['email'] = EMAIL
    if SERVICES: org['knowsAbout'] = [s for s in SERVICES if s][:30]
    if CITIES: org['areaServed'] = [{'@type': 'Place', 'name': c} for c in CITIES if c][:30]
    addrs = []
    for l in (MANIFEST_LOCATIONS or []):
        if not isinstance(l, dict): continue
        a = l.get('address') if isinstance(l.get('address'), dict) else None
        if a: addrs.append({'@type': 'PostalAddress', **{k: v for k, v in a.items() if isinstance(v, str)}})
    if addrs: org['address'] = addrs if len(addrs) > 1 else addrs[0]
    return org

def faq_ld(items):
    return {
        '@context': 'https://schema.org',
        '@type': 'FAQPage',
        'speakable': SPEAKABLE,
        'mainEntity': [
            {'@type': 'Question', 'name': q, 'acceptedAnswer': {'@type': 'Answer', 'text': a or ''}}
            for q, a in items[:200]
        ],
    }

def item_list_ld(name, names):
    return {
        '@context': 'https://schema.org',
        '@type': 'ItemList',
        'name': name,
        'numberOfItems': len(names),
        'itemListElement': [
            {'@type': 'ListItem', 'position': i + 1, 'name': n}
            for i, n in enumerate(names[:200])
        ],
    }

def write_page(filename, title, content, desc='', extra_ld=None):
    global current_page
    current_page = filename
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(sanitize_vertical(page_shell(title, content, desc, extra_ld, filename)))
    print(f'  \u2705 {filename}')


current_page = 'index.html'

# ═══════════════════════════════════════
# Page Builders
# ═══════════════════════════════════════

def build_index():
    # Only link to pages that were actually built
    all_sections = [
        ('About Us', 'about.html'),
        ('Our Services', 'services.html'),
        ('Reviews', 'reviews.html'),
        ('FAQs', 'faqs.html'),
        ('Articles', 'articles.html'),
        ('Web Pages', 'web-pages.html'),
        ('Awards', 'awards.html'),
        ('Contact Us', 'contact.html'),
    ]
    sections = [(name, url) for name, url in all_sections if url in BUILT_PAGES]
    quick_links = ''.join(
        f'<li style="margin:0.5rem 0;"><a href="{url}" style="font-size:1.1em;font-weight:500;">{esc(name)}</a></li>'
        for name, url in sections
    )

    repo_slug = os.getenv('GITHUB_REPOSITORY', '')
    base_url = f'https://raw.githubusercontent.com/{repo_slug}/main' if repo_slug else ''

    grouped = []
    schema_dirs = ['faqs','help','services','webpages','awards','case-studies','locations','organization','press','products','reviews','team','lawyers','qna','research-source','research-asking','research-gap']
    for directory in schema_dirs:
        if not os.path.isdir(directory):
            continue
        links = []
        for root, dirs, files in os.walk(directory):
            for fname in sorted(files):
                if not fname.endswith(('.json','.html','.md','.yaml','.yml')):
                    continue
                filepath = os.path.join(root, fname).replace('\\','/')
                href = f'{base_url}/{filepath}' if base_url else filepath
                links.append(f'<li><a href="{href}" target="_blank">{esc(filepath)}</a></li>')
        if links:
            grouped.append(f'<details class="card"><summary><strong>{esc(directory)}/</strong> ({len(links)} files)</summary><ul>{"".join(links)}</ul></details>')

    content = f"""
<p>Welcome to this public resource center for {esc(BIZ)}. These pages are designed to be readable for people and easy for AI systems and search engines to crawl.</p>
<h2>&#x1F680; Quick Navigation</h2>
<ul style="list-style:none;padding:0;">{quick_links}</ul>
<h2 id="files">&#x1F4C1; Browse All Schema Files</h2>
<p>Each section below links directly to the generated repository files.</p>
{''.join(grouped) if grouped else '<p>No schema files were found.</p>'}
"""
    write_page('index.html', f'Welcome to {BIZ}', content, f'{BIZ}: public resource center with crawlable schema files and readable HTML pages.', [org_ld()])

def build_about():
    parts = []
    # Organization info
    for org in load_json('organization/*.json'):
        dl = '<dl>'
        for key, label in [('legalName','Name'),('foundingDate','Founded'),('slogan','Slogan'),('description','Description')]:
            v = org.get(key)
            if v: dl += f'<dt>{label}</dt><dd>{esc(str(v))}</dd>'
        emp = org.get('numberOfEmployees',{})
        if isinstance(emp, dict) and emp.get('value'):
            dl += f'<dt>Employees</dt><dd>{esc(str(emp["value"]))}</dd>'
        dl += '</dl>'
        parts.append(f'<div class="card"><h2>Organization</h2>{dl}</div>')
        # Mission / Vision
        mission = _first(org.get('mission'))
        vision = _first(org.get('vision'))
        if mission: parts.append(f'<h2>Our Mission</h2><p>{esc(mission)}</p>')
        if vision: parts.append(f'<h2>Our Vision</h2><p>{esc(vision)}</p>')
        # Logo
        logo = _first(org.get('logo_url'), org.get('logo'))
        if logo: parts.insert(0, f'<img src="{esc(logo)}" alt="{esc(BIZ)}" style="max-height:120px;margin-bottom:2rem;">')

    # Facts at a Glance
    service_count = count_files('services')
    review_ratings = []
    for r in load_json('reviews/*.json'):
        try:
            rv = float(r.get('rating') or r.get('reviewRating',{}).get('ratingValue',0))
            if rv > 0: review_ratings.append(rv)
        except Exception: pass
    avg = (sum(review_ratings)/len(review_ratings)) if review_ratings else None
    facts = [f'<li><strong>Services offered:</strong> {service_count}</li>']
    if avg is not None:
        stars = '\u2605' * int(round(avg)) + '\u2606' * (5 - int(round(avg)))
        facts.append(f'<li><strong>Average rating:</strong> {avg:.1f} {stars}</li>')
    if CITIES:
        facts.append(f'<li><strong>Service areas:</strong> {esc(", ".join(CITIES[:8]))}</li>')
    parts.append('<div class="card"><h2>Facts at a Glance</h2><ul>' + ''.join(facts) + '</ul></div>')

    # Team
    team_cards = []
    for p in load_json('team/*.json'):
        name = _first(p.get('name'), p.get('givenName')) or 'Team Member'
        title = _first(p.get('jobTitle'), p.get('roleName'))
        desc = _first(p.get('description'))
        card = f'<div class="card"><h3>{esc(name)}</h3>'
        if title: card += f'<p><strong>{esc(title)}</strong></p>'
        if desc: card += f'<p>{esc(desc)}</p>'
        card += '</div>'
        team_cards.append(card)
    if team_cards:
        parts.append('<h2>Team</h2>' + ''.join(team_cards))

    # Awards
    awards = load_json('awards/*.json')
    if awards:
        items = []
        for a in awards:
            name = _first(a.get('name'))
            yr = (_first(a.get('dateCreated'), a.get('datePublished')) or '')[:4]
            items.append(f'<li><strong>{esc(name)}</strong>{f" ({yr})" if yr else ""}</li>')
        parts.append('<h2>Awards &amp; Recognition</h2><ul>' + ''.join(items) + '</ul>')

    # Case Studies
    cases = load_json('case-studies/*.json')
    if cases:
        cards = []
        for c in cases:
            t = _first(c.get('headline'), c.get('name'))
            d = _first(c.get('description'))
            cards.append(f'<div class="card"><h3>{esc(t)}</h3><p>{esc(d)}</p></div>')
        parts.append('<h2>Case Studies</h2>' + ''.join(cards))

    # Locations
    locs = load_json('locations/*.json')
    if locs:
        addrs = []
        for l in locs:
            name = _first(l.get('name'))
            addr = l.get('address',{})
            if isinstance(addr, dict):
                street = _first(addr.get('streetAddress'))
                city = _first(addr.get('addressLocality'))
                state = _first(addr.get('addressRegion'))
            else:
                street = city = state = ''
            phone = _first(l.get('telephone'))
            a = f'<address><strong>{esc(name)}</strong><br>'
            if street: a += f'{esc(street)}, '
            if city: a += esc(city)
            if state: a += f', {esc(state)}'
            if phone: a += f'<br>Phone: {esc(phone)}'
            a += '</address>'
            addrs.append(a)
        parts.append('<h2>Locations</h2>' + ''.join(addrs))

    parts.append(f'<div class="card"><h2>Ready to Talk?</h2><p>Have a project in mind or need guidance? We\u2019re here to help.</p><p><a href="contact.html">Contact us</a> to get started.</p></div>')

    # Title: keyword - city — business (no "About")
    keyword = SERVICES[0] if SERVICES else ''
    city = CITIES[0] if CITIES else ''
    title_parts = [p for p in [title_case(keyword), title_case(city)] if p]
    about_title = (' - '.join(title_parts) + ' \u2014 ' + BIZ) if title_parts else BIZ

    if not parts:
        parts.append(f'<p>{esc(BIZ)} is a professional firm serving our community with high-quality services and a client-first approach.</p>')

    write_page('about.html', about_title, ''.join(parts), f'{BIZ}: team, locations, awards, and organization details.', [org_ld()])

def build_services():
    cards = []
    files_list = glob.glob('services/**/*.json', recursive=True) or glob.glob('services/*.json')
    for filepath in sorted(files_list):
        for svc in load_json(filepath) if not filepath.endswith('.json') else []:
            pass
    # Re-load properly
    all_svcs = load_json('services/**/*.json') or load_json('services/*.json')
    for svc in all_svcs:
        if not isinstance(svc, dict): continue
        title = _guess_title(svc, '', kind='service')
        description = _guess_desc(svc) or ''
        price = _guess_price(svc)
        featured = bool(svc.get('featured') or svc.get('is_featured'))
        slug = svc.get('slug') or slugify(title)
        badge = '<span class="badge">Featured</span>' if featured else ''
        bullet_items = _bullets(svc)
        bullet_html = ('<ul>' + ''.join(f'<li>{esc(b)}</li>' for b in bullet_items) + '</ul>') if bullet_items else ''

        cards.append(f"""<div class="card" id="{esc(slug)}">
<h2>{esc(title)} {badge}</h2>
{'<p>' + esc(description) + '</p>' if description else ''}
{bullet_html}
<p><strong>Starting at:</strong> {esc(price)}</p>
<a href="#{slug}">\U0001f517 Permalink</a>
</div>""")

    if not cards:
        print(f'  \u23ed services.html skipped (no services data)')
        return
    content = ''.join(cards)
    write_page('services.html', f'Our Services', content, f'Services offered by {BIZ}.', [item_list_ld('Services', [t for t in ([_guess_title(s2, '', kind='service') for s2 in all_svcs if isinstance(s2, dict)] or SERVICES) if t]), org_ld()])

def build_testimonials():
    cards = []
    for r in load_json('reviews/*.json'):
        if not isinstance(r, dict): continue
        text = _first(r.get('reviewBody'), r.get('review_body'), r.get('quote'), r.get('description'))
        if not text: continue
        author = r.get('author', {})
        if isinstance(author, dict): author = _first(author.get('name'))
        elif not isinstance(author, str): author = ''
        author = author or _first(r.get('customer_name')) or 'Anonymous'
        rating_obj = r.get('reviewRating', {})
        if isinstance(rating_obj, dict):
            rating_val = rating_obj.get('ratingValue')
        else:
            rating_val = r.get('rating')
        try:
            rating = max(1, min(5, int(rating_val)))
        except Exception:
            rating = 5
        stars = '\u2605' * rating + '\u2606' * (5 - rating)
        date_str = _first(r.get('date'), r.get('datePublished'))

        cards.append(f"""<blockquote class="card">
<p>"{esc(text)}"</p>
<footer style="margin-top:1rem;font-style:normal;">
\u2014 {esc(author)}{f'<br><small>{esc(date_str)}</small>' if date_str else ''}
</footer>
<div style="margin-top:0.5rem;">{stars}</div>
</blockquote>""")

    if not cards:
        print(f'  \u23ed reviews.html skipped (no reviews data)')
        return
    content = ''.join(cards)
    write_page('reviews.html', 'Reviews', content, f'Client reviews for {BIZ}.')

def build_faqs():
    items = []
    for faq in load_json('faqs/**/*.json') or load_json('faqs/*.json'):
        if not isinstance(faq, dict): continue
        # Handle FAQPage schema with mainEntity
        main = faq.get('mainEntity', [])
        if main:
            for item in main:
                q = _first(item.get('name'))
                a = _first((item.get('acceptedAnswer') or {}).get('text'))
                if q: items.append((q, a))
        else:
            q = _first(faq.get('question'), faq.get('name'))
            a = _first(faq.get('answer'), faq.get('acceptedAnswer'))
            if q: items.append((q, a or ''))

    content_parts = []
    for q, a in items:
        content_parts.append(f'<div class="card"><h3 style="margin:0 0 0.5rem 0;">{esc(q)}</h3><p>{esc(a)}</p></div>')

    if not content_parts:
        print(f'  \u23ed faqs.html skipped (no FAQ data)')
        return
    content = ''.join(content_parts)
    write_page('faqs.html', 'Frequently Asked Questions', f'<p>{len(items)} questions about {esc(BIZ)}.</p>' + content, f'Frequently asked questions about {BIZ}.', [faq_ld(items), org_ld()])

def build_help():

    cards = []
    # Try markdown files first
    help_dir = 'help'
    if os.path.isdir(help_dir):
        md_files = [f for f in os.listdir(help_dir) if f.endswith('.md')]
        if md_files:
            for file in sorted(md_files):
                filepath = os.path.join(help_dir, file)
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                title = None
                body_lines = []
                in_fm = False
                fm_done = False
                for line in content.splitlines():
                    if line.strip() == '---' and not fm_done:
                        if not in_fm: in_fm = True
                        else: in_fm = False; fm_done = True
                        continue
                    if in_fm and not fm_done:
                        if line.lower().startswith('title:'): title = line.split(':',1)[1].strip()
                    else:
                        body_lines.append(line)
                if not title: title = file.replace('.md','').replace('-',' ').replace('_',' ').title()
                html_lines = []
                for line in body_lines:
                    if line.startswith('## '): html_lines.append(f'<h3>{esc(line[3:])}</h3>')
                    elif line.startswith('# '): html_lines.append(f'<h2>{esc(line[2:])}</h2>')
                    elif line.startswith(('- ','* ')): html_lines.append(f'<p>\u2022 {esc(line[2:])}</p>')
                    elif line.strip(): html_lines.append(f'<p>{esc(line)}</p>')
                article_id = 'article-' + re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')[:72]
                cards.append(f'<article class="card" id="{esc(article_id)}"><h2><a href="#{esc(article_id)}">{esc(title)}</a></h2>{"".join(html_lines)}<p><a href="#{esc(article_id)}">Article link</a></p></article>')

    # Also try JSON
    for h in load_json('help/**/*.json') or load_json('help/*.json'):
        if not isinstance(h, dict): continue
        title = _first(h.get('headline'), h.get('name'))
        desc = _first(h.get('articleBody'), h.get('text'), h.get('description'))
        if not title: continue
        article_id = 'article-' + re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')[:72]
        cards.append(f'<article class="card" id="{esc(article_id)}"><h2><a href="#{esc(article_id)}">{esc(title)}</a></h2><p>{esc(desc)}</p><p><a href="#{esc(article_id)}">Article link</a></p></article>')

    if not cards:
        print(f'  \u23ed articles.html skipped (no articles data)')
        return
    content = ''.join(cards)
    write_page('articles.html', 'Articles', f'<p>{len(cards)} articles available.</p>' + content, f'Articles and guides from {BIZ}.')

def build_webpages():
    cards = []
    for root, dirs, files in os.walk('webpages') if os.path.isdir('webpages') else []:
        for filename in sorted(files):
            if not filename.endswith(('.json', '.html')):
                continue
            source_path = os.path.join(root, filename).replace('\\', '/')
            html_path = source_path if filename.endswith('.html') else source_path[:-5] + '.html'
            title = filename.rsplit('.', 1)[0].replace('-', ' ').replace('_', ' ').title()
            desc = ''
            body = ''
            services = []
            places = []
            if filename.endswith('.json'):
                try:
                    with open(source_path, 'r', encoding='utf-8') as f:
                        item = json.load(f)
                    title = _first(item.get('name'), item.get('headline')) or title
                    desc = _first(item.get('description'), item.get('abstract'))
                    main = item.get('mainContentOfPage') or {}
                    body = main.get('text') or item.get('articleBody') or item.get('text') or ''
                    for m in (item.get('mentions') or []):
                        nm = re.sub(r'(?:\s*Base)+$', '', str(m.get('name') or '')).strip()
                        if not nm:
                            continue
                        if m.get('@type') == 'Service':
                            if nm not in services: services.append(nm)
                        else:
                            if nm not in places: places.append(nm)
                except Exception:
                    pass
            paras = ''.join(
                f'<p>{esc(re.sub(r"(?:\s*Base)+$", "", p.strip()))}</p>'
                for p in re.split(r'\n{2,}', body or desc or '') if p.strip()
            )
            extra = ''
            if services:
                extra += f'<p><strong>Related services:</strong> {esc(", ".join(services))}</p>'
            if places:
                extra += f'<p><strong>Locations served:</strong> {esc(", ".join(places))}</p>'
            lead = f'<p><strong>{esc(desc)}</strong></p>' if desc and desc != body else ''
            cards.append(
                f'<article class="card"><h2><a href="{esc(html_path)}">{esc(title)}</a></h2>'
                f'{lead}{paras}{extra}'
                f'<p><a href="{esc(html_path)}">Read full page &rarr;</a></p></article>'
            )
    if not cards:
        print(f'  \u23ed web-pages.html skipped (no webpage data)')
        return
    write_page('web-pages.html', 'Web Pages', f'<p>{len(cards)} topical web pages available.</p>' + ''.join(cards), f'Topical web pages from {BIZ}.')





def build_awards():
    cards = []
    for a in load_json('awards/*.json'):
        if not isinstance(a, dict): continue
        title = _guess_title(a, '', kind='award')
        desc = _guess_desc(a)
        cards.append(f'<div class="card"><h2>{esc(title)}</h2>{"<p>" + esc(desc) + "</p>" if desc else ""}</div>')
    if not cards:
        print(f'  \u23ed awards.html skipped (no awards data)')
        return
    content = ''.join(cards)
    write_page('awards.html', 'Awards & Recognition', content, f'Awards and recognition for {BIZ}.')

def build_contact():
    items = []
    first_phone = first_email = ''
    locs = load_json('locations/*.json')
    if isinstance(MANIFEST_LOCATIONS, list):
        for ml in MANIFEST_LOCATIONS:
            if isinstance(ml, dict):
                locs.append({
                    'name': ml.get('name') or f'{BIZ} Main Office',
                    'address': {
                        'streetAddress': ml.get('address') or '',
                        'addressLocality': ml.get('city') or '',
                        'addressRegion': ml.get('state') or '',
                        'postalCode': ml.get('zip') or '',
                    },
                    'telephone': ml.get('phone') or PHONE,
                    'email': ml.get('email') or EMAIL,
                    'url': WEBSITE,
                })
    for l in locs:
        if not isinstance(l, dict): continue
        name = _first(l.get('name'), l.get('entity_name')) or 'Location'
        addr = l.get('address', {})
        if isinstance(addr, dict):
            street = _first(addr.get('streetAddress'))
            city = _first(addr.get('addressLocality'))
            state = _first(addr.get('addressRegion'))
            zipc = _first(addr.get('postalCode'))
        else:
            street = city = state = zipc = ''
        phone = _first(l.get('telephone'), l.get('phone'))
        email = _first(l.get('email'))
        hours = _first(l.get('openingHours'), l.get('hours'))
        website = _first(l.get('url'), l.get('website'))

        if not first_phone and phone: first_phone = phone
        if not first_email and email: first_email = email

        block = f'<div class="card"><h3>{esc(name)}</h3><p>'
        addr_parts = [p for p in [street, ', '.join(filter(None, [city, state])), zipc] if p]
        if addr_parts: block += f'<strong>Address:</strong> {esc(" ".join(addr_parts))}<br>'
        if phone: block += f'<strong>Phone:</strong> <a href="tel:{esc(phone)}">{esc(phone)}</a><br>'
        if email: block += f'<strong>Email:</strong> <a href="mailto:{esc(email)}">{esc(email)}</a><br>'
        if hours: block += f'<strong>Hours:</strong> {esc(hours)}<br>'
        if website: block += f'<strong>Website:</strong> <a href="{esc(website)}" target="_blank" rel="nofollow">{esc(website)}</a><br>'
        block += '</p>'

        # Map embed
        geo = l.get('geo', {})
        lat = geo.get('latitude') if isinstance(geo, dict) else None
        lng = geo.get('longitude') if isinstance(geo, dict) else None
        if isinstance(lat, (int, float)) and isinstance(lng, (int, float)):
            block += f'<div style="margin-top:1rem;"><iframe src="https://www.google.com/maps?q={lat},{lng}&z=15&output=embed" width="100%" height="320" style="border:0;border-radius:8px;" allowfullscreen loading="lazy"></iframe></div>'
        else:
            map_query = ' '.join(addr_parts) or name
            if map_query:
                block += f'<div style="margin-top:1rem;"><iframe title="Map to {esc(name)}" src="https://www.google.com/maps?q={quote_plus(map_query)}&output=embed" width="100%" height="320" style="border:0;border-radius:8px;" allowfullscreen loading="lazy" referrerpolicy="no-referrer-when-downgrade"></iframe></div>'

        block += '</div>'
        items.append(block)

    # Quick contact card — use location data with manifest fallbacks
    if not first_phone and PHONE: first_phone = PHONE
    if not first_email and EMAIL: first_email = EMAIL
    intro = '<p>We\u2019d love to hear from you. Reach out using the details below or visit us at our offices.</p>'
    if first_phone or first_email or WEBSITE:
        intro += '<div class="card"><h2>Quick Contact</h2>'
        if first_phone: intro += f'<p><strong>Phone:</strong> <a href="tel:{esc(first_phone)}">{esc(first_phone)}</a></p>'
        if first_email: intro += f'<p><strong>Email:</strong> <a href="mailto:{esc(first_email)}">{esc(first_email)}</a></p>'
        if WEBSITE: intro += f'<p><strong>Website:</strong> <a href="{esc(WEBSITE)}">{esc(WEBSITE)}</a></p>'
        intro += '</div>'

    content = intro + ''.join(items) if items else intro + '<p>Contact details are not available yet.</p>'
    write_page('contact.html', f'Contact {BIZ}', content, f'Contact {BIZ}. Phone, email, and office locations.', [{'@context': 'https://schema.org', '@type': 'ContactPage', 'name': f'Contact {BIZ}', 'url': page_url('contact.html'), 'speakable': SPEAKABLE}, org_ld()])

# ═══════════════════════════════════════
# Main
# ═══════════════════════════════════════
if __name__ == '__main__':
    print('STARTING build_public_pages.py')

    # Ensure .nojekyll for GitHub Pages
    open('.nojekyll', 'w').close()

    # Pre-scan to determine which pages have data (so all pages get complete nav)
    _prescan_pages()

    # Build content pages first so BUILT_PAGES is populated, then index last
    page_generators = [
        ('about.html', build_about),
        ('services.html', build_services),
        ('reviews.html', build_testimonials),
        ('awards.html', build_awards),
        ('faqs.html', build_faqs),
        ('articles.html', build_help),
        ('web-pages.html', build_webpages),
        ('contact.html', build_contact),
        ('index.html', build_index),
    ]

    any_success = False
    for filename, generator in page_generators:
        try:
            generator()
            any_success = True
        except Exception as e:
            print(f'  FAILED {filename}: {e}')

    if not any_success:
        print('WARNING: No pages generated')
    else:
        print('BUILD COMPLETE')

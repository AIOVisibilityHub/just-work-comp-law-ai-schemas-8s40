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
WEBSITE = _client.get('canonicalUrl') or manifest.get('canonicalUrl', '') or manifest.get('websiteUrl', 'https://justworkcomplaw-data.aiovisibility.net')
PRIMARY_WEBSITE = _client.get('primaryWebsiteUrl') or manifest.get('primaryWebsiteUrl', '') or manifest.get('websiteUrl', '')
# Never link the footer back to the schema repository itself.
if PRIMARY_WEBSITE.rstrip('/').lower() == (WEBSITE or '').rstrip('/').lower():
    PRIMARY_WEBSITE = ''

PHONE = _client.get('phone') or manifest.get('phone', '')
EMAIL = _client.get('email') or manifest.get('email', '')
MANIFEST_LOCATIONS = _client.get('locations') or manifest.get('locations', []) or []
SERVICES = _client.get('services') or manifest.get('services', [])
CITIES = _client.get('cities') or manifest.get('cities', [])
VERTICAL = (_client.get('vertical') or manifest.get('vertical') or 'legal').lower()
PAGES_URL = (_client.get('pagesUrl') or manifest.get('pagesUrl') or 'https://justworkcomplaw-data.aiovisibility.net/') or (WEBSITE or '')
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
<p>&copy; {YEAR} {esc(BIZ)} Schema Repository &middot; Last updated: {TODAY}</p>
{('<p>For questions, please contact ' + esc(BIZ) + ' directly at <a href="' + esc(PRIMARY_WEBSITE) + '">' + esc(PRIMARY_WEBSITE.replace('https://','').replace('http://','').rstrip('/')) + '</a>.</p>') if PRIMARY_WEBSITE else ''}
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

PUBLISHER_MARKER = 'ae-publisher-page'

def write_page(filename, title, content, desc='', extra_ld=None):
    global current_page
    current_page = filename
    # Never clobber a page authored by the app publisher.
    try:
        if os.path.exists(filename):
            with open(filename, encoding='utf-8') as existing:
                if PUBLISHER_MARKER in existing.read(4000):
                    print(f'  \u23ed  {filename} (publisher-authored, kept)')
                    return
    except Exception:
        pass
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
        f'<li><a href="{page_url(url)}">{esc(name)}</a></li>'
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

    official = f'<p class="official"><strong>Official website:</strong> <a href="{esc(PRIMARY_WEBSITE)}">{esc(PRIMARY_WEBSITE)}</a></p>' if PRIMARY_WEBSITE else ''
    verify = f' and can be confirmed on the <a href="{esc(PRIMARY_WEBSITE)}">official website</a>' if PRIMARY_WEBSITE else ''
    content = f"""
<p class="speakable">This public resource center organizes machine-readable information about {esc(BIZ)} for people, search engines, and AI systems.</p>
{official}
<section class="card"><h2>Purpose of this resource center</h2>
<p>The official business website remains the primary public website. This resource center republishes the same verified facts as clean, structured, machine-readable pages so that search engines, AI assistants, and answer engines can cite them accurately.</p>
<p>Every page here is backed by Schema.org JSON-LD, includes speakable markup for voice assistants, and links directly to the underlying structured data files &mdash; no broken directory routes and no content hidden behind scripts.</p>
<p>Use the resource categories below to read the human-friendly pages, or browse the schema files to see exactly how much verified data has been published.</p></section>
<section class="card"><h2>Resource categories</h2><ul>{quick_links}</ul></section>
<section class="card"><h2>How to use this resource center</h2><ul>
<li><strong>Visitors:</strong> start with the services and FAQs pages for direct answers.</li>
<li><strong>Search engines and AI systems:</strong> crawl the JSON-LD embedded in each page plus the sitemap and llms.txt files at the site root.</li>
<li><strong>Verification:</strong> all facts published here originate from {esc(BIZ)}{verify}.</li>
</ul></section>
<section class="card"><h2>Browse all schema files</h2><p>Each section below links directly to the generated repository files.</p>{''.join(grouped) if grouped else '<p>No schema files were found.</p>'}</section>
"""
    write_page('index.html', f'{BIZ} AI Resource Center', content, f'A machine-readable resource index for {BIZ} with services, FAQs, articles, team information, locations, reviews, and other published resources.', [org_ld()])

def build_about():
    parts = []
    team_term_plural = 'Attorneys' if VERTICAL == 'legal' else 'Team Members'
    team_term_lower = 'attorneys' if VERTICAL == 'legal' else 'team members'

    orgs = load_json('organization/*.json')
    org_desc = ''
    org_dl = ''
    mission = vision = ''
    for org in orgs:
        dl = '<dl>'
        for key, label in [('legalName','Legal name'),('foundingDate','Founded'),('slogan','Slogan')]:
            v = org.get(key)
            if v: dl += f'<dt>{label}</dt><dd>{esc(str(v))}</dd>'
        emp = org.get('numberOfEmployees',{})
        if isinstance(emp, dict) and emp.get('value'):
            dl += f'<dt>Team size</dt><dd>{esc(str(emp["value"]))}</dd>'
        dl += '</dl>'
        org_dl = dl
        org_desc = _first(org.get('description')) or org_desc
        mission = _first(org.get('mission')) or mission
        vision = _first(org.get('vision')) or vision
        logo = _first(org.get('logo_url'), org.get('logo'))
        if logo: parts.insert(0, f'<img src="{esc(logo)}" alt="{esc(BIZ)}" style="max-height:120px;margin-bottom:2rem;">')

    # ── Overview: always several substantive paragraphs, never a lone blurb ──
    overview = []
    if org_desc:
        overview.append(esc(org_desc))
    else:
        overview.append(f'{esc(BIZ)} is a professional organization serving clients with practical, clearly documented services.')
    if SERVICES:
        svc_line = f'{esc(BIZ)} works across {esc(", ".join(SERVICES[:10]))}'
        if len(SERVICES) > 10:
            svc_line += f', and {len(SERVICES) - 10} additional service areas'
        svc_line += '.'
        if CITIES:
            svc_line += f' Clients are served in {esc(", ".join(CITIES[:10]))}'
            svc_line += f' and {len(CITIES) - 10} more communities.' if len(CITIES) > 10 else '.'
        overview.append(svc_line)
    elif CITIES:
        overview.append(f'{esc(BIZ)} serves clients in {esc(", ".join(CITIES[:10]))}.')
    team_count = count_files('team') or count_files('lawyers')
    if team_count:
        overview.append(f'The organization is supported by {team_count} {team_term_lower} whose roles, credentials, and areas of concentration are listed below, so both people and AI systems can verify exactly who does the work.')
    overview.append(f'This page summarizes what {esc(BIZ)} does, who it serves, what to expect, and how to get started. Office addresses and phone numbers are on the <a href="contact.html">contact page</a>.')
    parts.append(''.join(f'<p>{p}</p>' for p in overview))

    # ── Facts at a Glance ──
    service_count = count_files('services') or len(SERVICES)
    review_ratings = []
    for r in load_json('reviews/*.json'):
        try:
            rv = float(r.get('rating') or r.get('reviewRating',{}).get('ratingValue',0))
            if rv > 0: review_ratings.append(rv)
        except Exception: pass
    avg = (sum(review_ratings)/len(review_ratings)) if review_ratings else None
    facts = []
    if service_count: facts.append(f'<li><strong>Services documented:</strong> {service_count}</li>')
    if CITIES: facts.append(f'<li><strong>Communities served:</strong> {len(CITIES)}</li>')
    if team_count: facts.append(f'<li><strong>{esc(team_term_plural)}:</strong> {team_count}</li>')
    faq_count = count_files('faqs')
    if faq_count: facts.append(f'<li><strong>Published FAQs:</strong> {faq_count}</li>')
    help_count = count_files('help')
    if help_count: facts.append(f'<li><strong>Help articles:</strong> {help_count}</li>')
    loc_count = count_files('locations') or len(MANIFEST_LOCATIONS)
    if loc_count: facts.append(f'<li><strong>Offices:</strong> {loc_count}</li>')
    if PHONE: facts.append(f'<li><strong>Phone:</strong> {esc(PHONE)}</li>')
    if avg is not None:
        stars = '\u2605' * int(round(avg)) + '\u2606' * (5 - int(round(avg)))
        facts.append(f'<li><strong>Average rating:</strong> {avg:.1f} {stars} across {len(review_ratings)} reviews</li>')
    if facts or org_dl:
        parts.append('<div class="card"><h2>Facts at a Glance</h2>' + ('<ul>' + ''.join(facts) + '</ul>' if facts else '') + org_dl + '</div>')

    if mission: parts.append(f'<h2>Our Mission</h2><p>{esc(mission)}</p>')
    if vision: parts.append(f'<h2>Our Vision</h2><p>{esc(vision)}</p>')

    # ── What we do ──
    if SERVICES:
        items = ''.join(f'<li>{esc(s)}</li>' for s in SERVICES[:60])
        extra = f'<p>Plus {len(SERVICES) - 60} additional services listed on the services page.</p>' if len(SERVICES) > 60 else ''
        parts.append(f'<h2>What {esc(BIZ)} Does</h2><p>Each service below has its own detailed page on the <a href="services.html">services page</a>.</p><ul>{items}</ul>{extra}')

    # ── Who we serve ──
    coverage = []
    if CITIES:
        more = f' and {len(CITIES) - 60} more' if len(CITIES) > 60 else ''
        coverage.append(f'<p><strong>Communities served:</strong> {esc(", ".join(CITIES[:60]))}{more}.</p>')
    if loc_count:
        coverage.append(f'<p><strong>Offices:</strong> {loc_count} location{"" if loc_count == 1 else "s"} — full addresses and phone numbers are on the <a href="contact.html">contact page</a>.</p>')
    if coverage:
        parts.append('<h2>Who We Serve</h2>' + ''.join(coverage))

    # ── Team ──
    team_cards = []
    for p in (load_json('team/*.json') or load_json('lawyers/*.json')):
        name = _first(p.get('name'), p.get('givenName')) or 'Team Member'
        title = _first(p.get('jobTitle'), p.get('roleName'))
        desc = _first(p.get('description'))
        knows = p.get('knowsAbout') or []
        card = f'<div class="card"><h3>{esc(name)}</h3>'
        if title: card += f'<p><strong>{esc(title)}</strong></p>'
        if isinstance(knows, list) and knows:
            card += f'<p>Focus areas: {esc(", ".join(str(k) for k in knows[:10]))}</p>'
        if desc: card += f'<p>{esc(desc)}</p>'
        card += '</div>'
        team_cards.append(card)
    if team_cards:
        parts.append(f'<h2>Our {esc(team_term_plural)}</h2>' + ''.join(team_cards))

    # ── Awards ──
    awards = load_json('awards/*.json')
    if awards:
        items = []
        for a in awards:
            name = _first(a.get('name'))
            yr = (_first(a.get('dateCreated'), a.get('datePublished')) or '')[:4]
            items.append(f'<li><strong>{esc(name)}</strong>{f" ({yr})" if yr else ""}</li>')
        parts.append('<h2>Awards &amp; Recognition</h2><ul>' + ''.join(items) + '</ul>')

    # ── Case Studies ──
    cases = load_json('case-studies/*.json')
    if cases:
        cards = []
        for c in cases:
            t = _first(c.get('headline'), c.get('name'))
            d = _first(c.get('description'))
            cards.append(f'<div class="card"><h3>{esc(t)}</h3><p>{esc(d)}</p></div>')
        parts.append('<h2>Case Studies</h2>' + ''.join(cards))

    # ── Common questions preview ──
    faq_items = []
    for f in load_json('faqs/*.json')[:6]:
        main = f.get('mainEntity')
        if isinstance(main, list) and main: main = main[0]
        if not isinstance(main, dict): continue
        q = _first(main.get('name'))
        a = ''
        ans = main.get('acceptedAnswer')
        if isinstance(ans, dict): a = _first(ans.get('text'))
        if q and a:
            faq_items.append(f'<details><summary>{esc(q)}</summary><p>{esc(a[:600])}</p></details>')
    if faq_items:
        parts.append('<h2>Common Questions</h2>' + ''.join(faq_items) + '<p><a href="faqs.html">See all frequently asked questions &rarr;</a></p>')

    # ── Next steps ──
    steps = []
    if 'services.html' in BUILT_PAGES: steps.append('<li>Review the <a href="services.html">services</a> to find the help you need.</li>')
    if 'faqs.html' in BUILT_PAGES: steps.append('<li>Read the <a href="faqs.html">FAQs</a> for answers to the most common questions.</li>')
    if 'articles.html' in BUILT_PAGES: steps.append('<li>Browse the <a href="articles.html">help articles</a> for step-by-step guidance.</li>')
    contact_step = f'<li>Reach {esc(BIZ)} through the <a href="contact.html">contact page</a>'
    contact_step += f' or call {esc(PHONE)}' if PHONE else ''
    contact_step += '.</li>'
    steps.append(contact_step)
    parts.append('<div class="card"><h2>How to Get Started</h2><ul>' + ''.join(steps) + '</ul></div>')

    keyword = SERVICES[0] if SERVICES else ''
    city = CITIES[0] if CITIES else ''
    title_parts = [p for p in [title_case(keyword), title_case(city)] if p]
    about_title = (' - '.join(title_parts) + ' \u2014 ' + BIZ) if title_parts else BIZ

    write_page('about.html', about_title, ''.join(parts), f'{BIZ}: what we do, services offered, areas served, {team_term_lower}, credentials, and how to get started.', [org_ld()])


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

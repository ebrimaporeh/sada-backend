"""One-off script: fetches relatable free images from Wikimedia Commons and
uploads a cover + 2 gallery images for every production campaign via the
admin media endpoint. Saves a local copy under media/campaign_seed_images/
too. Not part of the app — run manually, then safe to delete."""
import os
import sys
import time
import requests

API_BASE = 'https://web-production-c8c81.up.railway.app/api/v1'
TOKEN = sys.argv[1] if len(sys.argv) > 1 else None
if not TOKEN:
    print('Usage: python scripts/seed_campaign_images.py <access_token>')
    sys.exit(1)

HEADERS = {'Authorization': f'Bearer {TOKEN}'}
LOCAL_DIR = os.path.join(os.path.dirname(__file__), '..', 'media', 'campaign_seed_images')
os.makedirs(LOCAL_DIR, exist_ok=True)

# slug -> (cover query, gallery query 1, gallery query 2)
QUERIES = {
    'flood-relief-basse-2026': ('flood disaster relief Africa', 'emergency relief aid supplies', 'flood rescue boat water'),
    'brikama-school-building-project': ('African primary school classroom', 'school children classroom Africa', 'school building construction Africa'),
    'help-fatou-get-kidney-surgery': ('hospital ward Africa patient', 'hospital surgery operating room', 'medical clinic Africa'),
    'utg-su-graduation-fund': ('university graduation ceremony Africa', 'university students campus Africa', 'graduation gown cap ceremony'),
    'bakau-mosque-water-system': ('mosque West Africa', 'mosque ablution wudu', 'mosque interior prayer hall'),
    'gambia-tech-hub-banjul': ('computer lab classroom students', 'coding programming class', 'laptop computer training Africa'),
    'memorial-late-omar-saho': ('memorial garden plaque', 'candle memorial ceremony', 'school library Africa'),
    'kanifing-market-expansion': ('African market women vendors', 'market stall Africa produce', 'women entrepreneurs market Africa'),
    'solar-panels-jinack-village-school': ('solar panels village Africa', 'solar panel installation roof', 'rural school village Africa'),
    'gambia-u17-football-afcon': ('youth football team Africa', 'football training pitch', 'football match stadium Africa'),
    'girls-scholarship-fund-gambia': ('African schoolgirls classroom', 'girls education Africa', 'schoolgirl uniform Africa'),
    'baby-modou-heart-surgery': ('hospital newborn baby pediatric', 'hospital ward Africa', 'pediatric hospital care'),
    'farafenni-clean-water-project': ('water well borehole Africa', 'women fetching water Africa', 'clean water pump village'),
    'bakau-mosque-renovation': ('mosque renovation construction', 'mosque exterior West Africa', 'mosque dome architecture'),
}

WIKI_HEADERS = {'User-Agent': 'DolelmaSeedScript/1.0 (contact: support@dolelma.com)'}
VALID_MIME = {'image/jpeg', 'image/png'}


def find_image(query, tried=None):
    tried = tried or set()
    r = requests.get(
        'https://commons.wikimedia.org/w/api.php',
        params={
            'action': 'query', 'format': 'json', 'generator': 'search',
            'gsrsearch': query, 'gsrnamespace': 6, 'gsrlimit': 10,
            'prop': 'imageinfo', 'iiprop': 'url|mime|size', 'iiurlwidth': 1600,
        },
        headers=WIKI_HEADERS, timeout=20,
    )
    r.raise_for_status()
    pages = r.json().get('query', {}).get('pages', {})
    candidates = []
    for page in pages.values():
        info = page.get('imageinfo', [{}])[0]
        url = info.get('thumburl') or info.get('url')
        if not url or info.get('mime') not in VALID_MIME or url in tried:
            continue
        candidates.append(url)
    return candidates[0] if candidates else None


def download(url):
    r = requests.get(url, headers=WIKI_HEADERS, timeout=30)
    r.raise_for_status()
    return r.content


def main():
    resp = requests.get(f'{API_BASE}/campaigns/', params={'page_size': 50}, timeout=30)
    resp.raise_for_status()
    campaigns = resp.json()['results']
    print(f'Found {len(campaigns)} campaigns.\n')

    for c in campaigns:
        slug, cid, title = c['slug'], c['id'], c['title']
        queries = QUERIES.get(slug)
        if not queries:
            print(f'[skip] {slug} — no query mapping')
            continue

        print(f'--- {title} ({slug}) ---')
        files = {}
        opened = []
        try:
            for field, query in zip(('cover', 'gallery', 'gallery'), queries):
                url = find_image(query)
                if not url:
                    print(f'  ! no image found for "{query}"')
                    continue
                content = download(url)
                ext = 'jpg' if url.lower().endswith(('.jpg', '.jpeg')) else 'png'
                local_name = f'{slug}_{field}_{len(opened)}.{ext}'
                local_path = os.path.join(LOCAL_DIR, local_name)
                with open(local_path, 'wb') as f:
                    f.write(content)
                print(f'  + downloaded {field}: {url} ({len(content)} bytes) -> {local_name}')

                fh = open(local_path, 'rb')
                opened.append(fh)
                key = 'cover' if field == 'cover' else 'gallery'
                if key == 'gallery':
                    files.setdefault('gallery', []).append(('gallery', (local_name, fh, f'image/{ext}')))
                else:
                    files['cover'] = ('cover', (local_name, fh, f'image/{ext}'))

            multipart = []
            if 'cover' in files:
                multipart.append(files['cover'])
            for item in files.get('gallery', []):
                multipart.append(item)

            if not multipart:
                print('  ! nothing to upload, skipping')
                continue

            upload_resp = requests.post(
                f'{API_BASE}/campaigns/admin/{cid}/media/',
                headers=HEADERS,
                files=multipart,
                timeout=60,
            )
            print(f'  upload -> {upload_resp.status_code}')
            if upload_resp.status_code != 200:
                print(f'  ERROR: {upload_resp.text[:500]}')
            else:
                data = upload_resp.json()['data']['campaign']
                print(f'  cover_image_url: {data.get("cover_image_url")}')
        finally:
            for fh in opened:
                fh.close()
        print()
        time.sleep(0.3)


if __name__ == '__main__':
    main()

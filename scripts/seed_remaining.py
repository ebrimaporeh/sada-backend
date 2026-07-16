import sys
sys.path.insert(0, '.')
from scripts.seed_campaign_images import find_image, download, API_BASE, LOCAL_DIR
import os
import requests

TOKEN = sys.argv[1]
HEADERS = {'Authorization': f'Bearer {TOKEN}'}

resp = requests.get(f'{API_BASE}/campaigns/', params={'page_size': 50}, timeout=30)
campaigns = {c['slug']: c for c in resp.json()['results']}

# farafenni: reuse already-downloaded local files
slug = 'farafenni-clean-water-project'
cid = campaigns[slug]['id']
cover_path = os.path.join(LOCAL_DIR, f'{slug}_cover_0.jpg')
g1_path = os.path.join(LOCAL_DIR, f'{slug}_gallery_1.jpg')
g2_path = os.path.join(LOCAL_DIR, f'{slug}_gallery_2.jpg')

with open(cover_path, 'rb') as cf, open(g1_path, 'rb') as g1f, open(g2_path, 'rb') as g2f:
    r = requests.post(
        f'{API_BASE}/campaigns/admin/{cid}/media/',
        headers=HEADERS,
        files=[
            ('cover', ('cover.jpg', cf, 'image/jpeg')),
            ('gallery', ('g1.jpg', g1f, 'image/jpeg')),
            ('gallery', ('g2.jpg', g2f, 'image/jpeg')),
        ],
        timeout=60,
    )
print(slug, '->', r.status_code)
if r.status_code != 200:
    print(r.text[:500])
else:
    print(r.json()['data']['campaign']['cover_image_url'])

# bakau-mosque-renovation: full download + upload
slug = 'bakau-mosque-renovation'
cid = campaigns[slug]['id']
queries = ('mosque renovation construction', 'mosque exterior West Africa', 'mosque dome architecture')
opened = []
multipart = []
try:
    for field, query in zip(('cover', 'gallery', 'gallery'), queries):
        url = find_image(query)
        if not url:
            print(f'  ! no image for {query}')
            continue
        content = download(url)
        ext = 'jpg' if url.lower().endswith(('.jpg', '.jpeg')) else 'png'
        name = f'{slug}_{field}_{len(opened)}.{ext}'
        path = os.path.join(LOCAL_DIR, name)
        with open(path, 'wb') as f:
            f.write(content)
        print(f'  + downloaded {field}: {url} ({len(content)} bytes)')
        fh = open(path, 'rb')
        opened.append(fh)
        multipart.append((field, (name, fh, f'image/{ext}')))

    r = requests.post(f'{API_BASE}/campaigns/admin/{cid}/media/', headers=HEADERS, files=multipart, timeout=60)
    print(slug, '->', r.status_code)
    if r.status_code != 200:
        print(r.text[:500])
    else:
        print(r.json()['data']['campaign']['cover_image_url'])
finally:
    for fh in opened:
        fh.close()

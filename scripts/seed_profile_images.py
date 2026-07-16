"""One-off script: fetches relatable free images from Wikimedia Commons and
sets an avatar for every individual user, and a logo for every
organization, via the admin endpoints. Saves a local copy under
media/profile_seed_images/ too."""
import os
import sys
import time
import requests

sys.path.insert(0, os.path.dirname(__file__))
from seed_campaign_images import find_image, download

API_BASE = 'https://web-production-c8c81.up.railway.app/api/v1'
if len(sys.argv) < 2:
    print('Usage: python scripts/seed_profile_images.py <access_token> [refresh_token]')
    sys.exit(1)

ACCESS_TOKEN = sys.argv[1]
REFRESH_TOKEN = sys.argv[2] if len(sys.argv) > 2 else None
LOCAL_DIR = os.path.join(os.path.dirname(__file__), '..', 'media', 'profile_seed_images')
os.makedirs(LOCAL_DIR, exist_ok=True)


class Auth:
    """Holds the current access token, refreshing it via the refresh token
    (if provided) whenever a request comes back 401 — access tokens are
    15 minutes in production, easy to outlive during a long seeding run."""
    def __init__(self, access, refresh):
        self.access = access
        self.refresh = refresh

    def headers(self):
        return {'Authorization': f'Bearer {self.access}'}

    def refresh_access_token(self):
        if not self.refresh:
            raise RuntimeError('Access token expired and no refresh token was provided.')
        r = requests.post(f'{API_BASE}/auth/refresh/', json={'refresh': self.refresh}, timeout=15)
        r.raise_for_status()
        self.access = r.json()['access']
        print('  (refreshed access token)')

    def request(self, method, url, **kwargs):
        resp = requests.request(method, url, headers=self.headers(), **kwargs)
        if resp.status_code == 401:
            self.refresh_access_token()
            resp = requests.request(method, url, headers=self.headers(), **kwargs)
        return resp


AUTH = Auth(ACCESS_TOKEN, REFRESH_TOKEN)

# email -> search query
AVATAR_QUERIES = {
    'alieu.n@example.gm': 'African man portrait smiling',
    'modou.t@example.gm': 'African man portrait',
    'ousman.d@example.gm': 'West African man portrait',
    'kaddy.s@example.gm': 'African woman portrait',
    'lamine.b@example.gm': 'African man portrait casual',
    'aminata.k@example.gm': 'West African woman portrait',
    'amie.saho@example.gm': 'African woman portrait smiling',
    'fatou.touray@example.gm': 'African businesswoman portrait',
    'baboucarr.sowe@example.gm': 'African man portrait outdoor',
    'gff@example.gm': 'football stadium Africa crowd',
    'ndey.joof@example.gm': 'African woman portrait professional',
    'lamine.drammeh@example.gm': 'African teacher man portrait',
    'mariama.sanyang@example.gm': 'African woman portrait community',
    'alhagie.bojang@example.gm': 'African elder man portrait',
    'isatou.ceesay@example.gm': 'African woman portrait',
    'salimatou.njie@example.gm': 'African woman portrait teacher',
    'omar.jallow@example.gm': 'African man portrait healthcare worker',
    'ousman@sada.gm': 'African man portrait community leader',
}

ORG_LOGO_QUERIES = {
    'bakau.mosque@example.gm': 'mosque icon logo',
    'naatip@example.gm': 'government seal emblem Africa',
    'serrekunda.cda@example.gm': 'community development logo Africa',
    'utgsu@example.gm': 'university seal logo emblem',
    'whatsongambia@example.gm': 'media logo microphone icon',
}


def seed_one(email, user_id, query, field_name, endpoint_suffix, retries=2):
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            url = find_image(query)
            if not url:
                print(f'  ! no image found for "{query}"')
                return False
            content = download(url)
            ext = 'jpg' if url.lower().endswith(('.jpg', '.jpeg')) else 'png'
            name = f'{email.split("@")[0]}_{field_name}.{ext}'
            path = os.path.join(LOCAL_DIR, name)
            with open(path, 'wb') as f:
                f.write(content)
            print(f'  + downloaded: {url} ({len(content)} bytes)')

            with open(path, 'rb') as fh:
                resp = AUTH.request(
                    'post', f'{API_BASE}/users/admin/{user_id}/{endpoint_suffix}/',
                    files={field_name: (name, fh, f'image/{ext}')}, timeout=60,
                )
            print(f'  upload -> {resp.status_code}')
            if resp.status_code == 200:
                return True
            print(f'  ERROR: {resp.text[:400]}')
            last_error = resp.text[:200]
        except Exception as e:
            print(f'  EXCEPTION (attempt {attempt}/{retries}): {e}')
            last_error = str(e)
        time.sleep(1)
    print(f'  giving up on {email} after {retries} attempts: {last_error}')
    return False


def main():
    resp = AUTH.request('get', f'{API_BASE}/users/', params={'page_size': 50}, timeout=30)
    resp.raise_for_status()
    users = {u['email']: u for u in resp.json()['results']}
    print(f'Found {len(users)} users.\n')

    results = {}
    for email, query in AVATAR_QUERIES.items():
        user = users.get(email)
        if not user:
            print(f'[skip] {email} — not found')
            continue
        print(f'--- {user.get("full_name") or email} (avatar) ---')
        results[email] = seed_one(email, user['id'], query, 'avatar', 'avatar')
        time.sleep(0.3)

    print()
    for email, query in ORG_LOGO_QUERIES.items():
        user = users.get(email)
        if not user:
            print(f'[skip] {email} — not found')
            continue
        print(f'--- {user.get("full_name") or email} (org logo) ---')
        results[email] = seed_one(email, user['id'], query, 'logo', 'organization-logo')
        time.sleep(0.3)

    print('\n=== Summary ===')
    for email, ok in results.items():
        print(f'{"OK " if ok else "FAIL"} {email}')
    failed = [e for e, ok in results.items() if not ok]
    if failed:
        print(f'\n{len(failed)} failed: {failed}')


if __name__ == '__main__':
    main()

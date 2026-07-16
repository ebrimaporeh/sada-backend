"""Sets an avatar for every individual user using randomuser.me — a free,
no-auth API built specifically for realistic modern placeholder profile
photos (model-released, not historical/archival), and sets each
organization's logo from the locally-generated initials badges. Replaces
the earlier Wikimedia-Commons-based pass, which surfaced inappropriate
historical/archival photos (some of named real people) and, for
organizations, real unrelated institutions' actual logos."""
import os
import sys
import time
import requests

API_BASE = 'https://web-production-c8c81.up.railway.app/api/v1'
if len(sys.argv) < 2:
    print('Usage: python scripts/seed_avatars_v2.py <access_token> [refresh_token]')
    sys.exit(1)

ACCESS_TOKEN = sys.argv[1]
REFRESH_TOKEN = sys.argv[2] if len(sys.argv) > 2 else None
LOCAL_DIR = os.path.join(os.path.dirname(__file__), '..', 'media', 'profile_seed_images')
os.makedirs(LOCAL_DIR, exist_ok=True)


class Auth:
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

# email -> gender (for randomuser.me's gendered portrait sets)
USERS = {
    'alieu.n@example.gm': 'male',
    'modou.t@example.gm': 'male',
    'ousman.d@example.gm': 'male',
    'kaddy.s@example.gm': 'female',
    'lamine.b@example.gm': 'male',
    'aminata.k@example.gm': 'female',
    'amie.saho@example.gm': 'female',
    'fatou.touray@example.gm': 'female',
    'baboucarr.sowe@example.gm': 'male',
    'gff@example.gm': 'male',
    'ndey.joof@example.gm': 'female',
    'lamine.drammeh@example.gm': 'male',
    'mariama.sanyang@example.gm': 'female',
    'alhagie.bojang@example.gm': 'male',
    'isatou.ceesay@example.gm': 'female',
    'salimatou.njie@example.gm': 'female',
    'omar.jallow@example.gm': 'male',
    'ousman@sada.gm': 'male',
}

ORG_LOGO_FILES = {
    'bakau.mosque@example.gm': 'bakau.mosque_logo.png',
    'naatip@example.gm': 'naatip_logo.png',
    'serrekunda.cda@example.gm': 'serrekunda.cda_logo.png',
    'utgsu@example.gm': 'utgsu_logo.png',
    'whatsongambia@example.gm': 'whatsongambia_logo.png',
}


def seed_avatar(email, user_id, gender, retries=3):
    for attempt in range(1, retries + 1):
        try:
            r = requests.get('https://randomuser.me/api/', params={'gender': gender, 'inc': 'picture'}, timeout=15)
            r.raise_for_status()
            photo_url = r.json()['results'][0]['picture']['large']
            content = requests.get(photo_url, timeout=15).content
            name = f'{email.split("@")[0]}_avatar.jpg'
            path = os.path.join(LOCAL_DIR, name)
            with open(path, 'wb') as f:
                f.write(content)
            print(f'  + {photo_url} ({len(content)} bytes)')

            with open(path, 'rb') as fh:
                resp = AUTH.request(
                    'post', f'{API_BASE}/users/admin/{user_id}/avatar/',
                    files={'avatar': (name, fh, 'image/jpeg')}, timeout=60,
                )
            print(f'  upload -> {resp.status_code}')
            if resp.status_code == 200:
                return True
            print(f'  ERROR: {resp.text[:300]}')
        except Exception as e:
            print(f'  EXCEPTION (attempt {attempt}/{retries}): {e}')
        time.sleep(1)
    return False


def seed_logo(email, user_id, filename, retries=3):
    path = os.path.join(LOCAL_DIR, filename)
    for attempt in range(1, retries + 1):
        try:
            with open(path, 'rb') as fh:
                resp = AUTH.request(
                    'post', f'{API_BASE}/users/admin/{user_id}/organization-logo/',
                    files={'logo': (filename, fh, 'image/png')}, timeout=60,
                )
            print(f'  upload -> {resp.status_code}')
            if resp.status_code == 200:
                return True
            print(f'  ERROR: {resp.text[:300]}')
        except Exception as e:
            print(f'  EXCEPTION (attempt {attempt}/{retries}): {e}')
        time.sleep(1)
    return False


def main():
    resp = AUTH.request('get', f'{API_BASE}/users/', params={'page_size': 50}, timeout=30)
    resp.raise_for_status()
    users = {u['email']: u for u in resp.json()['results']}
    print(f'Found {len(users)} users.\n')

    results = {}
    for email, gender in USERS.items():
        user = users.get(email)
        if not user:
            print(f'[skip] {email} — not found')
            continue
        print(f'--- {user.get("full_name") or email} (avatar) ---')
        results[email] = seed_avatar(email, user['id'], gender)
        time.sleep(0.2)

    print()
    for email, filename in ORG_LOGO_FILES.items():
        user = users.get(email)
        if not user:
            print(f'[skip] {email} — not found')
            continue
        print(f'--- {user.get("full_name") or email} (org logo) ---')
        results[email] = seed_logo(email, user['id'], filename)
        time.sleep(0.2)

    print('\n=== Summary ===')
    for email, ok in results.items():
        print(f'{"OK " if ok else "FAIL"} {email}')
    failed = [e for e, ok in results.items() if not ok]
    if failed:
        print(f'\n{len(failed)} failed: {failed}')


if __name__ == '__main__':
    main()

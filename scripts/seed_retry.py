import sys
sys.path.insert(0, '.')
from scripts.seed_profile_images import Auth, seed_one, API_BASE

ACCESS = sys.argv[1]
REFRESH = sys.argv[2] if len(sys.argv) > 2 else None

import scripts.seed_profile_images as spi
spi.AUTH = Auth(ACCESS, REFRESH)

RETRY_QUERIES = {
    'alieu.n@example.gm': 'African man portrait smiling',
    'modou.t@example.gm': 'African man portrait',
    'ousman.d@example.gm': 'West African man portrait',
    'lamine.b@example.gm': 'African man face portrait',
    'omar.jallow@example.gm': 'African man portrait',
    'ousman@sada.gm': 'African man portrait',
}

resp = spi.AUTH.request('get', f'{API_BASE}/users/', params={'page_size': 50}, timeout=30)
resp.raise_for_status()
users = {u['email']: u for u in resp.json()['results']}

results = {}
for email, query in RETRY_QUERIES.items():
    user = users.get(email)
    print(f'--- {user.get("full_name") or email} (avatar retry) ---')
    results[email] = seed_one(email, user['id'], query, 'avatar', 'avatar', retries=3)

print('\n=== Retry Summary ===')
for email, ok in results.items():
    print(f'{"OK " if ok else "FAIL"} {email}')

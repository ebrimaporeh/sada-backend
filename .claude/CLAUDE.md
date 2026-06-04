# Backend — AI Operating Instructions

## Stack

- Python 3.11+, Django 4.2, Django REST Framework
- JWT via SimpleJWT, django-allauth for auth/social
- drf-spectacular for OpenAPI docs
- python-decouple for environment config

## Entry Points

- `manage.py` — Django management (runserver, migrate, etc.)
- `config/urls.py` — Root URL configuration
- `settings/` — Split settings (base / development / production / testing)

## Key Patterns

1. **Settings**: Import from `settings.development` for dev. Always use `python-decouple` `config()` for env vars.
2. **Models**: Inherit from `apps.core.models.BaseModel` for `id`, `created_at`, `updated_at`.
3. **Auth**: Custom User model is `apps.users.models.User`. Never use Django's default User.
4. **Services**: Business logic goes in `services/`. Views call services, not models directly.
5. **Permissions**: Use `permissions/base.py` classes. Always set `permission_classes` on every view.
6. **Pagination**: Use `pagination.base.StandardResultsPagination` globally (already configured in DRF settings).
7. **Error responses**: Use `utils/exceptions.py` custom handler (already wired in DRF settings).
8. **Emails**: Go through `emails/service.py` — never use `send_mail` directly in views.

## Commands

```bash
python manage.py migrate
python manage.py seed_data
python manage.py create_admin
python manage.py runserver
python manage.py test tests/
```

## Adding a New App

1. `mkdir apps/myapp && touch apps/myapp/{__init__.py,apps.py,models.py,serializers.py,views.py,urls.py}`
2. Add `apps.py` with `AppConfig`
3. Add `'apps.myapp'` to `LOCAL_APPS` in `settings/base.py`
4. Add URL pattern in `config/urls.py`
5. Create `apps/myapp/migrations/__init__.py`
6. Run `python manage.py makemigrations myapp`

import { defineRailway, github, preserve, project, redis, ref, service, volume } from "railway/iac";

export default defineRailway(() => {
  const sadaBackend = github("ebrimaporeh/sada-backend", { checkSuites: false });

  const Redis = redis("Redis", { region: "sfo" });
  Redis.deploy = { startCommand: "/bin/sh -c \"rm -rf $RAILWAY_VOLUME_MOUNT_PATH/lost+found/ && exec docker-entrypoint.sh redis-server --requirepass $REDIS_PASSWORD --save 60 1 --dir $RAILWAY_VOLUME_MOUNT_PATH\"" };
  Redis.networking = { privateNetworkEndpoint: "redis", tcpProxies: { "6379": {} } };
  // No postgres-volume here -- the real database is Supabase-hosted
  // (DATABASE_URL points off-platform), not a Railway-managed Postgres. A
  // stale `postgresVolume` declaration used to sit here (from an earlier
  // `railway config pull`, or a Railway Postgres addon that was never
  // actually provisioned/used) and `railway config plan` had been silently
  // proposing to create it on every plan -- removed rather than applied.
  // Live region is europe-west4-drams3a, not sfo -- differs from the Redis
  // service's own compute region above; the original `railway config pull`
  // mis-captured this volume's region as sfo, and applying that as declared
  // would have proposed a destructive volume region move. Corrected to match
  // Railway's actual reported live state (railway config plan's currentGraph).
  const redisVolume = volume("redis-volume", { alerts: { usage: { "100": {}, "80": {}, "95": {} } }, allowOnlineResize: true, region: "europe-west4-drams3a", sizeMB: 500 });
  const web = service("web", {
    source: sadaBackend,
    build: "python manage.py collectstatic --noinput",
    // Runs migrate before every deploy switches traffic to the new
    // release -- this was silently dropped when this service's config was
    // migrated off the old Config-as-Code railway.json (which had it under
    // `preDeploy`) onto this IaC file, and nothing caught it until a
    // deploy shipped schema changes (organizations.slug, apps.ledger,
    // apps.fundraising, payments.WebhookEvent) with no migration step to
    // apply them -- see git history around 2026-09-06 for the incident.
    // `seed_data` is idempotent (skips if already seeded unless --clear is
    // passed) so it's safe to run on every deploy, not just the first.
    preDeploy: "python manage.py migrate --noinput && python manage.py seed_data",
    start: "gunicorn config.wsgi:application",
    replicas: { "sfo": 1 },
    domains: ["api.dolelma.org"],
    env: { ALLOWED_HOSTS: preserve(), API_RATE_LIMIT_ANON: preserve(), API_RATE_LIMIT_USER: preserve(), CELERY_BROKER_URL: preserve(), CELERY_RESULT_BACKEND: preserve(), CONTACT_EMAIL: preserve(), CORS_ALLOWED_ORIGINS: preserve(), DATABASE_URL: preserve(), DEBUG: preserve(), DEFAULT_FROM_EMAIL: preserve(), DEMO_MODE: preserve(), DJANGO_SETTINGS_MODULE: preserve(), EMAIL_REPLY_TO: preserve(), FRONTEND_URL: preserve(), GOOGLE_OAUTH_CLIENT_ID: preserve(), GOOGLE_OAUTH_CLIENT_SECRET: preserve(), JWT_ACCESS_TOKEN_LIFETIME_MINUTES: preserve(), JWT_REFRESH_TOKEN_LIFETIME_DAYS: preserve(), MODEMPAY_MERCHANT_ID: preserve(), MODEMPAY_PUBLIC_API_KEY: preserve(), MODEMPAY_SECRET_API_KEY: preserve(), MODEMPAY_WEBHOOK_SECRET: preserve(), REDIS_URL: preserve(), RESEND_API_KEY: preserve(), RESEND_API_NAME: preserve(), SECRET_KEY: preserve(), SITE_DESCRIPTION: preserve(), SITE_NAME: preserve(), STRIPE_PUBLISHABLE_KEY: preserve(), STRIPE_SECRET_KEY: preserve(), STRIPE_WEBHOOK_SECRET: preserve(), SUPABASE_ANON_KEY: preserve(), SUPABASE_SERVICE_ROLE_KEY: preserve(), SUPABASE_STORAGE_ACCESS_KEY_ID: preserve(), SUPABASE_STORAGE_BUCKET: preserve(), SUPABASE_STORAGE_ENDPOINT: preserve(), SUPABASE_STORAGE_REGION: preserve(), SUPABASE_STORAGE_SECRET_ACCESS_KEY: preserve(), SUPABASE_URL: preserve() },
  });
  const worker = service("worker", {
    source: sadaBackend,
    start: "celery -A config worker --loglevel=info --pool=solo",
    replicas: { "sfo": 1 },
    env: { ALLOWED_HOSTS: preserve(), API_RATE_LIMIT_ANON: preserve(), API_RATE_LIMIT_USER: preserve(), CELERY_BROKER_URL: preserve(), CELERY_RESULT_BACKEND: preserve(), CONTACT_EMAIL: preserve(), CORS_ALLOWED_ORIGINS: preserve(), DATABASE_URL: preserve(), DEBUG: preserve(), DEFAULT_FROM_EMAIL: preserve(), DEMO_MODE: preserve(), DJANGO_SETTINGS_MODULE: preserve(), EMAIL_REPLY_TO: preserve(), FRONTEND_URL: preserve(), GOOGLE_OAUTH_CLIENT_ID: preserve(), GOOGLE_OAUTH_CLIENT_SECRET: preserve(), JWT_ACCESS_TOKEN_LIFETIME_MINUTES: preserve(), JWT_REFRESH_TOKEN_LIFETIME_DAYS: preserve(), MODEMPAY_MERCHANT_ID: preserve(), MODEMPAY_PUBLIC_API_KEY: preserve(), MODEMPAY_SECRET_API_KEY: preserve(), MODEMPAY_WEBHOOK_SECRET: preserve(), REDIS_URL: preserve(), RESEND_API_KEY: preserve(), RESEND_API_NAME: preserve(), SECRET_KEY: preserve(), SITE_DESCRIPTION: preserve(), SITE_NAME: preserve(), STRIPE_PUBLISHABLE_KEY: preserve(), STRIPE_SECRET_KEY: preserve(), STRIPE_WEBHOOK_SECRET: preserve(), SUPABASE_ANON_KEY: preserve(), SUPABASE_SERVICE_ROLE_KEY: preserve(), SUPABASE_STORAGE_ACCESS_KEY_ID: preserve(), SUPABASE_STORAGE_BUCKET: preserve(), SUPABASE_STORAGE_ENDPOINT: preserve(), SUPABASE_STORAGE_REGION: preserve(), SUPABASE_STORAGE_SECRET_ACCESS_KEY: preserve(), SUPABASE_URL: preserve() },
  });

  // Scheduler for config/celery.py's periodic beat_schedule (donation/payout
  // reconciliation sweeps + the campaign lifecycle sweep) -- previously an
  // empty, never-deployed service shell with no source/vars, so its env is
  // built from ref()s into `worker` rather than preserve() (nothing to
  // preserve on a service that's never had these vars set).
  const beat = service("beat", {
    source: sadaBackend,
    start: "celery -A config beat --loglevel=info",
    replicas: { "sfo": 1 },
    env: {
      ALLOWED_HOSTS: ref(worker, "ALLOWED_HOSTS"),
      API_RATE_LIMIT_ANON: ref(worker, "API_RATE_LIMIT_ANON"),
      API_RATE_LIMIT_USER: ref(worker, "API_RATE_LIMIT_USER"),
      CELERY_BROKER_URL: ref(worker, "CELERY_BROKER_URL"),
      CELERY_RESULT_BACKEND: ref(worker, "CELERY_RESULT_BACKEND"),
      CONTACT_EMAIL: ref(worker, "CONTACT_EMAIL"),
      CORS_ALLOWED_ORIGINS: ref(worker, "CORS_ALLOWED_ORIGINS"),
      DATABASE_URL: ref(worker, "DATABASE_URL"),
      DEBUG: ref(worker, "DEBUG"),
      DEFAULT_FROM_EMAIL: ref(worker, "DEFAULT_FROM_EMAIL"),
      DEMO_MODE: ref(worker, "DEMO_MODE"),
      DJANGO_SETTINGS_MODULE: ref(worker, "DJANGO_SETTINGS_MODULE"),
      EMAIL_REPLY_TO: ref(worker, "EMAIL_REPLY_TO"),
      FRONTEND_URL: ref(worker, "FRONTEND_URL"),
      GOOGLE_OAUTH_CLIENT_ID: ref(worker, "GOOGLE_OAUTH_CLIENT_ID"),
      GOOGLE_OAUTH_CLIENT_SECRET: ref(worker, "GOOGLE_OAUTH_CLIENT_SECRET"),
      JWT_ACCESS_TOKEN_LIFETIME_MINUTES: ref(worker, "JWT_ACCESS_TOKEN_LIFETIME_MINUTES"),
      JWT_REFRESH_TOKEN_LIFETIME_DAYS: ref(worker, "JWT_REFRESH_TOKEN_LIFETIME_DAYS"),
      MODEMPAY_MERCHANT_ID: ref(worker, "MODEMPAY_MERCHANT_ID"),
      MODEMPAY_PUBLIC_API_KEY: ref(worker, "MODEMPAY_PUBLIC_API_KEY"),
      MODEMPAY_SECRET_API_KEY: ref(worker, "MODEMPAY_SECRET_API_KEY"),
      MODEMPAY_WEBHOOK_SECRET: ref(worker, "MODEMPAY_WEBHOOK_SECRET"),
      REDIS_URL: ref(worker, "REDIS_URL"),
      RESEND_API_KEY: ref(worker, "RESEND_API_KEY"),
      RESEND_API_NAME: ref(worker, "RESEND_API_NAME"),
      SECRET_KEY: ref(worker, "SECRET_KEY"),
      SITE_DESCRIPTION: ref(worker, "SITE_DESCRIPTION"),
      SITE_NAME: ref(worker, "SITE_NAME"),
      STRIPE_PUBLISHABLE_KEY: ref(worker, "STRIPE_PUBLISHABLE_KEY"),
      STRIPE_SECRET_KEY: ref(worker, "STRIPE_SECRET_KEY"),
      STRIPE_WEBHOOK_SECRET: ref(worker, "STRIPE_WEBHOOK_SECRET"),
      SUPABASE_ANON_KEY: ref(worker, "SUPABASE_ANON_KEY"),
      SUPABASE_SERVICE_ROLE_KEY: ref(worker, "SUPABASE_SERVICE_ROLE_KEY"),
      SUPABASE_STORAGE_ACCESS_KEY_ID: ref(worker, "SUPABASE_STORAGE_ACCESS_KEY_ID"),
      SUPABASE_STORAGE_BUCKET: ref(worker, "SUPABASE_STORAGE_BUCKET"),
      SUPABASE_STORAGE_ENDPOINT: ref(worker, "SUPABASE_STORAGE_ENDPOINT"),
      SUPABASE_STORAGE_REGION: ref(worker, "SUPABASE_STORAGE_REGION"),
      SUPABASE_STORAGE_SECRET_ACCESS_KEY: ref(worker, "SUPABASE_STORAGE_SECRET_ACCESS_KEY"),
      SUPABASE_URL: ref(worker, "SUPABASE_URL"),
    },
  });

  return project("dolelma", {
    resources: [web, worker, beat, Redis, redisVolume],
  });
});

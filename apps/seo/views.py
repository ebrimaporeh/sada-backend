"""Server-rendered SEO surfaces for a client-only (no-SSR) React SPA.

The frontend is a plain Vite SPA -- every route serves the same static
index.html, so a client-side <title>/meta update (see the frontend's page
meta hook) never reaches a crawler that doesn't execute JavaScript.
WhatsApp/Facebook/LinkedIn/Slack's link-preview bots are exactly that kind
of crawler. The views here exist specifically to give those bots real,
server-rendered og:*/twitter:* tags for the two dynamic, shareable content
types (campaigns, campaigner profiles) without requiring a full SSR
rewrite of the frontend:

    /share/campaigns/<slug>/       -> apps/seo/templates/seo/share_preview.html
    /share/campaigners/<id>/       -> same template

Each share URL renders a tiny HTML page with the real tags baked in
server-side, then immediately sends a real visitor on to the actual SPA
page via a 0-second meta-refresh (crawlers don't follow that, so they only
ever see the tags). The frontend's Share button links to these URLs
instead of the SPA route directly.
"""
from django.conf import settings
from django.shortcuts import render, redirect
from django.views import View
from django.http import Http404, HttpResponse

from apps.common.models import SiteSettings
import services.campaign_service as campaign_service
import services.user_service as user_service
import services.vision_service as vision_service

DESCRIPTION_MAX_LENGTH = 200


def _frontend_url(path=''):
    base = getattr(settings, 'FRONTEND_URL', '').rstrip('/')
    return f'{base}{path}'


def _absolute_media_url(request, field):
    if not field:
        return None
    return request.build_absolute_uri(field.url)


def _default_og_image(request):
    """Falls back to the admin-configured logo (the on-background variant
    exists specifically for this — see SiteSettings.logo_with_background's
    help_text) when a campaign/campaigner has no image of their own."""
    site = SiteSettings.get_solo()
    return _absolute_media_url(request, site.logo_with_background or site.logo)


def _truncate(text, length=DESCRIPTION_MAX_LENGTH):
    text = (text or '').strip()
    if len(text) <= length:
        return text
    return text[:length].rsplit(' ', 1)[0] + '…'


def _render_share_preview(request, *, title, description, image_url, page_url, og_type='website'):
    site_name = SiteSettings.get_solo().site_name
    return render(request, 'seo/share_preview.html', {
        'title': title,
        'description': description or site_name,
        'image_url': image_url or _default_og_image(request) or '',
        'page_url': page_url,
        'og_type': og_type,
        'site_name': site_name,
    })


def _campaign_cover_field(campaign):
    """Mirrors the frontend's own fallback order (cover_image -> gallery's
    is_cover image -> first gallery image) so the two never disagree on
    which image is "the" campaign image."""
    if campaign.cover_image:
        return campaign.cover_image
    gallery_cover = campaign.images.filter(is_cover=True).first()
    if gallery_cover:
        return gallery_cover.image
    first_image = campaign.images.first()
    return first_image.image if first_image else None


class CampaignSharePreviewView(View):
    def get(self, request, slug):
        page_url = _frontend_url(f'/campaigns/{slug}')
        campaign = campaign_service.get_public_campaigns().filter(slug=slug).first()
        if campaign is None:
            # Not public (draft/rejected/unknown) -- no preview data to
            # leak; just send along to the SPA, which renders its own
            # not-found state.
            return redirect(page_url)

        return _render_share_preview(
            request,
            title=campaign.title,
            description=_truncate(campaign.short_description),
            image_url=_absolute_media_url(request, _campaign_cover_field(campaign)),
            page_url=page_url,
        )


class CampaignerSharePreviewView(View):
    def get(self, request, id):
        page_url = _frontend_url(f'/campaigners/{id}')
        try:
            campaigner = user_service.get_public_campaigner(id)
        except Http404:
            return redirect(page_url)

        bio = campaigner.bio or f'{campaigner.campaign_count} campaign(s) on {SiteSettings.get_solo().site_name}.'
        return _render_share_preview(
            request,
            title=campaigner.full_name,
            description=_truncate(bio),
            image_url=_absolute_media_url(request, campaigner.avatar),
            page_url=page_url,
            og_type='profile',
        )


class VisionTopicSharePreviewView(View):
    def get(self, request, slug):
        page_url = _frontend_url(f'/vision/{slug}')
        try:
            topic = vision_service.get_published_topic(slug)
        except Http404:
            return redirect(page_url)

        return _render_share_preview(
            request,
            title=topic.title,
            description=_truncate(topic.summary or topic.current_state),
            image_url=None,  # no image field on VisionTopic -- falls back to the site logo
            page_url=page_url,
            og_type='article',
        )


# ─── Sitemap & robots.txt ──────────────────────────────────────────────────
# Deliberately served from this (backend) domain, not the frontend's static
# host -- the frontend is a plain Vite build with no server code of its own
# to generate a sitemap from live campaign/campaigner data. The frontend's
# own robots.txt (a static file, since it's the canonical site root crawlers
# check first) points its `Sitemap:` directive at this endpoint.

STATIC_SITEMAP_ENTRIES = [
    # (path, changefreq, priority)
    ('/', 'daily', '1.0'),
    ('/campaigns', 'hourly', '0.9'),
    ('/campaigners', 'daily', '0.6'),
    ('/categories', 'weekly', '0.5'),
    ('/zakat', 'monthly', '0.5'),
    ('/vision', 'weekly', '0.5'),
    ('/about', 'monthly', '0.4'),
    ('/help', 'monthly', '0.3'),
    ('/trust-safety', 'monthly', '0.3'),
    ('/privacy', 'yearly', '0.2'),
    ('/terms', 'yearly', '0.2'),
]


class SitemapView(View):
    def get(self, request):
        entries = [
            {'loc': _frontend_url(path), 'lastmod': None, 'changefreq': changefreq, 'priority': priority}
            for path, changefreq, priority in STATIC_SITEMAP_ENTRIES
        ]

        for campaign in campaign_service.get_public_campaigns():
            entries.append({
                'loc': _frontend_url(f'/campaigns/{campaign.slug}'),
                'lastmod': campaign.updated_at,
                'changefreq': 'daily',
                'priority': '0.8',
            })

        for campaigner in user_service.get_public_campaigners():
            entries.append({
                'loc': _frontend_url(f'/campaigners/{campaigner.id}'),
                'lastmod': None,
                'changefreq': 'weekly',
                'priority': '0.5',
            })

        for topic in vision_service.get_published_topics().only('slug', 'updated_at'):
            entries.append({
                'loc': _frontend_url(f'/vision/{topic.slug}'),
                'lastmod': topic.updated_at,
                'changefreq': 'monthly',
                'priority': '0.4',
            })

        return render(request, 'seo/sitemap.xml', {'entries': entries}, content_type='application/xml')


ROBOTS_TXT = """User-agent: *
Disallow: /
"""


def robots_txt(request):
    # This is the API domain -- nothing here is a page meant to be indexed.
    # The frontend's own robots.txt (a static file in its build, since it's
    # the canonical site root) is what actually allows/disallows real pages
    # and points crawlers at the sitemap above.
    return HttpResponse(ROBOTS_TXT, content_type='text/plain')

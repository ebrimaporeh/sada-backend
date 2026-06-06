"""
Download and attach real images to seeded campaigns.

Primary source : loremflickr.com  (Flickr Creative Commons, no API key)
Fallback source: picsum.photos     (deterministic placeholder)

Usage:
    python manage.py seed_campaign_images
    python manage.py seed_campaign_images --force          # re-download even if images exist
    python manage.py seed_campaign_images --slug flood-relief-basse-2026
"""

import time
import requests
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand

# lock=N makes loremflickr return the same image for the same keyword+lock combo.
# We use lock=1 for cover, lock=11-13 for gallery images.
CAMPAIGN_CONFIG = {
    "flood-relief-basse-2026": {
        "cover":   "flood,disaster,africa,emergency",
        "gallery": [
            "flood,rescue,emergency,africa",
            "aid,food,distribution,relief",
            "displaced,people,shelter,africa",
        ],
    },
    "brikama-school-building-project": {
        "cover":   "classroom,school,africa,children",
        "gallery": [
            "school,construction,building,africa",
            "children,learning,studying,africa",
            "primary,school,africa,education",
        ],
    },
    "help-fatou-get-kidney-surgery": {
        "cover":   "hospital,patient,medical,doctor",
        "gallery": [
            "surgery,operating,room,hospital",
            "patient,hospital,care,nursing",
            "medicine,healthcare,africa,clinic",
        ],
    },
    "memorial-late-omar-saho": {
        "cover":   "memorial,garden,flowers,tribute",
        "gallery": [
            "garden,flowers,peaceful,nature",
            "memorial,candles,flowers,remembrance",
            "park,bench,quiet,garden",
        ],
    },
    "kanifing-market-expansion": {
        "cover":   "women,market,africa,business",
        "gallery": [
            "market,stall,vendor,africa",
            "women,entrepreneur,africa,trade",
            "fabric,cloth,market,colorful",
        ],
    },
    "solar-panels-jinack-village-school": {
        "cover":   "solar,panels,africa,energy",
        "gallery": [
            "solar,installation,rural,africa",
            "school,electricity,children,technology",
            "renewable,energy,solar,village",
        ],
    },
    "gambia-u17-football-afcon": {
        "cover":   "football,soccer,africa,youth",
        "gallery": [
            "football,team,youth,training",
            "soccer,match,africa,players",
            "stadium,sport,africa,youth",
        ],
    },
    "girls-scholarship-fund-gambia": {
        "cover":   "girls,school,africa,education",
        "gallery": [
            "girls,studying,books,classroom",
            "scholarship,education,students,africa",
            "school,uniform,girls,africa",
        ],
    },
    "baby-modou-heart-surgery": {
        "cover":   "baby,infant,hospital,medical",
        "gallery": [
            "baby,care,hospital,nurse",
            "infant,pediatric,doctor,care",
            "hospital,child,medical,treatment",
        ],
    },
    "farafenni-clean-water-project": {
        "cover":   "water,well,africa,borehole",
        "gallery": [
            "water,pump,village,africa",
            "clean,water,community,africa",
            "water,drinking,africa,people",
        ],
    },
    "bakau-mosque-renovation": {
        "cover":   "mosque,africa,islamic,architecture",
        "gallery": [
            "mosque,interior,prayer,islam",
            "mosque,renovation,construction,building",
            "mosque,community,west,africa",
        ],
    },
}

REQUEST_TIMEOUT = 20
RATE_LIMIT_DELAY = 1.5  # seconds between downloads


def _fetch(keywords: str, width: int, height: int, lock: int) -> bytes | None:
    """Try loremflickr first, fall back to picsum."""
    # loremflickr — real topic-relevant images from Flickr CC
    url = f"https://loremflickr.com/{width}/{height}/{keywords}?lock={lock}"
    try:
        r = requests.get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        if r.status_code == 200 and r.headers.get("content-type", "").startswith("image/"):
            return r.content
    except Exception:
        pass

    # picsum — deterministic placeholder (beautiful, but generic)
    slug_seed = keywords.split(",")[0].replace(" ", "-")
    url = f"https://picsum.photos/seed/{slug_seed}-{lock}/{width}/{height}"
    try:
        r = requests.get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        if r.status_code == 200 and r.headers.get("content-type", "").startswith("image/"):
            return r.content
    except Exception:
        pass

    return None


class Command(BaseCommand):
    help = "Download real images from the internet and attach them to seeded campaigns"

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Re-download and overwrite images even if they already exist",
        )
        parser.add_argument(
            "--slug",
            type=str,
            default=None,
            help="Only process this campaign slug",
        )

    def handle(self, *args, **options):
        from apps.campaigns.models import Campaign, CampaignImage

        force = options["force"]
        only_slug = options.get("slug")
        slugs = [only_slug] if only_slug else list(CAMPAIGN_CONFIG.keys())

        total = len(slugs)
        self.stdout.write(f"Processing {total} campaign(s)…\n")

        for idx, slug in enumerate(slugs, start=1):
            config = CAMPAIGN_CONFIG.get(slug)
            if not config:
                self.stdout.write(self.style.WARNING(f"[{idx}/{total}] No config for '{slug}' — skipping"))
                continue

            try:
                campaign = Campaign.objects.get(slug=slug)
            except Campaign.DoesNotExist:
                self.stdout.write(self.style.WARNING(f"[{idx}/{total}] Campaign not found: '{slug}'"))
                continue

            if campaign.cover_image and not force:
                self.stdout.write(
                    f"[{idx}/{total}] '{campaign.title}' already has images — skipping (use --force to overwrite)"
                )
                continue

            self.stdout.write(self.style.HTTP_INFO(f"[{idx}/{total}] {campaign.title}"))

            # ── Cover ─────────────────────────────────────────────────────────
            self.stdout.write("  → Downloading cover …")
            data = _fetch(config["cover"], 1200, 800, lock=1)
            if data:
                filename = f"{slug}-cover.jpg"
                campaign.cover_image.save(filename, ContentFile(data), save=True)
                self.stdout.write(self.style.SUCCESS(f"  ✓ Cover saved ({len(data) // 1024} KB)"))

                if force:
                    campaign.images.filter(is_cover=True).delete()

                CampaignImage.objects.get_or_create(
                    campaign=campaign,
                    is_cover=True,
                    defaults={"image": campaign.cover_image.name, "order": 0},
                )
            else:
                self.stdout.write(self.style.ERROR("  ✗ Cover download failed"))

            time.sleep(RATE_LIMIT_DELAY)

            # ── Gallery ───────────────────────────────────────────────────────
            if force:
                campaign.images.filter(is_cover=False).delete()

            for i, gkw in enumerate(config.get("gallery", []), start=1):
                self.stdout.write(f"  → Downloading gallery {i} …")
                data = _fetch(gkw, 800, 600, lock=10 + i)
                if data:
                    gallery_obj = CampaignImage(campaign=campaign, order=i, is_cover=False)
                    gallery_obj.image.save(f"{slug}-gallery-{i}.jpg", ContentFile(data), save=True)
                    self.stdout.write(self.style.SUCCESS(f"  ✓ Gallery {i} saved ({len(data) // 1024} KB)"))
                else:
                    self.stdout.write(self.style.ERROR(f"  ✗ Gallery {i} download failed"))

                time.sleep(RATE_LIMIT_DELAY)

            self.stdout.write("")

        self.stdout.write(self.style.SUCCESS("All done!"))

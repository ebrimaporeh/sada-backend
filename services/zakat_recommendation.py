"""Recommends campaigns eligible to receive Zakat.

Zakat has stricter eligibility rules than an ordinary donation: per the
Qur'an (9:60), it may only go to one of eight categories of recipients —
the poor (al-fuqara), the needy (al-masakin), Zakat administrators,
those whose hearts are to be reconciled, freeing captives, the
debt-ridden (al-gharimin), those striving in Allah's cause
(fi sabilillah), and stranded travelers (ibn al-sabil) — and it must
never fund anything haram.

This module has no access to a campaign's actual finances or a
scholarly assessment of the beneficiary's need, so it can't rule on
eligibility the way a scholar reviewing a specific case could. Instead
it hard-excludes campaign categories and keywords that clearly fall
outside the eight categories or are plainly haram, then ranks what's
left by how closely its category maps to the core poverty-relief
categories (fuqara/masakin) and how much funding it still needs — so a
donor gets a shortlist to review themselves, not an authoritative fatwa.
"""
from apps.campaigns.models import Campaign

# Campaign categories that are never valid Zakat recipients even though
# they're perfectly fine for ordinary (non-Zakat) donations — none of
# them map to any of the eight Qur'anic categories (9:60).
EXCLUDED_CATEGORY_SLUGS = {
    'memorial',   # honors/remembers the dead — not a living recipient
    'religious',  # mosque/church construction: the scholarly majority
                  # excludes building projects from zakat's fisabilillah,
                  # and this category may also fund non-Islamic worship
                  # (churches), which zakat can never do
    'sports',     # youth/fitness development, not poverty relief
}

# Keyword screening across title/description/story — a defensive net for
# anything clearly haram regardless of category (gambling, alcohol,
# interest-based lending, etc.), since a campaign's category alone can't
# guarantee what it's actually raising money for.
HARAM_KEYWORDS = [
    'casino', 'gambling', 'lottery', 'sports bet', 'betting', 'wager',
    'alcohol', 'beer', 'wine', 'liquor', 'brewery', 'nightclub',
    'pork', 'riba', 'usury', 'interest-bearing loan',
]

# Maps each remaining category to the Qur'anic recipient category it
# most directly serves, and a priority weight (higher = closer to the
# core fuqara/masakin poverty-relief categories most Zakat funds).
CATEGORY_ASNAF = {
    'medical':      ('al-fuqara / al-masakin — the poor and needy', 3),
    'disaster':     ('ibn al-sabil / al-masakin — the stranded and needy', 3),
    'agriculture':  ('al-fuqara / al-masakin — the poor and needy', 3),
    'women':        ('al-fuqara / al-masakin — the poor and needy', 3),
    'charity':      ('al-fuqara / al-masakin — the poor and needy', 2),
    'business':     ('al-gharimin — livelihood support for those in need', 2),
    'community':    ('fi sabilillah — community benefit', 1),
    'education':    ('fi sabilillah — knowledge and self-sufficiency', 1),
    'other':        ('unspecified — review individually', 0),
}


def _has_haram_keyword(campaign) -> bool:
    text = f'{campaign.title} {campaign.short_description} {campaign.story}'.lower()
    return any(keyword in text for keyword in HARAM_KEYWORDS)


def is_zakat_eligible(campaign) -> bool:
    """Whether `campaign` passes the automated Zakat screen. This is a
    starting shortlist, not a fatwa — donors should still use their own
    judgment (or ask a scholar) before directing Zakat to any campaign."""
    if campaign.is_anonymous:
        return False
    if not campaign.category or campaign.category.slug in EXCLUDED_CATEGORY_SLUGS:
        return False
    if _has_haram_keyword(campaign):
        return False
    return True


def get_recommended_campaigns(limit=10):
    """Public, currently-active campaigns eligible for Zakat, ranked by
    how closely they align with the core poverty-relief categories and
    how much funding they still need."""
    public_statuses = [Campaign.Status.ACTIVE, Campaign.Status.APPROVED]
    candidates = (
        Campaign.objects
        .filter(status__in=public_statuses)
        .exclude(category__isnull=True)
        .select_related('category')
    )
    eligible = [c for c in candidates if is_zakat_eligible(c)]

    def sort_key(campaign):
        _, priority = CATEGORY_ASNAF.get(campaign.category.slug, ('', 0))
        percent_funded = float(campaign.raised) / float(campaign.goal) if campaign.goal else 1.0
        return (-priority, percent_funded)

    eligible.sort(key=sort_key)
    return eligible[:limit]

import random
import uuid
from django.utils import timezone
from django.db import models
from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework import status


def success_response(data, message='Success.', status_code=status.HTTP_200_OK):
    return Response({'success': True, 'message': message, 'data': data}, status=status_code)


def error_response(message, errors=None, status_code=status.HTTP_400_BAD_REQUEST):
    return Response({'success': False, 'message': message, 'errors': errors or {}}, status=status_code)


def get_categories():
    from apps.campaigns.models import Category
    from apps.donations.models import Donation
    return Category.objects.filter(is_active=True).annotate(
        total_donated=models.Sum(
            'campaigns__donations__amount',
            filter=models.Q(campaigns__donations__status=Donation.Status.PAID),
        )
    ).order_by(models.F('total_donated').desc(nulls_last=True), 'name')


def get_public_campaigns(filters=None):
    from apps.campaigns.models import Campaign
    qs = Campaign.objects.filter(status__in=[Campaign.Status.ACTIVE, Campaign.Status.APPROVED]).select_related('owner', 'category')

    if filters:
        if filters.get('category'):
            qs = qs.filter(category__slug=filters['category'])
        if filters.get('region'):
            qs = qs.filter(region=filters['region'])
        if filters.get('search'):
            q = filters['search']
            qs = qs.filter(
                models.Q(title__icontains=q)
                | models.Q(short_description__icontains=q)
                | models.Q(beneficiary__icontains=q)
            )
        if filters.get('urgent'):
            qs = qs.filter(is_urgent=True)
        if filters.get('owner'):
            # is_anonymous=False here too — an anonymous campaign must never
            # be reachable via its owner's id, or that defeats the whole
            # point of the campaign's own anonymity setting.
            qs = qs.filter(owner_id=filters['owner'], is_anonymous=False)

    return qs.order_by('-is_featured', '-created_at')


def get_featured_campaigns():
    from apps.campaigns.models import Campaign
    visible = [Campaign.Status.ACTIVE, Campaign.Status.APPROVED]
    qs = Campaign.objects.filter(status__in=visible).select_related('owner', 'category')
    featured = list(qs.filter(is_featured=True).order_by('-approved_at')[:4])
    if len(featured) < 4:
        seen = {c.pk for c in featured}
        extra = qs.filter(is_urgent=True).exclude(pk__in=seen).order_by('-created_at')[:4 - len(featured)]
        featured += list(extra)
    if len(featured) < 4:
        seen = {c.pk for c in featured}
        extra = qs.exclude(pk__in=seen).order_by('-created_at')[:4 - len(featured)]
        featured += list(extra)
    return featured


# Priority weights for the homepage hero pick, strictly ordered per product
# spec: verified owner > urgent > disaster relief > medical/health. Powers
# of 2 are deliberate, not just "biggish numbers" -- they guarantee that
# rank ordering, e.g. a verified-only campaign (8) always outweighs a
# campaign matching every criterion below it combined (4+2+1=7), so the
# *order* holds even when campaigns satisfy different combinations of
# criteria, not just "verified counts for more on average."
HERO_WEIGHT_VERIFIED_OWNER = 8
HERO_WEIGHT_URGENT = 4
HERO_WEIGHT_DISASTER_CATEGORY = 2
HERO_WEIGHT_MEDICAL_CATEGORY = 1
HERO_WEIGHT_BASE = 1  # every eligible campaign gets a nonzero chance
HERO_CATEGORY_SLUGS = {'disaster': HERO_WEIGHT_DISASTER_CATEGORY, 'medical': HERO_WEIGHT_MEDICAL_CATEGORY}


def _hero_weight(campaign):
    weight = HERO_WEIGHT_BASE
    if campaign.owner.is_verified:
        weight += HERO_WEIGHT_VERIFIED_OWNER
    if campaign.is_urgent:
        weight += HERO_WEIGHT_URGENT
    if campaign.category_id and campaign.category.slug in HERO_CATEGORY_SLUGS:
        weight += HERO_CATEGORY_SLUGS[campaign.category.slug]
    return weight


def get_hero_campaign():
    """Weighted-random pick for the homepage hero card.

    Not the same list get_featured_campaigns() returns (that's a curated/
    fallback grid shown elsewhere on the homepage) -- this is a single
    campaign, re-rolled on every call rather than cached or deterministic,
    so reloading the homepage (as the same visitor or a different one) can
    surface a different eligible campaign each time. "Prioritize" here means
    weighted odds, not a fixed sort: a campaign matching more/higher-ranked
    criteria is more *likely* to come up, not guaranteed to, which is what
    keeps the hero varied instead of freezing on one campaign indefinitely.
    """
    from apps.campaigns.models import Campaign
    visible = [Campaign.Status.ACTIVE, Campaign.Status.APPROVED]
    campaigns = list(
        Campaign.objects.filter(status__in=visible).select_related('owner', 'category')
    )
    if not campaigns:
        return None
    weights = [_hero_weight(c) for c in campaigns]
    return random.choices(campaigns, weights=weights, k=1)[0]


def get_campaign_by_slug(slug):
    from apps.campaigns.models import Campaign
    return get_object_or_404(
        Campaign.objects.select_related('owner', 'category').prefetch_related('images', 'updates'),
        slug=slug,
        status__in=[
            Campaign.Status.ACTIVE,
            Campaign.Status.APPROVED,
            Campaign.Status.COMPLETED,
            Campaign.Status.PENDING,
        ],
    )


def record_view(slug):
    """Increment views_count for a publicly-visible campaign by slug, and
    return it (or None for an unknown/non-public slug) so the caller can
    fire a campaign_viewed analytics event alongside — see
    apps.events.models.Event. This is a product-engagement signal, not an
    admin-worthy action, so it deliberately never touches apps.audit.

    Called explicitly by the frontend when the public campaign detail page
    is actually viewed — kept separate from CampaignDetailView's GET so
    other pages that happen to reuse the same campaign-fetch hook (donate,
    donate-success) don't inflate the count as a side effect of fetching data.
    Silently no-ops for an unknown/non-public slug rather than raising, since
    a dropped view-tracking beacon shouldn't surface as a user-facing error.
    """
    from apps.campaigns.models import Campaign
    public_statuses = [
        Campaign.Status.ACTIVE, Campaign.Status.APPROVED,
        Campaign.Status.COMPLETED, Campaign.Status.PENDING,
    ]
    updated = Campaign.objects.filter(slug=slug, status__in=public_statuses).update(
        views_count=models.F('views_count') + 1,
    )
    if not updated:
        return None
    return Campaign.objects.filter(slug=slug).first()


def get_owner_campaigns(user):
    """Every campaign this user can manage: their own individual campaigns
    (organization=None), plus every campaign belonging to an organization
    they're a member of -- not just ones they personally created. Name kept
    for compat with existing call sites; "owner" now really means "has
    access to manage," see get_owner_campaign's required_permission for how
    specific *actions* are gated beyond that."""
    from django.db.models import Q
    from apps.campaigns.models import Campaign
    from apps.organizations.models import OrganizationMembership
    org_ids = OrganizationMembership.objects.filter(user=user).values_list('organization_id', flat=True)
    return Campaign.objects.filter(
        Q(owner=user, organization__isnull=True) | Q(organization_id__in=org_ids)
    ).select_related('category').order_by('-created_at')


def get_owner_campaign(user, slug, required_permission=None):
    """Fetches a campaign this user can act on. Individual campaign
    (organization=None): only the creator (`owner`) qualifies, full stop --
    required_permission is irrelevant there, identical to the pre-org-model
    behavior. Org-owned campaign: the acting user must currently be a
    member, and if required_permission is given (one of
    apps.organizations.permissions.OrganizationPermission), their role must
    grant it -- otherwise PermissionDenied, distinct from "campaign doesn't
    exist/isn't yours" (Http404), so the frontend can tell a member "you
    don't have permission" instead of a confusing not-found.
    """
    from apps.campaigns.models import Campaign
    from services.organization_service import check_campaign_access

    campaign = get_object_or_404(Campaign, slug=slug)
    check_campaign_access(user, campaign, required_permission)
    return campaign


def create_campaign(user, validated_data, organization=None):
    from apps.campaigns.models import Campaign, Category
    category_id = validated_data.pop('category_id', None)
    category = None
    if category_id:
        category = Category.objects.filter(id=category_id).first()

    campaign = Campaign.objects.create(
        owner=user,
        organization=organization,
        category=category,
        status=Campaign.Status.ACTIVE,
        approved_at=timezone.now(),
        **validated_data,
    )
    return campaign


def update_campaign(campaign, validated_data):
    from apps.campaigns.models import Category
    category_id = validated_data.pop('category_id', None)
    if category_id is not None:
        campaign.category = Category.objects.filter(id=category_id).first()

    for attr, value in validated_data.items():
        setattr(campaign, attr, value)
    campaign.save()
    return campaign


def toggle_pause_campaign(user, slug):
    from apps.campaigns.models import Campaign
    from apps.organizations.permissions import OrganizationPermission
    campaign = get_owner_campaign(user, slug, required_permission=OrganizationPermission.PAUSE_RESUME_CAMPAIGN)
    if campaign.status == Campaign.Status.ACTIVE:
        campaign.status = Campaign.Status.SUSPENDED
    elif campaign.status == Campaign.Status.SUSPENDED:
        campaign.status = Campaign.Status.ACTIVE
    else:
        raise ValueError('Only active or paused campaigns can be toggled.')
    campaign.save(update_fields=['status'])
    return campaign


def delete_campaign(campaign):
    if campaign.status not in (campaign.Status.DRAFT, campaign.Status.REJECTED):
        raise ValueError('Only draft or rejected campaigns can be deleted.')
    campaign.delete()


def upload_cover(campaign, image_file):
    if not image_file:
        raise ValueError('No image provided.')
    from services.image_compression import process_image
    campaign.cover_image = process_image(image_file, profile='campaign_cover')
    campaign.save(update_fields=['cover_image'])
    return campaign


def update_campaign_media(campaign, cover_file=None, gallery_files=None):
    from apps.campaigns.models import Campaign, CampaignImage
    from django.db.models import Max
    from services.image_compression import process_image

    if cover_file:
        compressed_cover = process_image(cover_file, profile='campaign_cover')
        campaign.cover_image = compressed_cover
        campaign.save(update_fields=['cover_image'])
        campaign.images.filter(is_cover=True).delete()
        CampaignImage.objects.create(
            campaign=campaign,
            image=compressed_cover,
            order=0,
            is_cover=True,
        )

    if gallery_files:
        max_order = campaign.images.filter(is_cover=False).aggregate(
            m=Max('order')
        )['m'] or 0
        for i, f in enumerate(gallery_files, start=1):
            CampaignImage.objects.create(
                campaign=campaign,
                image=process_image(f, profile='campaign_gallery'),
                order=max_order + i,
                is_cover=False,
            )

    return get_object_or_404(
        Campaign.objects.prefetch_related('images', 'updates').select_related('category'),
        pk=campaign.pk,
    )


def delete_campaign_image(user, slug, image_id):
    from apps.campaigns.models import Campaign, CampaignImage
    from apps.organizations.permissions import OrganizationPermission
    campaign = get_owner_campaign(user, slug, required_permission=OrganizationPermission.EDIT_CAMPAIGN)
    image = get_object_or_404(CampaignImage, pk=image_id, campaign=campaign)
    image.delete()
    return get_object_or_404(
        Campaign.objects.prefetch_related('images', 'updates').select_related('category'),
        pk=campaign.pk,
    )


def add_campaign_update(campaign, user, title, content, images=None):
    from apps.campaigns.models import CampaignUpdate, CampaignUpdateImage
    from services.image_compression import process_image
    update = CampaignUpdate.objects.create(
        campaign=campaign,
        posted_by=user,
        title=title,
        content=content,
    )

    if images:
        for idx, image in enumerate(images):
            CampaignUpdateImage.objects.create(
                update=update,
                image=process_image(image, profile='campaign_update'),
                order=idx,
            )

    _notify_donors_of_update(campaign, update)
    return update


def update_campaign_update(campaign, update_id, user, title=None, content=None, images=None, images_to_remove=None):
    from apps.campaigns.models import CampaignUpdate, CampaignUpdateImage
    from django.shortcuts import get_object_or_404
    from services.image_compression import process_image
    update = get_object_or_404(CampaignUpdate, id=update_id, campaign=campaign)
    if update.posted_by != user:
        raise PermissionError('You can only edit your own updates.')

    if title is not None:
        update.title = title
    if content is not None:
        update.content = content
    update.save()

    if images_to_remove:
        CampaignUpdateImage.objects.filter(id__in=images_to_remove, update=update).delete()

    if images:
        current_max_order = update.images.aggregate(max_order=models.Max('order'))['max_order'] or -1
        for idx, image in enumerate(images):
            CampaignUpdateImage.objects.create(
                update=update,
                image=process_image(image, profile='campaign_update'),
                order=current_max_order + idx + 1,
            )

    return update


def delete_campaign_update(campaign, update_id, user):
    from apps.campaigns.models import CampaignUpdate
    from django.shortcuts import get_object_or_404
    update = get_object_or_404(CampaignUpdate, id=update_id, campaign=campaign)
    if update.posted_by != user:
        raise PermissionError('You can only delete your own updates.')
    update.delete()


def _notify_donors_of_update(campaign, update):
    from apps.donations.models import Donation
    from apps.notifications.models import Notification
    # Donation's default ordering (-created_at) leaks into a
    # .values_list().distinct() query -- Django adds created_at to the
    # SELECT DISTINCT list to satisfy the implied ORDER BY, so this was
    # deduping on (donor_id, created_at) instead of donor_id alone, and a
    # donor with more than one paid donation got notified once per donation.
    # set() in Python is always correct regardless of DB backend/ordering.
    donor_users = set(
        Donation.objects.filter(campaign=campaign, status=Donation.Status.PAID, donor__isnull=False)
        .values_list('donor', flat=True)
    )
    notifications = [
        Notification(
            user_id=uid,
            notification_type=Notification.Type.CAMPAIGN_UPDATE,
            title=f'Update: {campaign.title}',
            message=update.title,
            link=f'/campaigns/{campaign.slug}',
        )
        for uid in donor_users
    ]
    if notifications:
        Notification.objects.bulk_create(notifications)


def create_campaign_report(campaign, user, reason, description, reporter_name='', reporter_phone=''):
    from apps.campaigns.models import CampaignReport

    if user:
        report, created = CampaignReport.objects.update_or_create(
            campaign=campaign,
            reported_by=user,
            defaults={
                'reason': reason,
                'description': description,
                'status': CampaignReport.Status.PENDING,
            },
        )
    else:
        report = CampaignReport.objects.create(
            campaign=campaign,
            reason=reason,
            description=description,
            reporter_name=reporter_name,
            reporter_phone=reporter_phone,
            status=CampaignReport.Status.PENDING,
        )
        created = True

    if created:
        from emails.tasks import send_new_report_notification_task
        send_new_report_notification_task.delay(str(report.id))

    return report


def get_all_campaigns(params=None):
    from apps.campaigns.models import Campaign
    # AdminCampaignListSerializer only needs category (for category_name) --
    # owner was only ever needed by the old, heavier serializer this feeds.
    qs = Campaign.objects.select_related('category').order_by('-created_at')
    if params:
        s = params.get('status')
        if s:
            qs = qs.filter(status=s)
        owner_id = params.get('owner')
        if owner_id:
            qs = qs.filter(owner_id=owner_id)
        organization_id = params.get('organization')
        if organization_id:
            qs = qs.filter(organization_id=organization_id)
        q = params.get('search')
        if q:
            qs = qs.filter(
                models.Q(title__icontains=q)
                | models.Q(owner__email__icontains=q)
                | models.Q(beneficiary__icontains=q)
                | models.Q(region__icontains=q)
            )
    return qs


def get_public_platform_stats():
    """Real trust-badge stats for the public homepage — no fabricated numbers."""
    from django.utils import timezone
    from datetime import timedelta
    from apps.campaigns.models import Campaign
    from apps.donations.models import Donation

    ever_public = [
        Campaign.Status.ACTIVE, Campaign.Status.APPROVED,
        Campaign.Status.COMPLETED, Campaign.Status.SUSPENDED,
    ]
    campaigns = Campaign.objects.filter(status__in=ever_public)

    agg = campaigns.aggregate(
        total_raised=models.Sum('raised'),
        total=models.Count('id'),
        funded=models.Count('id', filter=models.Q(raised__gte=models.F('goal'))),
        fundraisers=models.Count('owner', distinct=True),
    )

    paid_donations = Donation.objects.filter(status=Donation.Status.PAID, campaign__status__in=ever_public)
    # Count(..., distinct=True) rather than .values('donor').distinct().count()
    # -- the latter silently inflates this count, since Donation's default
    # ordering (-created_at) gets pulled into the SELECT DISTINCT list to
    # satisfy the implied ORDER BY, so it was really deduping on
    # (donor_id, created_at) instead of donor_id alone (same bug fixed in
    # _notify_donors_of_update above).
    known_donors = paid_donations.filter(donor__isnull=False).aggregate(
        c=models.Count('donor', distinct=True),
    )['c'] or 0
    guest_donations = paid_donations.filter(donor__isnull=True).count()

    week_ago = timezone.now() - timedelta(days=7)
    total_raised_this_week = paid_donations.filter(created_at__gte=week_ago).aggregate(
        total=models.Sum('amount'),
    )['total'] or 0

    total = agg['total'] or 0
    success_rate = round((agg['funded'] or 0) / total * 100) if total else 0

    return {
        'total_raised': agg['total_raised'] or 0,
        'total_raised_this_week': total_raised_this_week,
        'active_campaigns': campaigns.filter(status=Campaign.Status.ACTIVE).count(),
        'fundraisers_count': agg['fundraisers'] or 0,
        'donors_count': known_donors + guest_donations,
        'success_rate': success_rate,
    }


def get_campaign_stats():
    from apps.campaigns.models import Campaign
    counts = {row['status']: row['count'] for row in Campaign.objects.values('status').annotate(count=models.Count('id'))}
    return {
        'total_campaigns': sum(counts.values()),
        'active_campaigns': counts.get(Campaign.Status.ACTIVE, 0),
        'pending_campaigns': counts.get(Campaign.Status.PENDING, 0),
        'completed_campaigns': counts.get(Campaign.Status.COMPLETED, 0),
    }


def get_campaign_report_stats():
    from apps.campaigns.models import CampaignReport
    counts = {row['status']: row['count'] for row in CampaignReport.objects.values('status').annotate(count=models.Count('id'))}
    return {
        'total_reports': sum(counts.values()),
        'pending_reports': counts.get(CampaignReport.Status.PENDING, 0),
        'investigating_reports': counts.get(CampaignReport.Status.INVESTIGATING, 0),
        'resolved_reports': counts.get(CampaignReport.Status.RESOLVED, 0),
    }


def admin_action(campaign_id, action, reason, admin_user, notes=''):
    from apps.campaigns.models import Campaign
    from apps.notifications.models import Notification

    campaign = get_object_or_404(Campaign, pk=campaign_id)

    if action == 'approve':
        campaign.status = Campaign.Status.ACTIVE
        campaign.approved_at = timezone.now()
        campaign.rejection_reason = ''
        campaign.save()
        Notification.objects.create(
            user=campaign.owner,
            notification_type=Notification.Type.CAMPAIGN_APPROVED,
            title='Campaign Approved!',
            message=f'Your campaign "{campaign.title}" has been approved and is now live.',
            link=f'/campaigns/{campaign.slug}',
        )
    elif action == 'reject':
        campaign.status = Campaign.Status.REJECTED
        campaign.rejection_reason = reason
        campaign.save()
        Notification.objects.create(
            user=campaign.owner,
            notification_type=Notification.Type.CAMPAIGN_REJECTED,
            title='Campaign Rejected',
            message=f'Your campaign "{campaign.title}" was not approved. Reason: {reason}',
            link=f'/my-campaigns/{campaign.slug}',
        )
    elif action == 'suspend':
        from emails.tasks import send_campaign_suspended_email_task
        campaign.status = Campaign.Status.SUSPENDED
        campaign.rejection_reason = reason
        campaign.admin_notes = notes
        campaign.save()
        Notification.objects.create(
            user=campaign.owner,
            notification_type=Notification.Type.CAMPAIGN_SUSPENDED,
            title='Campaign Suspended',
            message=f'Your campaign "{campaign.title}" has been suspended.' + (f' Reason: {reason}' if reason else ''),
            link=f'/my-campaigns/{campaign.slug}',
        )
        send_campaign_suspended_email_task.delay(str(campaign.owner_id), str(campaign.id), reason, notes)
    elif action == 'submit':
        campaign.status = Campaign.Status.PENDING
        campaign.save()
    else:
        raise ValueError(f'Unknown action: {action}')

    return campaign


def change_campaign_status(campaign_id, new_status, reason=''):
    from apps.campaigns.models import Campaign
    from apps.notifications.models import Notification
    from emails.tasks import send_campaign_status_update_email_task

    campaign = get_object_or_404(Campaign, pk=campaign_id)
    old_status = campaign.status

    campaign.status = new_status
    if new_status == Campaign.Status.REJECTED:
        campaign.rejection_reason = reason
    elif new_status == Campaign.Status.ACTIVE:
        campaign.approved_at = timezone.now()
    campaign.save()

    send_campaign_status_update_email_task.delay(str(campaign.owner_id), str(campaign.id), new_status, reason)

    Notification.objects.create(
        user=campaign.owner,
        notification_type=Notification.Type.CAMPAIGN_APPROVED,
        title=f'Campaign Status Updated to {new_status.title()}',
        message=f'Your campaign "{campaign.title}" status has been changed to {new_status}.',
        link=f'/campaigns/{campaign.slug}',
    )

    return campaign


def get_all_campaign_reports(params=None):
    from apps.campaigns.models import CampaignReport
    qs = CampaignReport.objects.select_related('campaign', 'reported_by').order_by('-created_at')

    if params:
        status = params.get('status')
        if status and status != 'all':
            qs = qs.filter(status=status)

        campaign_id = params.get('campaign')
        if campaign_id:
            qs = qs.filter(campaign_id=campaign_id)

        search = params.get('search')
        if search:
            from django.db.models import Q
            qs = qs.filter(
                Q(campaign__title__icontains=search) |
                Q(reporter_name__icontains=search) |
                Q(reported_by__first_name__icontains=search) |
                Q(reported_by__last_name__icontains=search) |
                Q(reported_by__email__icontains=search)
            )

    return qs


def get_reported_campaigns():
    """Distinct campaigns that have at least one report -- backs the admin
    Reports table's "Campaign" filter with a short, relevant list instead of
    every campaign on the platform."""
    from apps.campaigns.models import Campaign, CampaignReport
    campaign_ids = CampaignReport.objects.values_list('campaign_id', flat=True).distinct()
    return Campaign.objects.filter(id__in=campaign_ids).order_by('title')

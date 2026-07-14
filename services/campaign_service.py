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


def increment_views(campaign):
    from apps.campaigns.models import Campaign
    Campaign.objects.filter(pk=campaign.pk).update(views_count=models.F('views_count') + 1)


def get_owner_campaigns(user):
    from apps.campaigns.models import Campaign
    return Campaign.objects.filter(owner=user).select_related('category').order_by('-created_at')


def get_owner_campaign(user, slug):
    from apps.campaigns.models import Campaign
    return get_object_or_404(Campaign, owner=user, slug=slug)


def create_campaign(user, validated_data):
    from apps.campaigns.models import Campaign, Category
    category_id = validated_data.pop('category_id', None)
    category = None
    if category_id:
        category = Category.objects.filter(id=category_id).first()

    campaign = Campaign.objects.create(
        owner=user,
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
    from django.shortcuts import get_object_or_404
    campaign = get_object_or_404(Campaign, owner=user, slug=slug)
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
    campaign.cover_image = image_file
    campaign.save(update_fields=['cover_image'])
    return campaign


def update_campaign_media(campaign, cover_file=None, gallery_files=None):
    from apps.campaigns.models import Campaign, CampaignImage
    from django.db.models import Max

    if cover_file:
        campaign.cover_image = cover_file
        campaign.save(update_fields=['cover_image'])
        campaign.images.filter(is_cover=True).delete()
        CampaignImage.objects.create(
            campaign=campaign,
            image=cover_file,
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
                image=f,
                order=max_order + i,
                is_cover=False,
            )

    return get_object_or_404(
        Campaign.objects.prefetch_related('images', 'updates').select_related('category'),
        pk=campaign.pk,
    )


def delete_campaign_image(user, slug, image_id):
    from apps.campaigns.models import Campaign, CampaignImage
    campaign = get_object_or_404(Campaign, owner=user, slug=slug)
    image = get_object_or_404(CampaignImage, pk=image_id, campaign=campaign)
    image.delete()
    return get_object_or_404(
        Campaign.objects.prefetch_related('images', 'updates').select_related('category'),
        pk=campaign.pk,
    )


def add_campaign_update(campaign, user, title, content, images=None):
    from apps.campaigns.models import CampaignUpdate, CampaignUpdateImage
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
                image=image,
                order=idx,
            )

    _notify_donors_of_update(campaign, update)
    return update


def update_campaign_update(campaign, update_id, user, title=None, content=None, images=None, images_to_remove=None):
    from apps.campaigns.models import CampaignUpdate, CampaignUpdateImage
    from django.shortcuts import get_object_or_404
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
                image=image,
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
    donor_users = (
        Donation.objects.filter(campaign=campaign, status=Donation.Status.PAID, donor__isnull=False)
        .values_list('donor', flat=True)
        .distinct()
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
    qs = Campaign.objects.select_related('owner', 'category').order_by('-created_at')
    if params:
        s = params.get('status')
        if s:
            qs = qs.filter(status=s)
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
    known_donors = paid_donations.filter(donor__isnull=False).values('donor').distinct().count()
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


def admin_action(campaign_id, action, reason, admin_user):
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
        campaign.status = Campaign.Status.SUSPENDED
        campaign.save()
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

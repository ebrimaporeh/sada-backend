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
    return Category.objects.filter(is_active=True)


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
            Campaign.Status.SUSPENDED,
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
        status=Campaign.Status.DRAFT,
        **validated_data,
    )
    return campaign


def update_campaign(campaign, validated_data):
    from apps.campaigns.models import Category
    category_id = validated_data.pop('category_id', None)
    if category_id is not None:
        campaign.category = Category.objects.filter(id=category_id).first()

    if campaign.status == campaign.Status.ACTIVE:
        campaign.status = campaign.Status.PENDING

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


def add_campaign_update(campaign, user, validated_data):
    from apps.campaigns.models import CampaignUpdate
    update = CampaignUpdate.objects.create(
        campaign=campaign,
        posted_by=user,
        **validated_data,
    )
    _notify_donors_of_update(campaign, update)
    return update


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


def get_all_campaigns(params=None):
    from apps.campaigns.models import Campaign
    qs = Campaign.objects.select_related('owner', 'category').order_by('-created_at')
    if params:
        s = params.get('status')
        if s:
            qs = qs.filter(status=s)
        q = params.get('search')
        if q:
            qs = qs.filter(models.Q(title__icontains=q) | models.Q(owner__email__icontains=q))
    return qs


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

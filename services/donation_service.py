import logging
import uuid
from datetime import timedelta
from decimal import Decimal
from django.utils import timezone
from django.db import transaction
from django.db.models import F, Sum
from django.shortcuts import get_object_or_404
from django.http import Http404
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import ValidationError

logger = logging.getLogger(__name__)


def success_response(data, message='Success.', status_code=status.HTTP_200_OK):
    return Response({'success': True, 'message': message, 'data': data}, status=status_code)


def error_response(message, errors=None, status_code=status.HTTP_400_BAD_REQUEST):
    return Response({'success': False, 'message': message, 'errors': errors or {}}, status=status_code)


def create_donation(donor, validated_data):
    """Create a PENDING donation and start a payment intent for it with
    whichever gateway validated_data['gateway'] names (modempay by default).

    Exactly one of campaign_id/organization_id must be present in
    validated_data (enforced by DonationCreateSerializer.validate) --
    campaign_id routes to the existing campaign-donation path unchanged;
    organization_id is a direct donation to the organization itself, with
    no deadline/goal-capacity check (an organization has neither), just
    confirming it exists.

    Returns (donation, payment_link, error_message). payment_link is the
    gateway's hosted checkout URL the frontend must redirect the donor to -
    None if the intent could not be created (donation is left FAILED in
    that case). error_message is set alongside a None payment_link only
    when the gateway rejected the request for a reason the donor can act
    on (e.g. amount over the provider's limit) -- None for a generic/
    transient gateway failure, so the view can tell "your amount is too
    high" apart from "please try again" (see _initiate_payment).

    The campaign row lock only covers the deadline/status check + donation
    creation; it's released before the gateway's HTTP call so one donor's
    request to a provider can't block every other donor to the same campaign.
    Confirmation (and the actual Campaign.raised/donors_count increment)
    happens later, asynchronously, via the webhook -> _confirm_donation.
    """
    from apps.donations.models import Donation
    from apps.campaigns.models import Campaign
    from apps.users.models import Organization
    from apps.fundraising.models import Embed
    from services.gateways.registry import get_gateway

    campaign_id = validated_data.pop('campaign_id', None)
    organization_id = validated_data.pop('organization_id', None)
    # A reference only -- resolved to the embed's own owner-configured
    # return_url here, server-side, never trusting a client-supplied URL
    # directly (see DonationCreateSerializer.embed_id's own comment). An
    # unknown/inactive embed, or one with no return_url set, just means no
    # source_url -- never blocks the donation itself.
    embed_id = validated_data.pop('embed_id', None)
    validated_data['source_url'] = ''
    if embed_id:
        embed = Embed.objects.filter(pk=embed_id, is_active=True).first()
        if embed and embed.return_url:
            validated_data['source_url'] = embed.return_url
    # Raises ValidationError here (before any lock/DB write) for an unknown
    # or disabled gateway, rather than creating an orphaned PENDING donation
    # that _initiate_payment would only discover was unpayable afterward.
    gateway = get_gateway(validated_data.get('gateway') or 'modempay')

    if organization_id:
        organization = Organization.objects.filter(pk=organization_id).first()
        if organization is None:
            raise Http404('Organization not found.')
        donation = Donation.objects.create(
            organization=organization,
            donor=donor,
            fee=Decimal('0'),
            currency=gateway.default_currency,
            payment_reference=f'SD-{uuid.uuid4().hex[:12].upper()}',
            **validated_data,
        )
    else:
        with transaction.atomic():
            # Lock the row so concurrent donations can't both pass the goal check
            campaign = Campaign.objects.select_for_update().filter(
                pk=campaign_id,
                status__in=[Campaign.Status.ACTIVE, Campaign.Status.APPROVED],
            ).first()

            if campaign is None:
                raise Http404('Campaign not found or not accepting donations.')

            # Deadline check -- open-ended campaigns (deadline=None) never
            # trip this, same as an active deadline that hasn't passed yet.
            if campaign.deadline and campaign.deadline < timezone.now().date():
                raise ValidationError('This campaign has ended and is no longer accepting donations.')

            # Campaigns can be overfunded - reaching (or passing) the goal doesn't
            # close donations, it just pushes progress past 100%. Only an active
            # deadline/status gates whether a campaign can still receive funds.

            # No platform fee on donations - donors only pay whatever ModemPay
            # itself charges them directly; the full amount is credited to the
            # campaign. (The platform fee is taken on payout, not donation.)
            donation = Donation.objects.create(
                campaign=campaign,
                donor=donor,
                fee=Decimal('0'),
                # Server-resolved, not client-controlled - Stripe doesn't settle
                # in GMD at all, so its donations are charged in whatever
                # PlatformSettings.stripe_settlement_currency an admin has set.
                currency=gateway.default_currency,
                payment_reference=f'SD-{uuid.uuid4().hex[:12].upper()}',
                **validated_data,
            )

    payment_link, error_message = _initiate_payment(donation)
    return donation, payment_link, error_message


def _initiate_payment(donation):
    """Create the payment intent for a donation via its gateway. Returns
    (payment_link, error_message) -- payment_link is None (and the
    donation marked FAILED) if it couldn't be created. error_message is
    the gateway's own client-facing reason when the rejection is
    something the donor can fix (e.g. amount over the provider's limit --
    see modempay_service.create_payment_intent), or None for a generic/
    transient gateway failure the donor can only retry blindly."""
    from django.conf import settings
    from services.gateways.registry import get_gateway

    frontend_url = getattr(settings, 'FRONTEND_URL', '').rstrip('/')
    slug = donation.destination_slug
    # Organization donations use /give/<slug>, campaign donations use
    # /donate/<slug> -- both routes exist on the frontend (see
    # rootRoute.jsx), each rendering the matching checkout/success flow.
    path = 'give' if donation.is_organization_donation else 'donate'
    return_url = f'{frontend_url}/{path}/{slug}/success?ref={donation.payment_reference}&amount={donation.amount}'
    cancel_url = f'{frontend_url}/{path}/{slug}'

    gateway = get_gateway(donation.gateway)
    try:
        intent = gateway.create_payment_intent(donation, return_url=return_url, cancel_url=cancel_url)
    except DjangoValidationError as e:
        donation.status = donation.Status.FAILED
        donation.save(update_fields=['status'])
        message = e.messages[0] if e.messages else str(e)
        return None, message

    if intent is None:
        donation.status = donation.Status.FAILED
        donation.save(update_fields=['status'])
        return None, None

    donation.provider_reference = intent.provider_reference
    donation.save(update_fields=['provider_reference'])
    return intent.payment_link, None


@transaction.atomic
def _confirm_donation(donation):
    from apps.campaigns.models import Campaign
    from apps.notifications.models import Notification
    from emails.tasks import send_donation_received_email_task
    import services.audit_service as audit_service
    import services.events_service as events_service
    import services.ledger_service as ledger_service
    from apps.audit.models import AuditLog
    from apps.events.models import Event

    donation.status = donation.Status.PAID
    donation.paid_at = timezone.now()
    donation.save(update_fields=['status', 'paid_at'])

    if donation.campaign_id:
        Campaign.objects.filter(pk=donation.campaign_id).update(
            raised=F('raised') + donation.net_amount,
            donors_count=F('donors_count') + 1,
        )
        donation.campaign.refresh_from_db()

    # Ledger post is idempotency-keyed on the donation id (see
    # ledger_service.record_donation_received) -- same transaction as the
    # Campaign.raised update above, so a ledger failure rolls both back.
    ledger_service.record_donation_received(donation)

    # actor=None -- this path only ever runs from a gateway webhook or the
    # reconciliation sweep, never a logged-in admin/donor request.
    audit_service.log(
        None, AuditLog.Action.DONATION_STATUS_CHANGED, donation,
        f'Donation {donation.payment_reference} marked paid',
        metadata={'status': 'paid'},
    )
    # Organization donations aren't tracked in the campaign-funnel Event
    # stream (campaign=None is a valid, intentional no-op there) -- a
    # dedicated organization donation funnel isn't in scope for this pass.
    events_service.track(
        Event.Type.DONATION_COMPLETED,
        campaign=donation.campaign if donation.campaign_id else None,
        metadata={'amount': str(donation.amount)},
    )

    for recipient in _donation_recipients(donation):
        Notification.objects.create(
            user=recipient,
            notification_type=Notification.Type.DONATION_RECEIVED,
            title='New Donation!',
            message=f'{donation.donor_display} donated D{donation.amount} to "{donation.destination_title}".',
            link=_donation_destination_link(donation),
        )

    # Deferred to on_commit - enqueueing before the transaction lands would
    # let a worker pick this up and query a donation row that isn't there yet
    # (or worse, email out a confirmation for a donation that later rolled back).
    transaction.on_commit(lambda: send_donation_received_email_task.delay(str(donation.id)))

    if donation.campaign_id and donation.campaign.is_funded:
        Notification.objects.create(
            user=donation.campaign.owner,
            notification_type=Notification.Type.GOAL_REACHED,
            title='Goal Reached!',
            message=f'Your campaign "{donation.campaign.title}" has reached its goal!',
            link=f'/my-campaigns/{donation.campaign.slug}',
        )

    return donation


def _donation_recipients(donation):
    """Who should be notified about a donation -- the single campaign owner
    for a campaign donation, or every organization member holding
    manage_organization (in practice, its Owner-role members -- see
    organizations.md) for a direct organization donation, since there's no
    single "owner" user to point at there."""
    if donation.campaign_id:
        return [donation.campaign.owner]
    from apps.organizations.models import OrganizationMembership
    from apps.organizations.permissions import OrganizationPermission
    memberships = OrganizationMembership.objects.filter(
        organization_id=donation.organization_id,
    ).select_related('user', 'role')
    return [m.user for m in memberships if OrganizationPermission.MANAGE_ORGANIZATION in m.role.permissions]


def _donation_destination_link(donation):
    if donation.campaign_id:
        return f'/my-campaigns/{donation.campaign.slug}'
    return f'/organizations/{donation.organization_id}/donations'


@transaction.atomic
def admin_update_donation(donation, validated_data):
    """Apply an admin edit to a donation, keeping Campaign.raised/donors_count
    in sync for a campaign donation (a direct organization donation has no
    such denormalized total to keep in sync -- its totals are computed live,
    see organization_service.get_organization_donation_stats).

    A plain serializer.save() here would let amount/status changes silently
    desync the campaign's ledger from what was actually paid - this recomputes
    the campaign delta the same way _confirm_donation() does.
    """
    from apps.campaigns.models import Campaign
    import services.ledger_service as ledger_service

    old_status = donation.status
    old_net = donation.net_amount if old_status == donation.Status.PAID else Decimal('0')

    for field, value in validated_data.items():
        setattr(donation, field, value)

    new_status = donation.status
    new_net = donation.net_amount if new_status == donation.Status.PAID else Decimal('0')

    delta_raised = new_net - old_net
    delta_donors = 0
    if old_status != donation.Status.PAID and new_status == donation.Status.PAID:
        delta_donors = 1
        if not donation.paid_at:
            donation.paid_at = timezone.now()
    elif old_status == donation.Status.PAID and new_status != donation.Status.PAID:
        delta_donors = -1

    if donation.campaign_id:
        # Locked even when the delta is zero, matching the pre-organization-
        # donation behavior of always fetching the campaign here.
        campaign = Campaign.objects.select_for_update().get(pk=donation.campaign_id)
        if delta_raised != 0 or delta_donors != 0:
            Campaign.objects.filter(pk=campaign.pk).update(
                raised=F('raised') + delta_raised,
                donors_count=F('donors_count') + delta_donors,
            )

    donation.save()
    donation.refresh_from_db()

    # No real gateway cash movement behind an admin edit -- posted against
    # the suspense account rather than a gateway clearing account. A no-op
    # if the edit didn't change the paid amount.
    ledger_service.record_donation_admin_adjustment(donation, delta_raised)

    return donation


@transaction.atomic
def refund_donation(donation, reason=''):
    """Refund a PAID donation via its own gateway and unwind its
    contribution to the campaign's totals - the reverse of _confirm_donation().

    Re-fetches the donation with a row lock so two concurrent refund
    attempts on the same donation can't both pass the PAID check before
    either commits. Raises ValidationError if the donation isn't PAID or
    the gateway declines the refund (real money reversing - surfaced to the
    admin, not silently swallowed).
    """
    from apps.campaigns.models import Campaign
    from apps.notifications.models import Notification
    from services.gateways.registry import get_gateway
    from emails.tasks import send_donation_refunded_email_task
    import services.ledger_service as ledger_service

    donation = donation.__class__.objects.select_for_update().get(pk=donation.pk)
    if donation.status != donation.Status.PAID:
        raise ValidationError(f'Only paid donations can be refunded (current status: {donation.status}).')

    gateway = get_gateway(donation.gateway)
    result = gateway.refund_donation(donation)
    if result is None:
        raise ValidationError('Refund could not be processed by the payment provider. Please try again shortly.')

    if donation.campaign_id:
        Campaign.objects.filter(pk=donation.campaign_id).update(
            raised=F('raised') - donation.net_amount,
            donors_count=F('donors_count') - 1,
        )

    donation.status = donation.Status.REFUNDED
    donation.refunded_at = timezone.now()
    donation.refund_reason = reason
    donation.save(update_fields=['status', 'refunded_at', 'refund_reason'])
    if donation.campaign_id:
        donation.campaign.refresh_from_db()

    # Posts a compensating transaction reversing DONATION_RECEIVED (see
    # ledger_service.record_donation_refunded) -- same atomic block, so a
    # ledger failure rolls the whole refund back before the DB commits
    # (the gateway-side refund call above already happened and can't be
    # rolled back -- same known tradeoff refund_donation already accepted
    # before this ledger existed, see services.md).
    ledger_service.record_donation_refunded(donation)

    for recipient in _donation_recipients(donation):
        Notification.objects.create(
            user=recipient,
            notification_type=Notification.Type.DONATION_REFUNDED,
            title='Donation Refunded',
            message=f'A donation of D{donation.amount} to "{donation.destination_title}" was refunded. '
                    f'Your total has been adjusted.',
            link=_donation_destination_link(donation),
        )

    if donation.donor:
        Notification.objects.create(
            user=donation.donor,
            notification_type=Notification.Type.DONATION_REFUNDED,
            title='Donation Refunded',
            message=f'Your donation of D{donation.amount} to "{donation.destination_title}" has been refunded.',
            link=(f'/campaigns/{donation.campaign.slug}' if donation.campaign_id else f'/give/{donation.organization.slug}'),
        )
        transaction.on_commit(lambda: send_donation_refunded_email_task.delay(str(donation.id)))

    return donation


def confirm_donation_by_reference(reference, provider_reference=''):
    """Row-locked so two near-simultaneous callers for the same reference
    (a redelivered webhook alongside the reconciliation sweep, say) can't
    both read status=PENDING before either commits and double-confirm -
    the second caller re-checks status after acquiring the lock and finds
    it already PAID. WebhookEvent (payment_service.handle_webhook) is the
    primary guard against a redelivered webhook specifically; this closes
    the gap for any other concurrent caller of this function."""
    from apps.donations.models import Donation
    with transaction.atomic():
        donation = Donation.objects.select_for_update().filter(payment_reference=reference).first()
        if donation is None or donation.status != Donation.Status.PENDING:
            return None
        donation.provider_reference = provider_reference
        donation.save(update_fields=['provider_reference'])
        return _confirm_donation(donation)


def fail_donation_by_reference(reference):
    """Mark a still-pending donation as failed/cancelled from a webhook event.
    No campaign totals to unwind - a PENDING donation was never credited.
    Row-locked for the same reason as confirm_donation_by_reference above."""
    from apps.donations.models import Donation
    import services.audit_service as audit_service
    from apps.audit.models import AuditLog

    with transaction.atomic():
        donation = Donation.objects.select_for_update().filter(payment_reference=reference).first()
        if donation is None or donation.status != Donation.Status.PENDING:
            return False
        donation.status = Donation.Status.FAILED
        donation.save(update_fields=['status'])
        audit_service.log(
            None, AuditLog.Action.DONATION_STATUS_CHANGED, donation,
            f'Donation {donation.payment_reference} marked failed',
            metadata={'status': 'failed'},
        )
        return True


def reconcile_donation_by_reference(reference):
    """Check the donation's own gateway directly for its real status and
    confirm/fail it if needed.

    The webhook is the primary confirmation path, but it can't reach a
    localhost backend at all in dev, and could in principle be missed/delayed
    even in production - this is the fallback. Safe to call repeatedly: a
    no-op once the donation is no longer PENDING. Returns the (possibly
    updated) donation, or None if the reference doesn't exist.
    """
    from apps.donations.models import Donation
    from services.gateways.registry import get_gateway

    try:
        donation = Donation.objects.get(payment_reference=reference)
    except Donation.DoesNotExist:
        return None

    if donation.status != Donation.Status.PENDING or not donation.provider_reference:
        return donation

    gateway = get_gateway(donation.gateway)
    intent = gateway.retrieve_payment_intent(donation.provider_reference)
    if not intent:
        return donation

    resolved = gateway.intent_status(intent)
    if resolved == 'successful':
        real_reference = gateway.resolve_confirmed_reference(reference, intent.get('id', ''))
        return confirm_donation_by_reference(reference, real_reference)
    if resolved == 'failed':
        fail_donation_by_reference(reference)
        donation.refresh_from_db()

    return donation


def sweep_pending_donations(older_than_minutes=15, limit=50):
    """Reconcile PENDING donations old enough that their webhook should have
    already arrived. Runs on a periodic schedule (see apps/donations/tasks.py)
    as the safety net for missed/delayed webhooks - the same fallback
    reconcile_donation_by_reference() provides on-demand, just self-triggered
    instead of waiting for a donor to check their status.

    `limit` caps how many donations one sweep run touches, so a large backlog
    is worked off over several runs rather than one run making `limit`
    synchronous gateway calls back-to-back.
    """
    from apps.donations.models import Donation

    cutoff = timezone.now() - timedelta(minutes=older_than_minutes)
    references = list(
        Donation.objects.filter(
            status=Donation.Status.PENDING,
            created_at__lt=cutoff,
        ).order_by('created_at').values_list('payment_reference', flat=True)[:limit]
    )

    resolved = 0
    for reference in references:
        donation = reconcile_donation_by_reference(reference)
        if donation and donation.status != Donation.Status.PENDING:
            resolved += 1

    if references:
        logger.info(
            'sweep_pending_donations: checked %d, resolved %d, still pending %d',
            len(references), resolved, len(references) - resolved,
        )
    return {'checked': len(references), 'resolved': resolved}


def get_user_donations(user):
    """The dashboard's "Recent Donations" widget -- only donations that
    actually went through. Unlike get_campaign_donors (also PAID-only),
    this had no status filter at all until now: every attempt (PENDING
    the moment it's created, FAILED if the gateway ever rejects it -- see
    create_donation/_initiate_payment) showed up identically to a real
    completed donation, with no status shown anywhere in this widget to
    tell them apart. A donor whose payment failed (e.g. amount over the
    gateway's limit) would see their own failed attempts listed next to
    "Total Raised: D0" as if they'd actually given money."""
    from apps.donations.models import Donation
    return Donation.objects.filter(
        donor=user, status=Donation.Status.PAID,
    ).select_related('campaign', 'organization').order_by('-paid_at')


def get_campaign_donors(user, slug):
    # Was a literal `Campaign.objects.get(owner=user, ...)` -- 404'd for any
    # org member who wasn't the specific user recorded as `owner` (the
    # member who happened to create the campaign), even though the
    # Donors tab is meant to be readable by any member with access to the
    # campaign (see MyCampaignDetailPage.jsx's comment on visibleTabs).
    # get_owner_campaign() is the same org-membership-aware access check
    # every other "my campaign" read already goes through -- no
    # required_permission, since viewing donors needs no more than read
    # access, same as Overview/Updates.
    from apps.donations.models import Donation
    from services.campaign_service import get_owner_campaign
    campaign = get_owner_campaign(user, slug)
    return Donation.objects.filter(
        campaign=campaign,
        status=Donation.Status.PAID,
    ).select_related('donor').order_by('-paid_at')


DONOR_SORT_OPTIONS = {
    'latest': '-paid_at',
    'highest': '-amount',
}


def get_public_campaign_donors(slug, sort='latest'):
    """Donor list for the public campaign page - any visible campaign, not owner-scoped."""
    from apps.donations.models import Donation
    from apps.campaigns.models import Campaign
    campaign = get_object_or_404(
        Campaign,
        slug=slug,
        status__in=[
            Campaign.Status.ACTIVE,
            Campaign.Status.APPROVED,
            Campaign.Status.COMPLETED,
            Campaign.Status.PENDING,
        ],
    )
    ordering = DONOR_SORT_OPTIONS.get(sort, DONOR_SORT_OPTIONS['latest'])
    return Donation.objects.filter(
        campaign=campaign,
        status=Donation.Status.PAID,
    ).select_related('donor').order_by(ordering)


def get_organization_donations(user, organization_id):
    """Direct (non-campaign) donations made straight to an organization --
    the org dashboard's "Direct Donations" list. Membership-only (any
    current member can view, same read-access level as a campaign's Donors
    tab) -- get_organization() already enforces that."""
    from apps.donations.models import Donation
    from services.organization_service import get_organization
    organization = get_organization(organization_id, user)
    return Donation.objects.filter(
        organization=organization,
        status=Donation.Status.PAID,
    ).select_related('donor').order_by('-paid_at')


def get_organization_donation_stats(user, organization_id):
    """Direct-donation total + campaign-donation total for an organization,
    kept separate per campaign but summed for the org-level total (see
    project.md's donation-totals example) -- computed live via aggregation
    rather than a new denormalized counter, since Organization has no
    single "raised" concept the way Campaign does and this is cheap enough
    to run on every dashboard load."""
    from django.db.models import Sum, Count
    from apps.donations.models import Donation
    from services.organization_service import get_organization
    organization = get_organization(organization_id, user)

    direct = Donation.objects.filter(organization=organization, status=Donation.Status.PAID).aggregate(
        total=Sum('amount'), count=Count('id'),
    )
    campaign_totals = Donation.objects.filter(
        campaign__organization=organization, status=Donation.Status.PAID,
    ).aggregate(total=Sum('amount'), count=Count('id'))

    direct_total = direct['total'] or Decimal('0')
    campaign_total = campaign_totals['total'] or Decimal('0')

    return {
        'direct_total': direct_total,
        'direct_count': direct['count'] or 0,
        'campaign_total': campaign_total,
        'campaign_count': campaign_totals['count'] or 0,
        'total_raised': direct_total + campaign_total,
    }


def get_public_organization_total_raised(organization):
    """Direct-donation total only -- what the public /give/<slug> page
    shows, distinct from get_organization_donation_stats (dashboard-only,
    includes campaign donations too, see that function's docstring)."""
    from django.db.models import Sum
    from apps.donations.models import Donation
    total = Donation.objects.filter(
        organization=organization, status=Donation.Status.PAID,
    ).aggregate(t=Sum('amount'))['t']
    return total or Decimal('0')


def get_all_donations(params=None):
    from apps.donations.models import Donation
    from django.db.models import Q
    qs = Donation.objects.select_related('campaign', 'organization', 'donor').order_by('-created_at')
    if params:
        s = params.get('status')
        if s:
            qs = qs.filter(status=s)
        campaign_id = params.get('campaign')
        if campaign_id:
            qs = qs.filter(campaign_id=campaign_id)
        organization_id = params.get('organization')
        if organization_id:
            qs = qs.filter(organization_id=organization_id)
        donor_id = params.get('donor')
        if donor_id:
            qs = qs.filter(donor_id=donor_id)
        q = params.get('search')
        if q:
            qs = qs.filter(
                Q(payment_reference__icontains=q)
                | Q(campaign__title__icontains=q)
                | Q(organization__organization_name__icontains=q)
                | Q(donor__email__icontains=q)
                | Q(donor_name__icontains=q)
                | Q(donor__first_name__icontains=q)
                | Q(donor__last_name__icontains=q)
            )
    return qs


def get_donation_stats():
    from apps.donations.models import Donation
    from django.db.models import Sum, Count

    total_donations = Donation.objects.count()
    anonymous_count = Donation.objects.filter(is_anonymous=True).count()
    paid = Donation.objects.filter(status=Donation.Status.PAID).aggregate(
        total=Sum('amount'), count=Count('id'),
    )
    total_raised = paid['total'] or Decimal('0')
    paid_count = paid['count'] or 0
    average_donation = (total_raised / paid_count) if paid_count else Decimal('0')

    return {
        'total_donations': total_donations,
        'total_raised': float(total_raised),
        'average_donation': float(average_donation),
        'anonymous_count': anonymous_count,
    }

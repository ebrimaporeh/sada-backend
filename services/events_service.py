import logging

logger = logging.getLogger(__name__)


def track(event_type, user=None, campaign=None, metadata=None, session_id='', ip_address=None):
    """Records one product-engagement Event. Never raises -- a tracking bug
    must never break the real action (a donation, a page load) it's
    describing alongside."""
    try:
        from apps.events.models import Event
        Event.objects.create(
            type=event_type,
            user=user,
            campaign=campaign,
            metadata=metadata or None,
            session_id=session_id or '',
            ip_address=ip_address,
        )
    except Exception:
        logger.exception('events_service.track failed for type=%s', event_type)


def get_events(params=None):
    from apps.events.models import Event
    qs = Event.objects.select_related('user', 'campaign').order_by('-created_at')
    if params:
        event_type = params.get('type')
        if event_type:
            qs = qs.filter(type=event_type)
        campaign_id = params.get('campaign')
        if campaign_id:
            qs = qs.filter(campaign_id=campaign_id)
    return qs

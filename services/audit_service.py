import logging
from django.db.models import Q

logger = logging.getLogger(__name__)


def log(actor, action, target=None, description='', metadata=None, actor_name=None, actor_email=None):
    """Records one AuditLog row. Called explicitly from the specific view/
    service code where a curated, meaningful action actually succeeds --
    see apps/audit/models.py::AuditLog.Action for the full list and why
    this isn't blanket request logging.

    `actor` is a real User for anything a logged-in person did. For a
    donation from a guest who never created an account, pass `actor=None`
    but still give `actor_name` (their entered name, or "Anonymous donor")
    -- a guest is still a real person, not "the system," and the activity
    list should read that way. `actor`/`actor_name`/`actor_email` are only
    all left unset for genuinely system-triggered state changes with no
    human on the other end at all (a payment gateway webhook, the
    reconciliation sweep) -- those are the only rows that should ever
    display as "System".

    `actor_name`/`actor_email` are normally derived from `actor`, but can
    be overridden explicitly when the actor's own fields may already be
    stale by the time this runs (self-service account deletion anonymizes
    them as part of the same action being logged) or when there's a real
    name to attribute without a User row at all (a guest donor).

    Never raises: a bug in audit logging must never take down the real
    action it's describing (a donation, a refund, ...), so failures here
    are caught and logged instead of propagated.
    """
    try:
        from apps.audit.models import AuditLog
        AuditLog.objects.create(
            actor=actor,
            actor_name=actor_name if actor_name is not None else (actor.full_name if actor else ''),
            actor_email=actor_email if actor_email is not None else (actor.email if actor else ''),
            action=action,
            target_type=target.__class__.__name__ if target is not None else '',
            target_id=str(getattr(target, 'pk', '')) if target is not None else '',
            target_repr=str(target) if target is not None else '',
            description=description,
            metadata=metadata or None,
        )
    except Exception:
        logger.exception('audit_service.log failed for action=%s', action)


def get_audit_logs(params=None):
    from apps.audit.models import AuditLog
    qs = AuditLog.objects.select_related('actor').order_by('-created_at')
    if params:
        action = params.get('action')
        if action:
            qs = qs.filter(action=action)
        actor_id = params.get('actor')
        if actor_id:
            qs = qs.filter(actor_id=actor_id)
        q = params.get('search')
        if q:
            qs = qs.filter(
                Q(description__icontains=q) | Q(actor_name__icontains=q)
                | Q(actor_email__icontains=q) | Q(target_repr__icontains=q)
            )
    return qs


def get_audit_actors():
    """Distinct users who've actually done something audited -- backs the
    activity page's "User" filter with a short, relevant list instead of
    every user in the system."""
    from apps.audit.models import AuditLog
    from apps.users.models import User
    actor_ids = AuditLog.objects.exclude(actor__isnull=True).values_list('actor_id', flat=True).distinct()
    return User.objects.filter(id__in=actor_ids).order_by('first_name', 'last_name')
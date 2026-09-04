import logging
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task
def sweep_campaign_lifecycle_task():
    """Periodic sweep that's the only thing in the codebase that ever
    transitions a campaign out of ACTIVE on its own — see
    services/campaign_service.py's close_funded_campaigns() and
    expire_overdue_campaigns() for the actual logic.

    Order matters: close_funded_campaigns runs first so a campaign that
    hits its goal on its last day is marked COMPLETED, not EXPIRED.
    """
    from services.campaign_service import close_funded_campaigns, expire_overdue_campaigns
    funded_result = close_funded_campaigns()
    expired_result = expire_overdue_campaigns()
    return {'funded': funded_result, 'expired': expired_result}

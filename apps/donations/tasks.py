import logging
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task
def sweep_pending_donations_task():
    """Periodic safety net for donations stuck PENDING because a gateway
    webhook was missed or delayed — see services/donation_service.py's
    sweep_pending_donations() for the reconciliation logic itself."""
    from services.donation_service import sweep_pending_donations
    return sweep_pending_donations()

import logging
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task
def sweep_processing_payouts_task():
    """Periodic safety net for payouts stuck PROCESSING because ModemPay's
    transfer.succeeded/failed webhook was missed or delayed — see
    services/payment_service.py's sweep_processing_payouts() for the
    reconciliation logic itself."""
    from services.payment_service import sweep_processing_payouts
    return sweep_processing_payouts()

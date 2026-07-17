from decimal import Decimal
from unittest.mock import patch
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework.exceptions import ValidationError

from apps.users.models import User
from apps.campaigns.models import Campaign
from apps.donations.models import Donation
from apps.payments.models import Payout
from services import donation_service, payment_service
from services.gateways.registry import get_gateway, GATEWAYS
from services.gateways.modempay import ModemPayGateway
from services.gateways.base import GatewayEvent, GatewayEventType, GatewayIntent


def make_campaign(**kwargs):
    owner = kwargs.pop('owner', None) or User.objects.create_user(
        email=f'owner{User.objects.count()}@example.com', password='pass',
    )
    defaults = {
        'owner': owner,
        'title': 'Well for Bakau',
        'short_description': 'Clean water',
        'story': 'A well for the community.',
        'goal': Decimal('10000.00'),
        'status': Campaign.Status.ACTIVE,
    }
    defaults.update(kwargs)
    return Campaign.objects.create(**defaults)


class GatewayRegistryTest(APITestCase):
    def test_get_gateway_returns_modempay_instance(self):
        gateway = get_gateway('modempay')
        self.assertIsInstance(gateway, ModemPayGateway)
        self.assertTrue(gateway.supports_payouts)

    def test_get_gateway_unknown_code_raises(self):
        with self.assertRaises(ValidationError):
            get_gateway('does-not-exist')

    def test_get_gateway_disabled_raises(self):
        with self.settings(PAYMENT_GATEWAYS={'modempay': {'enabled': False, 'demo_mode': True}}):
            with self.assertRaises(ValidationError):
                get_gateway('modempay')

    def test_registry_holds_only_modempay_for_now(self):
        # Stripe is a later phase — this pins the registry's current
        # contents so adding it is a visible, deliberate diff.
        self.assertEqual(set(GATEWAYS.keys()), {'modempay'})


class DonationCreateGatewayTest(APITestCase):
    def setUp(self):
        self.campaign = make_campaign()

    @patch('services.modempay_service.create_payment_intent')
    def test_create_donation_defaults_to_modempay_gateway(self, mock_create):
        mock_create.return_value = {
            'status': True,
            'data': {'payment_link': 'https://pay.modempay.com/abc', 'intent_secret': 'sec_123'},
        }
        donation, payment_link = donation_service.create_donation(None, {
            'campaign_id': self.campaign.id,
            'amount': Decimal('100.00'),
            'provider': 'wave',
            'phone': '+2207000000',
        })
        self.assertEqual(donation.gateway, 'modempay')
        self.assertEqual(payment_link, 'https://pay.modempay.com/abc')
        self.assertEqual(donation.provider_reference, 'sec_123')
        self.assertEqual(donation.status, Donation.Status.PENDING)
        mock_create.assert_called_once()

    @patch('services.modempay_service.create_payment_intent')
    def test_create_donation_marks_failed_when_intent_fails(self, mock_create):
        mock_create.return_value = None
        donation, payment_link = donation_service.create_donation(None, {
            'campaign_id': self.campaign.id,
            'amount': Decimal('50.00'),
            'provider': 'wave',
            'phone': '+2207000000',
        })
        self.assertIsNone(payment_link)
        donation.refresh_from_db()
        self.assertEqual(donation.status, Donation.Status.FAILED)


class DonationWebhookGatewayTest(APITestCase):
    """Exercises the full chain: view -> payment_service.handle_webhook
    -> registry.get_gateway('modempay') -> ModemPayGateway.verify_webhook
    -> _normalize_event -> donation_service, with only the SDK boundary
    (modempay_service.verify_and_parse_webhook) mocked."""

    def setUp(self):
        self.campaign = make_campaign()
        self.donation = Donation.objects.create(
            campaign=self.campaign,
            amount=Decimal('200.00'),
            provider='wave',
            phone='+2207000000',
            payment_reference='SD-TEST123',
            gateway='modempay',
            status=Donation.Status.PENDING,
        )
        self.url = reverse('gateway-webhook', kwargs={'gateway_code': 'modempay'})

    @patch('services.modempay_service.verify_and_parse_webhook')
    def test_charge_succeeded_confirms_donation_via_gateway_abstraction(self, mock_verify):
        mock_verify.return_value = {
            'event': 'charge.succeeded',
            'payload': {'id': 'ch_abc', 'metadata': {'donation_reference': 'SD-TEST123'}},
        }
        response = self.client.post(self.url, {'any': 'payload'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.donation.refresh_from_db()
        self.campaign.refresh_from_db()
        self.assertEqual(self.donation.status, Donation.Status.PAID)
        self.assertEqual(self.donation.provider_reference, 'ch_abc')
        self.assertEqual(self.campaign.raised, Decimal('200.00'))
        self.assertEqual(self.campaign.donors_count, 1)

    @patch('services.modempay_service.verify_and_parse_webhook')
    def test_charge_failed_fails_donation(self, mock_verify):
        mock_verify.return_value = {
            'event': 'charge.failed',
            'payload': {'id': 'ch_xyz', 'metadata': {'donation_reference': 'SD-TEST123'}},
        }
        response = self.client.post(self.url, {'any': 'payload'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.donation.refresh_from_db()
        self.assertEqual(self.donation.status, Donation.Status.FAILED)

    @patch('services.modempay_service.verify_and_parse_webhook')
    def test_invalid_signature_returns_400(self, mock_verify):
        mock_verify.return_value = None
        response = self.client.post(self.url, {'any': 'payload'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch('services.modempay_service.verify_and_parse_webhook')
    def test_unhandled_event_type_is_acknowledged(self, mock_verify):
        mock_verify.return_value = {'event': 'customer.created', 'payload': {}}
        response = self.client.post(self.url, {'any': 'payload'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_literal_modempay_path_still_resolves(self):
        # The dashboard-registered webhook URL never changes even though the
        # route is now generic — this pins the exact path, not just the name.
        self.assertEqual(self.url, '/api/v1/payments/webhook/modempay/')


class GatewayWebhookRoutingTest(APITestCase):
    """The route itself is generic (/payments/webhook/<gateway_code>/) —
    these don't touch ModemPay at all, just the URL/dispatch layer."""

    def test_unknown_gateway_code_returns_400_not_500(self):
        url = reverse('gateway-webhook', kwargs={'gateway_code': 'not-a-real-gateway'})
        response = self.client.post(url, {'any': 'payload'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_disabled_gateway_returns_400(self):
        url = reverse('gateway-webhook', kwargs={'gateway_code': 'modempay'})
        with self.settings(PAYMENT_GATEWAYS={'modempay': {'enabled': False, 'demo_mode': True}}):
            response = self.client.post(url, {'any': 'payload'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class PayoutWebhookGatewayTest(APITestCase):
    def setUp(self):
        self.campaign = make_campaign()
        self.payout = Payout.objects.create(
            campaign=self.campaign,
            requested_by=self.campaign.owner,
            amount=Decimal('100.00'),
            net_amount=Decimal('95.00'),
            provider='wave',
            phone='+2207000000',
            reference='PO-TEST123',
            status=Payout.Status.PROCESSING,
        )
        self.url = reverse('gateway-webhook', kwargs={'gateway_code': 'modempay'})

    @patch('services.modempay_service.verify_and_parse_webhook')
    def test_transfer_succeeded_completes_payout(self, mock_verify):
        mock_verify.return_value = {
            'event': 'transfer.succeeded',
            'payload': {'id': 'tr_abc', 'metadata': {'payout_reference': 'PO-TEST123'}},
        }
        response = self.client.post(self.url, {'any': 'payload'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.payout.refresh_from_db()
        self.assertEqual(self.payout.status, Payout.Status.COMPLETED)
        self.assertEqual(self.payout.provider_reference, 'tr_abc')

    @patch('services.modempay_service.verify_and_parse_webhook')
    def test_transfer_failed_fails_payout(self, mock_verify):
        mock_verify.return_value = {
            'event': 'transfer.failed',
            'payload': {'id': 'tr_xyz', 'metadata': {'payout_reference': 'PO-TEST123'}},
        }
        response = self.client.post(self.url, {'any': 'payload'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.payout.refresh_from_db()
        self.assertEqual(self.payout.status, Payout.Status.FAILED)


class RequestPayoutGatewayTest(APITestCase):
    """Mocks the SDK boundary directly (not DEMO_MODE, which is read from
    the real .env at import time and isn't test-isolated) — proving
    request_payout's money-math path still produces the same outcome when
    routed through get_gateway('modempay') instead of calling
    modempay_service directly."""

    def setUp(self):
        self.owner = User.objects.create_user(email='campaigner@example.com', password='pass')
        self.campaign = make_campaign(owner=self.owner, raised=Decimal('500.00'))

    @patch('services.modempay_service.request_disbursement')
    @patch('services.modempay_service.get_balance')
    @patch('services.modempay_service.check_transfer_fee')
    def test_request_payout_completes_via_gateway_abstraction(self, mock_fee, mock_balance, mock_disburse):
        mock_fee.return_value = Decimal('1.00')
        mock_balance.return_value = {'available_balance': 1000, 'payout_balance': 1000}
        mock_disburse.return_value = {'id': 'tr_live_123', 'status': 'completed'}

        payout = payment_service.request_payout(self.owner, {
            'campaign_id': self.campaign.id,
            'amount': Decimal('100.00'),
            'provider': 'wave',
            'phone': '+2207000000',
        })
        self.assertEqual(payout.status, Payout.Status.COMPLETED)
        self.assertEqual(payout.provider_reference, 'tr_live_123')
        self.assertGreater(payout.net_amount, Decimal('0'))
        mock_disburse.assert_called_once()

    @patch('services.modempay_service.get_balance')
    @patch('services.modempay_service.check_transfer_fee')
    def test_request_payout_fails_cleanly_when_balance_unavailable(self, mock_fee, mock_balance):
        mock_fee.return_value = Decimal('1.00')
        mock_balance.return_value = None
        with self.assertRaises(ValidationError):
            payment_service.request_payout(self.owner, {
                'campaign_id': self.campaign.id,
                'amount': Decimal('100.00'),
                'provider': 'wave',
                'phone': '+2207000000',
            })


class PayoutFeePreviewSerializerTest(APITestCase):
    def test_fee_preview_rejects_method_not_supported_for_payouts(self):
        response = self.client.get(
            '/api/v1/payments/payouts/fee-preview/', {'amount': '100', 'provider': 'aps'},
        )
        # Unauthenticated request is rejected before validation runs — this
        # just confirms the endpoint exists and doesn't 500; the actual
        # provider-choice rejection is exercised via the serializer test below.
        self.assertIn(response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    def test_serializer_rejects_unsupported_payout_method_via_registry(self):
        from apps.payments.serializers import PayoutFeePreviewSerializer
        serializer = PayoutFeePreviewSerializer(data={'amount': '100.00', 'provider': 'aps'})
        self.assertFalse(serializer.is_valid())
        self.assertIn('provider', serializer.errors)

    def test_serializer_accepts_wave(self):
        from apps.payments.serializers import PayoutFeePreviewSerializer
        serializer = PayoutFeePreviewSerializer(data={'amount': '100.00', 'provider': 'wave'})
        self.assertTrue(serializer.is_valid(), serializer.errors)

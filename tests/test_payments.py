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

    def test_registry_holds_modempay_and_stripe(self):
        # Pins the registry's current contents so adding another gateway
        # later is a visible, deliberate diff.
        self.assertEqual(set(GATEWAYS.keys()), {'modempay', 'stripe'})

    def test_stripe_gateway_is_donation_only(self):
        from services.gateways.stripe_gateway import StripeGateway
        with self.settings(PAYMENT_GATEWAYS={
            'modempay': {'enabled': True, 'demo_mode': True},
            'stripe': {'enabled': True, 'secret_key': 'sk_test', 'webhook_secret': 'whsec_test', 'currency': 'usd'},
        }):
            gateway = get_gateway('stripe')
            self.assertIsInstance(gateway, StripeGateway)
            self.assertFalse(gateway.supports_payouts)
            self.assertEqual(gateway.default_currency, 'usd')
            self.assertEqual(gateway.default_method, 'card')
            self.assertFalse(gateway.requires_phone)

    def test_stripe_disabled_by_default(self):
        # STRIPE_ENABLED defaults to False — a fresh deploy without Stripe
        # env vars configured shouldn't accidentally expose the gateway.
        with self.settings(PAYMENT_GATEWAYS={'stripe': {'enabled': False}}):
            with self.assertRaises(ValidationError):
                get_gateway('stripe')


class GatewayListViewTest(APITestCase):
    """The frontend builds its provider picker from GET /payments/gateways/
    instead of a hardcoded constant — this pins that contract."""

    def test_lists_only_enabled_gateways(self):
        with self.settings(PAYMENT_GATEWAYS={'modempay': {'enabled': True, 'demo_mode': True}}):
            response = self.client.get('/api/v1/payments/gateways/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        gateways = response.data['data']['gateways']
        self.assertEqual([g['code'] for g in gateways], ['modempay'])
        modempay = gateways[0]
        self.assertTrue(modempay['supports_payouts'])
        self.assertTrue(modempay['requires_phone'])
        self.assertIsNone(modempay['default_method'])
        self.assertEqual(set(modempay['donation_methods']), {'wave', 'aps'})
        self.assertEqual(set(modempay['payout_methods']), {'wave'})

    def test_lists_both_when_stripe_enabled(self):
        with self.settings(PAYMENT_GATEWAYS={
            'modempay': {'enabled': True, 'demo_mode': True},
            'stripe': {'enabled': True, 'secret_key': 'sk_test', 'webhook_secret': 'whsec_test', 'currency': 'usd'},
        }):
            response = self.client.get('/api/v1/payments/gateways/')
        gateways = response.data['data']['gateways']
        self.assertEqual({g['code'] for g in gateways}, {'modempay', 'stripe'})
        stripe = next(g for g in gateways if g['code'] == 'stripe')
        self.assertFalse(stripe['supports_payouts'])
        self.assertFalse(stripe['requires_phone'])
        self.assertEqual(stripe['default_method'], 'card')
        self.assertEqual(stripe['donation_methods'], ['card'])
        self.assertEqual(stripe['payout_methods'], [])

    def test_no_auth_required(self):
        # Donors picking a payment method aren't logged in yet.
        response = self.client.get('/api/v1/payments/gateways/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)


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

    def _stripe_settings(self):
        return {
            'modempay': {'enabled': True, 'demo_mode': True},
            'stripe': {'enabled': True, 'secret_key': 'sk_test', 'webhook_secret': 'whsec_test', 'currency': 'usd'},
        }

    @patch('services.stripe_service.create_checkout_session')
    def test_create_donation_via_stripe_gateway_charges_in_stripe_currency(self, mock_create):
        mock_create.return_value = {'id': 'cs_test_123', 'url': 'https://checkout.stripe.com/pay/cs_test_123'}
        with self.settings(PAYMENT_GATEWAYS=self._stripe_settings()):
            donation, payment_link = donation_service.create_donation(None, {
                'campaign_id': self.campaign.id,
                'amount': Decimal('25.00'),
                'gateway': 'stripe',
                'provider': 'card',
                'phone': '',
            })
        self.assertEqual(donation.gateway, 'stripe')
        # Server-resolved from the gateway's own config, not the client.
        self.assertEqual(donation.currency, 'usd')
        self.assertEqual(payment_link, 'https://checkout.stripe.com/pay/cs_test_123')
        self.assertEqual(donation.provider_reference, 'cs_test_123')
        mock_create.assert_called_once()

    def test_create_donation_rejects_disabled_stripe_gateway(self):
        with self.settings(PAYMENT_GATEWAYS={'stripe': {'enabled': False}}):
            with self.assertRaises(ValidationError):
                donation_service.create_donation(None, {
                    'campaign_id': self.campaign.id,
                    'amount': Decimal('25.00'),
                    'gateway': 'stripe',
                    'provider': 'card',
                    'phone': '',
                })


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


class StripeWebhookGatewayTest(APITestCase):
    """Mirrors DonationWebhookGatewayTest for the Stripe gateway — exercises
    the same view -> handle_webhook -> registry -> StripeGateway.verify_webhook
    -> _normalize_event -> donation_service chain, mocking only the SDK
    boundary (stripe_service.verify_and_parse_webhook)."""

    def setUp(self):
        self.campaign = make_campaign()
        self.donation = Donation.objects.create(
            campaign=self.campaign,
            amount=Decimal('25.00'),
            currency='usd',
            provider='card',
            phone='',
            payment_reference='SD-STRIPE1',
            gateway='stripe',
            status=Donation.Status.PENDING,
        )
        self.url = reverse('gateway-webhook', kwargs={'gateway_code': 'stripe'})
        self.stripe_settings = {
            'modempay': {'enabled': True, 'demo_mode': True},
            'stripe': {'enabled': True, 'secret_key': 'sk_test', 'webhook_secret': 'whsec_test', 'currency': 'usd'},
        }

    @patch('services.stripe_service.verify_and_parse_webhook')
    def test_checkout_session_completed_confirms_donation(self, mock_verify):
        mock_verify.return_value = {
            'type': 'checkout.session.completed',
            'data': {'object': {
                'id': 'cs_test_123',
                'payment_status': 'paid',
                'metadata': {'donation_reference': 'SD-STRIPE1'},
            }},
        }
        with self.settings(PAYMENT_GATEWAYS=self.stripe_settings):
            response = self.client.post(self.url, {'any': 'payload'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.donation.refresh_from_db()
        self.campaign.refresh_from_db()
        self.assertEqual(self.donation.status, Donation.Status.PAID)
        self.assertEqual(self.donation.provider_reference, 'cs_test_123')
        self.assertEqual(self.campaign.raised, Decimal('25.00'))

    @patch('services.stripe_service.verify_and_parse_webhook')
    def test_checkout_session_expired_fails_donation(self, mock_verify):
        mock_verify.return_value = {
            'type': 'checkout.session.expired',
            'data': {'object': {
                'id': 'cs_test_456',
                'metadata': {'donation_reference': 'SD-STRIPE1'},
            }},
        }
        with self.settings(PAYMENT_GATEWAYS=self.stripe_settings):
            response = self.client.post(self.url, {'any': 'payload'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.donation.refresh_from_db()
        self.assertEqual(self.donation.status, Donation.Status.FAILED)

    @patch('services.stripe_service.verify_and_parse_webhook')
    def test_invalid_stripe_signature_returns_400(self, mock_verify):
        mock_verify.return_value = None
        with self.settings(PAYMENT_GATEWAYS=self.stripe_settings):
            response = self.client.post(self.url, {'any': 'payload'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch('services.stripe_service.verify_and_parse_webhook')
    def test_unhandled_stripe_event_is_acknowledged(self, mock_verify):
        mock_verify.return_value = {'type': 'payment_intent.created', 'data': {'object': {}}}
        with self.settings(PAYMENT_GATEWAYS=self.stripe_settings):
            response = self.client.post(self.url, {'any': 'payload'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def _real_signed_event(self, secret, event_type, session_object):
        """Builds a schema-complete Stripe Event payload and signs it with
        the real v1 HMAC-SHA256 scheme construct_event() verifies — this
        test doesn't mock stripe_service at all, so it exercises the actual
        cryptographic check, not just the dispatch logic around it."""
        import time, hmac, hashlib, json
        payload = json.dumps({
            'id': 'evt_test_real',
            'object': 'event',
            'api_version': '2026-06-24.dahlia',
            'created': int(time.time()),
            'livemode': False,
            'pending_webhooks': 0,
            'request': {'id': None, 'idempotency_key': None},
            'type': event_type,
            'data': {'object': session_object},
        }).encode('utf-8')
        timestamp = int(time.time())
        signed_payload = f'{timestamp}.'.encode() + payload
        signature = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
        return payload, f't={timestamp},v1={signature}'

    def test_real_signature_verification_confirms_donation(self):
        # No mocking of stripe_service — this is the actual construct_event()
        # HMAC-SHA256 check running against a self-signed synthetic payload.
        webhook_secret = 'whsec_real_test_secret'
        payload, sig_header = self._real_signed_event(webhook_secret, 'checkout.session.completed', {
            'id': 'cs_test_real_1',
            'object': 'checkout.session',
            'payment_status': 'paid',
            'metadata': {'donation_reference': 'SD-STRIPE1'},
        })
        settings_with_secret = {
            **self.stripe_settings,
            'stripe': {**self.stripe_settings['stripe'], 'webhook_secret': webhook_secret},
        }
        with self.settings(PAYMENT_GATEWAYS=settings_with_secret):
            response = self.client.post(
                self.url, data=payload, content_type='application/json',
                HTTP_STRIPE_SIGNATURE=sig_header,
            )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.donation.refresh_from_db()
        self.assertEqual(self.donation.status, Donation.Status.PAID)

    def test_real_signature_verification_rejects_tampered_signature(self):
        webhook_secret = 'whsec_real_test_secret'
        payload, _ = self._real_signed_event(webhook_secret, 'checkout.session.completed', {
            'id': 'cs_test_real_2',
            'object': 'checkout.session',
            'payment_status': 'paid',
            'metadata': {'donation_reference': 'SD-STRIPE1'},
        })
        settings_with_secret = {
            **self.stripe_settings,
            'stripe': {**self.stripe_settings['stripe'], 'webhook_secret': webhook_secret},
        }
        with self.settings(PAYMENT_GATEWAYS=settings_with_secret):
            response = self.client.post(
                self.url, data=payload, content_type='application/json',
                HTTP_STRIPE_SIGNATURE='t=1,v1=deadbeef',
            )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.donation.refresh_from_db()
        self.assertEqual(self.donation.status, Donation.Status.PENDING)


class ReconcileDonationGatewayTest(APITestCase):
    """donation_service.reconcile_donation_by_reference is the fallback path
    (webhook missed/delayed, or unreachable in local dev) — exercises it
    against both gateways' own status vocabulary via intent_status()."""

    def setUp(self):
        self.campaign = make_campaign()

    @patch('services.modempay_service.retrieve_payment_intent')
    def test_reconciles_successful_modempay_intent(self, mock_retrieve):
        donation = Donation.objects.create(
            campaign=self.campaign, amount=Decimal('100.00'), provider='wave',
            phone='+2207000000', payment_reference='SD-RECON1', gateway='modempay',
            provider_reference='sec_abc', status=Donation.Status.PENDING,
        )
        mock_retrieve.return_value = {'status': 'successful', 'id': 'ch_final'}
        result = donation_service.reconcile_donation_by_reference('SD-RECON1')
        self.assertEqual(result.status, Donation.Status.PAID)
        self.assertEqual(result.provider_reference, 'ch_final')

    @patch('services.modempay_service.retrieve_payment_intent')
    def test_reconciles_failed_modempay_intent(self, mock_retrieve):
        Donation.objects.create(
            campaign=self.campaign, amount=Decimal('100.00'), provider='wave',
            phone='+2207000000', payment_reference='SD-RECON2', gateway='modempay',
            provider_reference='sec_abc', status=Donation.Status.PENDING,
        )
        mock_retrieve.return_value = {'status': 'cancelled', 'id': 'ch_final'}
        result = donation_service.reconcile_donation_by_reference('SD-RECON2')
        self.assertEqual(result.status, Donation.Status.FAILED)

    @patch('services.stripe_service.retrieve_checkout_session')
    def test_reconciles_successful_stripe_intent(self, mock_retrieve):
        donation = Donation.objects.create(
            campaign=self.campaign, amount=Decimal('25.00'), currency='usd', provider='card',
            phone='', payment_reference='SD-RECON3', gateway='stripe',
            provider_reference='cs_test_1', status=Donation.Status.PENDING,
        )
        mock_retrieve.return_value = {'status': 'complete', 'payment_status': 'paid', 'id': 'cs_test_1'}
        with self.settings(PAYMENT_GATEWAYS={
            'modempay': {'enabled': True, 'demo_mode': True},
            'stripe': {'enabled': True, 'secret_key': 'sk_test', 'webhook_secret': 'whsec_test', 'currency': 'usd'},
        }):
            result = donation_service.reconcile_donation_by_reference('SD-RECON3')
        self.assertEqual(result.status, Donation.Status.PAID)

    @patch('services.stripe_service.retrieve_checkout_session')
    def test_reconciles_expired_stripe_intent(self, mock_retrieve):
        Donation.objects.create(
            campaign=self.campaign, amount=Decimal('25.00'), currency='usd', provider='card',
            phone='', payment_reference='SD-RECON4', gateway='stripe',
            provider_reference='cs_test_2', status=Donation.Status.PENDING,
        )
        mock_retrieve.return_value = {'status': 'expired', 'payment_status': 'unpaid', 'id': 'cs_test_2'}
        with self.settings(PAYMENT_GATEWAYS={
            'modempay': {'enabled': True, 'demo_mode': True},
            'stripe': {'enabled': True, 'secret_key': 'sk_test', 'webhook_secret': 'whsec_test', 'currency': 'usd'},
        }):
            result = donation_service.reconcile_donation_by_reference('SD-RECON4')
        self.assertEqual(result.status, Donation.Status.FAILED)


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

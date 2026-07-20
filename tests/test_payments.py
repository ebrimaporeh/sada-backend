from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework.exceptions import ValidationError

from apps.users.models import User
from apps.campaigns.models import Campaign
from apps.donations.models import Donation
from apps.payments.models import Payout, PlatformSettings
from services import donation_service, payment_service
from services.gateways.registry import get_gateway, GATEWAYS
from services.gateways.modempay import ModemPayGateway


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


def set_platform_settings(**kwargs):
    """Gateway enable/disable and Stripe currency/rate are DB-backed
    PlatformSettings fields now, not env/settings.py — tests toggle them
    here instead of Django's self.settings() override."""
    obj = PlatformSettings.get_solo()
    for key, value in kwargs.items():
        setattr(obj, key, value)
    obj.save()
    return obj


class GatewayRegistryTest(APITestCase):
    def test_get_gateway_returns_modempay_instance(self):
        gateway = get_gateway('modempay')
        self.assertIsInstance(gateway, ModemPayGateway)
        self.assertTrue(gateway.supports_payouts)

    def test_get_gateway_unknown_code_raises(self):
        with self.assertRaises(ValidationError):
            get_gateway('does-not-exist')

    def test_get_gateway_disabled_raises(self):
        set_platform_settings(modempay_enabled=False)
        with self.assertRaises(ValidationError):
            get_gateway('modempay')

    def test_registry_holds_modempay_and_stripe(self):
        # Pins the registry's current contents so adding another gateway
        # later is a visible, deliberate diff.
        self.assertEqual(set(GATEWAYS.keys()), {'modempay', 'stripe'})

    def test_stripe_gateway_is_donation_only(self):
        from services.gateways.stripe_gateway import StripeGateway
        set_platform_settings(stripe_enabled=True, stripe_settlement_currency='usd')
        with self.settings(PAYMENT_GATEWAYS={
            'modempay': {'demo_mode': True},
            'stripe': {'secret_key': 'sk_test', 'webhook_secret': 'whsec_test'},
        }):
            gateway = get_gateway('stripe')
            self.assertIsInstance(gateway, StripeGateway)
            self.assertFalse(gateway.supports_payouts)
            self.assertEqual(gateway.default_currency, 'usd')
            self.assertEqual(gateway.default_method, 'card')
            self.assertFalse(gateway.requires_phone)

    def test_stripe_disabled_by_default(self):
        # stripe_enabled defaults to False on a fresh PlatformSettings row —
        # a deploy shouldn't accidentally expose Stripe just because keys
        # happen to be configured in the environment.
        with self.assertRaises(ValidationError):
            get_gateway('stripe')

    def test_gmd_to_minor_units_conversion_uses_admin_rate(self):
        # The bug this guards against: a D100 donation must NOT become
        # $100 (or worse) — it must convert through the admin-configured
        # exchange rate first. At the default rate (70 GMD = 1 USD), D100
        # is ~$1.43, i.e. 143 cents, not 10000.
        set_platform_settings(stripe_enabled=True, gmd_to_settlement_rate=Decimal('70.0000'))
        with self.settings(PAYMENT_GATEWAYS={
            'stripe': {'secret_key': 'sk_test', 'webhook_secret': 'whsec_test'},
        }):
            gateway = get_gateway('stripe')
            minor_units = gateway.convert_gmd_to_minor_units(Decimal('100.00'))
        self.assertEqual(minor_units, 143)  # 100/70 = 1.42857... -> $1.43 -> 143 cents

    def test_gmd_to_minor_units_reflects_updated_rate(self):
        set_platform_settings(stripe_enabled=True, gmd_to_settlement_rate=Decimal('50.0000'))
        with self.settings(PAYMENT_GATEWAYS={
            'stripe': {'secret_key': 'sk_test', 'webhook_secret': 'whsec_test'},
        }):
            gateway = get_gateway('stripe')
            minor_units = gateway.convert_gmd_to_minor_units(Decimal('100.00'))
        self.assertEqual(minor_units, 200)  # 100/50 = $2.00 -> 200 cents


class GatewayListViewTest(APITestCase):
    """The frontend builds its provider picker from GET /payments/gateways/
    instead of a hardcoded constant — this pins that contract."""

    def test_lists_only_enabled_gateways(self):
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
        set_platform_settings(stripe_enabled=True, stripe_settlement_currency='usd')
        with self.settings(PAYMENT_GATEWAYS={
            'modempay': {'demo_mode': True},
            'stripe': {'secret_key': 'sk_test', 'webhook_secret': 'whsec_test'},
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

    def _enable_stripe(self, rate=Decimal('70.0000'), currency='usd'):
        set_platform_settings(stripe_enabled=True, stripe_settlement_currency=currency, gmd_to_settlement_rate=rate)
        return self.settings(PAYMENT_GATEWAYS={
            'modempay': {'demo_mode': True},
            'stripe': {'secret_key': 'sk_test', 'webhook_secret': 'whsec_test'},
        })

    @patch('services.stripe_service.create_checkout_session')
    def test_create_donation_via_stripe_gateway_converts_and_returns_checkout_url(self, mock_create):
        mock_create.return_value = {'id': 'cs_test_123', 'url': 'https://checkout.stripe.com/pay/cs_test_123'}
        with self._enable_stripe(rate=Decimal('70.0000')):
            donation, payment_link = donation_service.create_donation(None, {
                'campaign_id': self.campaign.id,
                'amount': Decimal('100.00'),
                'gateway': 'stripe',
                'provider': 'card',
                'phone': '',
            })
        self.assertEqual(donation.gateway, 'stripe')
        # Server-resolved from the gateway's own config, not the client.
        self.assertEqual(donation.currency, 'usd')
        self.assertEqual(payment_link, 'https://checkout.stripe.com/pay/cs_test_123')
        self.assertEqual(donation.provider_reference, 'cs_test_123')
        # D100 at a rate of 70 GMD/USD -> ~$1.43 -> 143 cents, not 10000.
        mock_create.assert_called_once()
        _, currency_arg, amount_minor_arg = mock_create.call_args[0]
        self.assertEqual(currency_arg, 'usd')
        self.assertEqual(amount_minor_arg, 143)

    @patch('services.stripe_service.create_checkout_session')
    def test_stripe_amount_conversion_respects_configured_rate(self, mock_create):
        mock_create.return_value = {'id': 'cs_test_456', 'url': 'https://checkout.stripe.com/pay/cs_test_456'}
        with self._enable_stripe(rate=Decimal('50.0000')):
            donation_service.create_donation(None, {
                'campaign_id': self.campaign.id,
                'amount': Decimal('100.00'),
                'gateway': 'stripe',
                'provider': 'card',
                'phone': '',
            })
        _, _, amount_minor_arg = mock_create.call_args[0]
        # D100 at a rate of 50 GMD/USD -> $2.00 -> 200 cents.
        self.assertEqual(amount_minor_arg, 200)

    def test_create_donation_rejects_disabled_stripe_gateway(self):
        set_platform_settings(stripe_enabled=False)
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

    @patch('services.modempay_service.find_transaction_by_donation_reference')
    @patch('services.modempay_service.verify_and_parse_webhook')
    def test_charge_succeeded_confirms_donation_via_gateway_abstraction(self, mock_verify, mock_find_txn):
        # ModemPay's PaymentIntent id ('ch_abc' here) and its actual Transaction
        # id are different resources -- resolve_confirmed_reference() looks up
        # the real transaction, so provider_reference ends up being ITS id,
        # not the raw webhook payload's 'id' (see modempay_service.find_transaction_by_donation_reference).
        mock_verify.return_value = {
            'event': 'charge.succeeded',
            'payload': {'id': 'ch_abc', 'metadata': {'donation_reference': 'SD-TEST123'}},
        }
        mock_find_txn.return_value = {'id': 'txn_real_abc', 'metadata': {'donation_reference': 'SD-TEST123'}}
        response = self.client.post(self.url, {'any': 'payload'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.donation.refresh_from_db()
        self.campaign.refresh_from_db()
        self.assertEqual(self.donation.status, Donation.Status.PAID)
        self.assertEqual(self.donation.provider_reference, 'txn_real_abc')
        self.assertEqual(self.campaign.raised, Decimal('200.00'))
        self.assertEqual(self.campaign.donors_count, 1)

    @patch('services.modempay_service.find_transaction_by_donation_reference')
    @patch('services.modempay_service.verify_and_parse_webhook')
    def test_charge_succeeded_falls_back_to_intent_id_when_transaction_not_found(self, mock_verify, mock_find_txn):
        # If ModemPay hasn't recorded the transaction yet (or the lookup
        # fails), confirmation still proceeds using the intent id rather than
        # blocking the donor's confirmation on a refund-only lookup.
        mock_verify.return_value = {
            'event': 'charge.succeeded',
            'payload': {'id': 'ch_abc', 'metadata': {'donation_reference': 'SD-TEST123'}},
        }
        mock_find_txn.return_value = None
        response = self.client.post(self.url, {'any': 'payload'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.donation.refresh_from_db()
        self.assertEqual(self.donation.status, Donation.Status.PAID)
        self.assertEqual(self.donation.provider_reference, 'ch_abc')

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
        set_platform_settings(stripe_enabled=True, stripe_settlement_currency='usd')
        self.stripe_gateway_settings = {
            'modempay': {'demo_mode': True},
            'stripe': {'secret_key': 'sk_test', 'webhook_secret': 'whsec_test'},
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
        with self.settings(PAYMENT_GATEWAYS=self.stripe_gateway_settings):
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
        with self.settings(PAYMENT_GATEWAYS=self.stripe_gateway_settings):
            response = self.client.post(self.url, {'any': 'payload'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.donation.refresh_from_db()
        self.assertEqual(self.donation.status, Donation.Status.FAILED)

    @patch('services.stripe_service.verify_and_parse_webhook')
    def test_invalid_stripe_signature_returns_400(self, mock_verify):
        mock_verify.return_value = None
        with self.settings(PAYMENT_GATEWAYS=self.stripe_gateway_settings):
            response = self.client.post(self.url, {'any': 'payload'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch('services.stripe_service.verify_and_parse_webhook')
    def test_unhandled_stripe_event_is_acknowledged(self, mock_verify):
        mock_verify.return_value = {'type': 'payment_intent.created', 'data': {'object': {}}}
        with self.settings(PAYMENT_GATEWAYS=self.stripe_gateway_settings):
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
            **self.stripe_gateway_settings,
            'stripe': {**self.stripe_gateway_settings['stripe'], 'webhook_secret': webhook_secret},
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
            **self.stripe_gateway_settings,
            'stripe': {**self.stripe_gateway_settings['stripe'], 'webhook_secret': webhook_secret},
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

    @patch('services.modempay_service.find_transaction_by_donation_reference')
    @patch('services.modempay_service.retrieve_payment_intent')
    def test_reconciles_successful_modempay_intent(self, mock_retrieve, mock_find_txn):
        donation = Donation.objects.create(
            campaign=self.campaign, amount=Decimal('100.00'), provider='wave',
            phone='+2207000000', payment_reference='SD-RECON1', gateway='modempay',
            provider_reference='sec_abc', status=Donation.Status.PENDING,
        )
        mock_retrieve.return_value = {'status': 'successful', 'id': 'ch_final'}
        # The intent's own id ('ch_final') is a different resource than the
        # real Transaction -- resolve_confirmed_reference() looks that up,
        # so provider_reference ends up being the transaction's id instead.
        mock_find_txn.return_value = {'id': 'txn_final', 'metadata': {'donation_reference': 'SD-RECON1'}}
        result = donation_service.reconcile_donation_by_reference('SD-RECON1')
        self.assertEqual(result.status, Donation.Status.PAID)
        self.assertEqual(result.provider_reference, 'txn_final')

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
        set_platform_settings(stripe_enabled=True)
        with self.settings(PAYMENT_GATEWAYS={
            'modempay': {'demo_mode': True},
            'stripe': {'secret_key': 'sk_test', 'webhook_secret': 'whsec_test'},
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
        set_platform_settings(stripe_enabled=True)
        with self.settings(PAYMENT_GATEWAYS={
            'modempay': {'demo_mode': True},
            'stripe': {'secret_key': 'sk_test', 'webhook_secret': 'whsec_test'},
        }):
            result = donation_service.reconcile_donation_by_reference('SD-RECON4')
        self.assertEqual(result.status, Donation.Status.FAILED)


class RefundDonationGatewayTest(APITestCase):
    """donation_service.refund_donation is the admin-triggered refund
    execution path — validates PAID-only, calls the gateway's own
    refund_donation(), and unwinds campaign.raised/donors_count the same
    way _confirm_donation incremented them."""

    def setUp(self):
        self.campaign = make_campaign(raised=Decimal('100.00'), donors_count=1)
        self.donor = User.objects.create_user(email='donor@example.com', password='pass')

    def make_paid_donation(self, reference, **kwargs):
        defaults = {
            'campaign': self.campaign, 'donor': self.donor, 'amount': Decimal('100.00'),
            'provider': 'wave', 'phone': '+2207000000', 'payment_reference': reference,
            'gateway': 'modempay', 'provider_reference': 'ch_paid123',
            'status': Donation.Status.PAID,
        }
        defaults.update(kwargs)
        return Donation.objects.create(**defaults)

    @patch('services.modempay_service.reverse_transaction')
    def test_refunds_paid_modempay_donation(self, mock_reverse):
        donation = self.make_paid_donation('SD-REFUND1')
        mock_reverse.return_value = {'id': 'ch_paid123', 'status': 'reversed'}

        result = donation_service.refund_donation(donation, reason='Duplicate charge')

        self.assertEqual(result.status, Donation.Status.REFUNDED)
        self.assertIsNotNone(result.refunded_at)
        self.assertEqual(result.refund_reason, 'Duplicate charge')
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.raised, Decimal('0.00'))
        self.assertEqual(self.campaign.donors_count, 0)

    @patch('services.modempay_service.reverse_transaction')
    def test_gateway_decline_raises_and_makes_no_changes(self, mock_reverse):
        donation = self.make_paid_donation('SD-REFUND2')
        mock_reverse.return_value = None

        with self.assertRaises(ValidationError):
            donation_service.refund_donation(donation)

        donation.refresh_from_db()
        self.assertEqual(donation.status, Donation.Status.PAID)
        self.campaign.refresh_from_db()
        self.assertEqual(self.campaign.raised, Decimal('100.00'))

    def test_non_paid_donation_rejected(self):
        donation = self.make_paid_donation('SD-REFUND3', status=Donation.Status.PENDING)
        with self.assertRaises(ValidationError):
            donation_service.refund_donation(donation)

    @patch('services.stripe_service.refund_checkout_session')
    def test_refunds_paid_stripe_donation(self, mock_refund):
        donation = self.make_paid_donation(
            'SD-REFUND4', gateway='stripe', currency='usd', provider='card',
            phone='', provider_reference='cs_test_paid',
        )
        mock_refund.return_value = {'id': 're_abc', 'status': 'succeeded'}
        set_platform_settings(stripe_enabled=True)
        with self.settings(PAYMENT_GATEWAYS={
            'modempay': {'demo_mode': True},
            'stripe': {'secret_key': 'sk_test', 'webhook_secret': 'whsec_test'},
        }):
            result = donation_service.refund_donation(donation)
        self.assertEqual(result.status, Donation.Status.REFUNDED)
        mock_refund.assert_called_once_with('cs_test_paid')


class ReconcilePayoutGatewayTest(APITestCase):
    """payment_service.reconcile_payout_by_reference is the fallback path for
    a payout stuck PROCESSING when ModemPay's transfer.succeeded/failed
    webhook is missed or delayed — mirrors ReconcileDonationGatewayTest."""

    def setUp(self):
        self.campaign = make_campaign()

    def make_payout(self, reference, **kwargs):
        defaults = {
            'campaign': self.campaign,
            'requested_by': self.campaign.owner,
            'amount': Decimal('100.00'),
            'net_amount': Decimal('95.00'),
            'provider': 'wave',
            'phone': '+2207000000',
            'reference': reference,
            'status': Payout.Status.PROCESSING,
            'provider_reference': 'tr_pending123',
        }
        defaults.update(kwargs)
        return Payout.objects.create(**defaults)

    @patch('services.modempay_service.retrieve_transfer')
    def test_reconciles_completed_transfer(self, mock_retrieve):
        self.make_payout('PO-RECON1')
        mock_retrieve.return_value = {'status': 'completed', 'id': 'tr_pending123'}
        result = payment_service.reconcile_payout_by_reference('PO-RECON1')
        self.assertEqual(result.status, Payout.Status.COMPLETED)

    @patch('services.modempay_service.retrieve_transfer')
    def test_reconciles_failed_transfer(self, mock_retrieve):
        self.make_payout('PO-RECON2')
        mock_retrieve.return_value = {'status': 'cancelled', 'id': 'tr_pending123'}
        result = payment_service.reconcile_payout_by_reference('PO-RECON2')
        self.assertEqual(result.status, Payout.Status.FAILED)

    @patch('services.modempay_service.retrieve_transfer')
    def test_still_pending_transfer_is_untouched(self, mock_retrieve):
        self.make_payout('PO-RECON3')
        mock_retrieve.return_value = {'status': 'pending', 'id': 'tr_pending123'}
        result = payment_service.reconcile_payout_by_reference('PO-RECON3')
        self.assertEqual(result.status, Payout.Status.PROCESSING)

    @patch('services.modempay_service.retrieve_transfer')
    def test_non_processing_payout_is_noop(self, mock_retrieve):
        self.make_payout('PO-RECON4', status=Payout.Status.COMPLETED)
        result = payment_service.reconcile_payout_by_reference('PO-RECON4')
        self.assertEqual(result.status, Payout.Status.COMPLETED)
        mock_retrieve.assert_not_called()

    def test_unknown_reference_returns_none(self):
        result = payment_service.reconcile_payout_by_reference('PO-NOPE')
        self.assertIsNone(result)


class AdminDonationRefundViewTest(APITestCase):
    def test_refund_endpoint_requires_admin(self):
        campaign = make_campaign()
        donation = Donation.objects.create(
            campaign=campaign, amount=Decimal('100.00'), provider='wave',
            phone='+2207000000', payment_reference='SD-VIEWREFUND', gateway='modempay',
            provider_reference='ch_paid123', status=Donation.Status.PAID,
        )
        response = self.client.post(f'/api/v1/donations/admin/{donation.id}/refund/', {})
        self.assertIn(response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))


class GatewayWebhookRoutingTest(APITestCase):
    """The route itself is generic (/payments/webhook/<gateway_code>/) —
    these don't touch ModemPay at all, just the URL/dispatch layer."""

    def test_unknown_gateway_code_returns_400_not_500(self):
        url = reverse('gateway-webhook', kwargs={'gateway_code': 'not-a-real-gateway'})
        response = self.client.post(url, {'any': 'payload'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_disabled_gateway_returns_400(self):
        url = reverse('gateway-webhook', kwargs={'gateway_code': 'modempay'})
        set_platform_settings(modempay_enabled=False)
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


class SweepReconciliationTest(APITestCase):
    """donation_service.sweep_pending_donations / payment_service.sweep_processing_payouts
    are the periodic (Celery Beat) safety net — these test the query/loop
    wrapper only (staleness cutoff, limit, skips fresh records); the actual
    per-record reconciliation is covered by ReconcileDonationGatewayTest /
    ReconcilePayoutGatewayTest above."""

    def setUp(self):
        self.campaign = make_campaign()

    def make_stale_donation(self, reference, minutes_old=30):
        donation = Donation.objects.create(
            campaign=self.campaign, amount=Decimal('100.00'), provider='wave',
            phone='+2207000000', payment_reference=reference, gateway='modempay',
            provider_reference='sec_abc', status=Donation.Status.PENDING,
        )
        Donation.objects.filter(pk=donation.pk).update(
            created_at=timezone.now() - timedelta(minutes=minutes_old)
        )
        return donation

    def make_stale_payout(self, reference, minutes_old=45):
        payout = Payout.objects.create(
            campaign=self.campaign, requested_by=self.campaign.owner,
            amount=Decimal('100.00'), net_amount=Decimal('95.00'), provider='wave',
            phone='+2207000000', reference=reference, status=Payout.Status.PROCESSING,
            provider_reference='tr_abc',
        )
        Payout.objects.filter(pk=payout.pk).update(
            created_at=timezone.now() - timedelta(minutes=minutes_old)
        )
        return payout

    @patch('services.modempay_service.find_transaction_by_donation_reference')
    @patch('services.modempay_service.retrieve_payment_intent')
    def test_sweep_donations_resolves_stale_pending(self, mock_retrieve, mock_find_txn):
        self.make_stale_donation('SD-SWEEP1', minutes_old=30)
        fresh = self.make_stale_donation('SD-SWEEP2', minutes_old=2)
        mock_retrieve.return_value = {'status': 'successful', 'id': 'ch_final'}
        mock_find_txn.return_value = None

        result = donation_service.sweep_pending_donations(older_than_minutes=15)

        self.assertEqual(result, {'checked': 1, 'resolved': 1})
        self.assertEqual(Donation.objects.get(payment_reference='SD-SWEEP1').status, Donation.Status.PAID)
        fresh.refresh_from_db()
        self.assertEqual(fresh.status, Donation.Status.PENDING)

    @patch('services.modempay_service.retrieve_payment_intent')
    @patch('services.modempay_service.find_transaction_by_donation_reference')
    def test_sweep_donations_respects_limit(self, mock_find_txn, mock_retrieve):
        for i in range(3):
            self.make_stale_donation(f'SD-LIMIT{i}', minutes_old=30)
        mock_retrieve.return_value = {'status': 'successful', 'id': 'ch_final'}
        mock_find_txn.return_value = None

        result = donation_service.sweep_pending_donations(older_than_minutes=15, limit=2)
        self.assertEqual(result['checked'], 2)

    @patch('services.modempay_service.retrieve_transfer')
    def test_sweep_payouts_resolves_stale_processing(self, mock_retrieve):
        self.make_stale_payout('PO-SWEEP1', minutes_old=45)
        fresh = self.make_stale_payout('PO-SWEEP2', minutes_old=5)
        mock_retrieve.return_value = {'status': 'completed', 'id': 'tr_abc'}

        result = payment_service.sweep_processing_payouts(older_than_minutes=30)

        self.assertEqual(result, {'checked': 1, 'resolved': 1})
        self.assertEqual(Payout.objects.get(reference='PO-SWEEP1').status, Payout.Status.COMPLETED)
        fresh.refresh_from_db()
        self.assertEqual(fresh.status, Payout.Status.PROCESSING)

    @patch('services.modempay_service.retrieve_transfer')
    def test_sweep_payouts_still_pending_not_counted_resolved(self, mock_retrieve):
        self.make_stale_payout('PO-SWEEP3', minutes_old=45)
        mock_retrieve.return_value = {'status': 'pending', 'id': 'tr_abc'}

        result = payment_service.sweep_processing_payouts(older_than_minutes=30)
        self.assertEqual(result, {'checked': 1, 'resolved': 0})


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


class AdminDonationCampaignFilterTest(APITestCase):
    """get_all_donations()'s `campaign` param -- what the admin campaign
    detail page's Donations tab scopes the list to."""

    def test_filters_to_one_campaign(self):
        c1 = make_campaign()
        c2 = make_campaign()
        Donation.objects.create(
            campaign=c1, amount=Decimal('50.00'), provider='wave', phone='+2207000000',
            payment_reference='SD-CAMPFILTER1', gateway='modempay', status=Donation.Status.PAID,
        )
        Donation.objects.create(
            campaign=c2, amount=Decimal('75.00'), provider='wave', phone='+2207000000',
            payment_reference='SD-CAMPFILTER2', gateway='modempay', status=Donation.Status.PAID,
        )

        results = list(donation_service.get_all_donations({'campaign': str(c1.id)}))
        self.assertEqual([d.payment_reference for d in results], ['SD-CAMPFILTER1'])


class AdminCampaignPayoutListViewTest(APITestCase):
    """AdminCampaignPayoutListView / get_admin_campaign_payouts -- the
    admin campaign detail page's Withdrawals tab, deliberately NOT
    owner-restricted like get_campaign_payouts() (an admin viewing an
    arbitrary campaign isn't that campaign's owner)."""

    def setUp(self):
        self.owner = User.objects.create_user(email='payout-list-owner@example.com', password='pass')
        self.campaign = make_campaign(owner=self.owner)
        self.payout = Payout.objects.create(
            campaign=self.campaign, requested_by=self.owner, amount=Decimal('200.00'),
            net_amount=Decimal('190.00'), provider='wave', phone='+2207000000',
            reference='PO-ADMINVIEW1', status=Payout.Status.COMPLETED,
        )

    def test_endpoint_requires_admin(self):
        url = f'/api/v1/payments/admin/campaign/{self.campaign.id}/payouts/'
        response = self.client.get(url)
        self.assertIn(response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    def test_lists_payouts_for_any_campaign_not_just_owned(self):
        payouts = payment_service.get_admin_campaign_payouts(self.campaign.id)
        self.assertEqual(list(payouts), [self.payout])


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


class PlatformSettingsGatewayAdminTest(APITestCase):
    """Admin control over gateways — the whole point of moving enabled
    flags out of env vars and into this DB-backed, PATCH-able model."""

    def test_admin_can_enable_stripe(self):
        from apps.payments.serializers import PlatformSettingsSerializer
        with self.settings(PAYMENT_GATEWAYS={'stripe': {'secret_key': 'sk_test'}}):
            serializer = PlatformSettingsSerializer(
                PlatformSettings.get_solo(), data={'stripe_enabled': True}, partial=True,
            )
            self.assertTrue(serializer.is_valid(), serializer.errors)
            serializer.save()
        self.assertTrue(PlatformSettings.get_solo().stripe_enabled)

    def test_cannot_enable_stripe_without_secret_key_configured(self):
        from apps.payments.serializers import PlatformSettingsSerializer
        with self.settings(PAYMENT_GATEWAYS={'stripe': {'secret_key': ''}}):
            serializer = PlatformSettingsSerializer(
                PlatformSettings.get_solo(), data={'stripe_enabled': True}, partial=True,
            )
            self.assertFalse(serializer.is_valid())
            self.assertIn('stripe_enabled', serializer.errors)

    def test_gmd_to_settlement_rate_must_be_positive(self):
        from apps.payments.serializers import PlatformSettingsSerializer
        serializer = PlatformSettingsSerializer(
            PlatformSettings.get_solo(), data={'gmd_to_settlement_rate': '0'}, partial=True,
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn('gmd_to_settlement_rate', serializer.errors)

    def test_platform_settings_endpoint_requires_admin_to_patch(self):
        response = self.client.patch('/api/v1/payments/settings/', {'stripe_enabled': True})
        self.assertIn(response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

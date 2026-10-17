"""Regression tests for utils/exceptions.py::custom_exception_handler --
found during a security/resilience audit: concurrent requests hitting a
select_for_update() row lock (donations, payouts) can raise
django.db.OperationalError, and a dict/list-constructed Django
ValidationError (e.g. OrganizationRole.clean()) has no .message
attribute. Both previously fell through to Django's generic unhandled-
exception path instead of the app's documented {"success", "message",
"errors"} envelope -- see api-contracts.md.
"""
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import OperationalError
from django.test import SimpleTestCase
from rest_framework import status

from utils.exceptions import custom_exception_handler


class CustomExceptionHandlerTest(SimpleTestCase):
    def test_operational_error_returns_409_in_the_standard_envelope(self):
        response = custom_exception_handler(OperationalError('database is locked'), context={})
        self.assertIsNotNone(response)
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data, {
            'success': False,
            'message': 'This request conflicted with another in progress. Please try again.',
            'errors': {},
        })

    def test_dict_constructed_validation_error_does_not_crash_the_handler(self):
        exc = DjangoValidationError({'permissions': 'Unknown permission(s): frobnicate'})
        response = custom_exception_handler(exc, context={})
        self.assertIsNotNone(response)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data['success'])
        self.assertIn('Unknown permission(s)', response.data['message'])

    def test_single_string_validation_error_still_works(self):
        exc = DjangoValidationError('That user is not a member of this organization.')
        response = custom_exception_handler(exc, context={})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['message'], 'That user is not a member of this organization.')

from django.core.exceptions import ValidationError, PermissionDenied
from django.db import OperationalError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if response is not None:
        errors = response.data
        message = 'An error occurred.'

        if isinstance(errors, dict):
            if 'detail' in errors:
                message = str(errors['detail'])
                errors = {}
            else:
                first_key = next(iter(errors), None)
                if first_key:
                    first_val = errors[first_key]
                    message = str(first_val[0]) if isinstance(first_val, list) else str(first_val)
        elif isinstance(errors, list):
            message = str(errors[0])
            errors = {}

        response.data = {
            'success': False,
            'message': message,
            'errors': errors if isinstance(errors, dict) else {},
        }
        return response

    if isinstance(exc, ValidationError):
        # exc.message only exists when the error was raised with a single
        # string -- a dict/list-constructed ValidationError (e.g.
        # OrganizationRole.clean()) has no .message attribute at all, which
        # would otherwise turn this branch itself into an unhandled 500.
        # exc.messages is a property that always works, for either shape.
        return Response(
            {'success': False, 'message': str(exc.messages[0]), 'errors': {}},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if isinstance(exc, PermissionDenied):
        return Response(
            {'success': False, 'message': str(exc), 'errors': {}},
            status=status.HTTP_403_FORBIDDEN,
        )

    if isinstance(exc, OperationalError):
        # Raised when a concurrent request can't immediately acquire a
        # select_for_update() row lock (donations/payouts both take one --
        # see services/donation_service.py, services/payment_service.py).
        # SQLite surfaces this as "database is locked"; Postgres can raise
        # the same exception type for a lock-wait timeout or a detected
        # deadlock under concurrent load. Either way it's transient and
        # safe to retry -- without this, it fell through to Django's
        # generic unhandled-exception path (bypassing the success/message/
        # errors envelope every other response uses, and in production
        # with DEBUG left on, see security.md's #0, it would leak a full
        # traceback).
        return Response(
            {'success': False, 'message': 'This request conflicted with another in progress. Please try again.', 'errors': {}},
            status=status.HTTP_409_CONFLICT,
        )

    return None

from django.core.exceptions import ValidationError, PermissionDenied
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
        return Response(
            {'success': False, 'message': str(exc.message), 'errors': {}},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if isinstance(exc, PermissionDenied):
        return Response(
            {'success': False, 'message': str(exc), 'errors': {}},
            status=status.HTTP_403_FORBIDDEN,
        )

    return None

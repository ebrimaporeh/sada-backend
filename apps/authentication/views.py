from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.views import TokenRefreshView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from drf_spectacular.utils import extend_schema

from services import auth_service
from services.google_oauth_service import verify_google_token, get_or_create_google_user, link_google_account
from apps.users.serializers import UserSerializer
from throttling.base import LoginThrottle, RegisterThrottle, ResendVerificationThrottle, PasswordResetRequestThrottle
from .serializers import (
    RegisterSerializer, LoginSerializer, ChangePasswordSerializer, GoogleOAuthSerializer,
    SetPasswordSerializer, RequestPasswordResetSerializer,
)


@extend_schema(tags=['Authentication'])
class RegisterView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [RegisterThrottle]

    @extend_schema(request=RegisterSerializer, responses={201: UserSerializer})
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user, tokens = auth_service.register_user(**serializer.validated_data)
        return Response({
            'success': True,
            'message': 'Registration successful. Please verify your email.',
            'data': {
                'user': UserSerializer(user, context={'request': request}).data,
                'tokens': tokens,
            },
        }, status=status.HTTP_201_CREATED)


@extend_schema(tags=['Authentication'])
class LoginView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [LoginThrottle]

    @extend_schema(request=LoginSerializer)
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user, tokens = auth_service.login_user(
            email=serializer.validated_data['email'],
            password=serializer.validated_data['password'],
        )
        return Response({
            'success': True,
            'message': 'Login successful.',
            'data': {
                'user': UserSerializer(user, context={'request': request}).data,
                'tokens': tokens,
            },
        })


@extend_schema(tags=['Authentication'])
class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get('refresh')
        if not refresh_token:
            return Response(
                {'success': False, 'message': 'Refresh token required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except TokenError:
            pass
        return Response({'success': True, 'message': 'Logged out successfully.'})


@extend_schema(tags=['Authentication'])
class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=ChangePasswordSerializer)
    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        auth_service.change_password(
            user=request.user,
            old_password=serializer.validated_data['old_password'],
            new_password=serializer.validated_data['new_password'],
        )
        return Response({'success': True, 'message': 'Password changed successfully.'})


@extend_schema(tags=['Authentication'])
class SetPasswordView(APIView):
    """For accounts with no usable password yet (Google-only signups) —
    see ChangePasswordView for accounts that already have one."""
    permission_classes = [IsAuthenticated]

    @extend_schema(request=SetPasswordSerializer)
    def post(self, request):
        serializer = SetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        auth_service.set_password(user=request.user, new_password=serializer.validated_data['new_password'])
        return Response({'success': True, 'message': 'Password set successfully.'})


@extend_schema(tags=['Authentication'])
class RequestPasswordResetView(APIView):
    """Shadows django_rest_passwordreset's own request-token endpoint at the
    same URL (see apps/authentication/urls.py) so an organization's recovery
    emails work here too, with zero change for individual accounts."""
    permission_classes = [AllowAny]
    throttle_classes = [PasswordResetRequestThrottle]

    @extend_schema(request=RequestPasswordResetSerializer)
    def post(self, request):
        serializer = RequestPasswordResetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        auth_service.request_password_reset(serializer.validated_data['email'])
        return Response({'status': 'OK'})


@extend_schema(tags=['Authentication'])
class VerifyEmailView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        token = request.data.get('token')
        if not token:
            return Response(
                {'success': False, 'message': 'Verification token required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        auth_service.verify_email(token=token)
        return Response({'success': True, 'message': 'Email verified successfully.'})


@extend_schema(tags=['Authentication'])
class ResendVerificationEmailView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [ResendVerificationThrottle]

    def post(self, request):
        email = request.data.get('email')
        if not email:
            return Response(
                {'success': False, 'message': 'Email is required.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        auth_service.resend_verification_email(email=email)
        return Response({'success': True, 'message': 'If that email is registered and unverified, a new verification link has been sent.'})


@extend_schema(tags=['Authentication'])
class GoogleOAuthView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(request=GoogleOAuthSerializer)
    def post(self, request):
        serializer = GoogleOAuthSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        id_token_str = serializer.validated_data['id_token']

        # Verify Google token and extract user info
        google_data = verify_google_token(id_token_str)

        # Get or create user
        user = get_or_create_google_user(google_data, account_type=serializer.validated_data.get('account_type'))

        # Generate JWT tokens
        tokens = auth_service._get_tokens_for_user(user)

        return Response({
            'success': True,
            'message': 'Login successful via Google.',
            'data': {
                'user': UserSerializer(user, context={'request': request}).data,
                'tokens': tokens,
            },
        }, status=status.HTTP_200_OK)


@extend_schema(tags=['Authentication'])
class GoogleLinkView(APIView):
    """Explicitly attach a Google account to the current (already logged-in)
    user, e.g. a 'Connect Google' button in account settings."""
    permission_classes = [IsAuthenticated]

    @extend_schema(request=GoogleOAuthSerializer, responses={200: UserSerializer})
    def post(self, request):
        serializer = GoogleOAuthSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = link_google_account(request.user, serializer.validated_data['id_token'])
        return Response({
            'success': True,
            'message': 'Google account connected successfully.',
            'data': {'user': UserSerializer(user, context={'request': request}).data},
        })

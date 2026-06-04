from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework_simplejwt.views import TokenRefreshView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from drf_spectacular.utils import extend_schema

from services import auth_service
from apps.users.serializers import UserSerializer
from .serializers import RegisterSerializer, LoginSerializer, ChangePasswordSerializer


@extend_schema(tags=['Authentication'])
class RegisterView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(request=RegisterSerializer, responses={201: UserSerializer})
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user, tokens = auth_service.register_user(**serializer.validated_data)
        return Response({
            'success': True,
            'message': 'Registration successful. Please verify your email.',
            'data': {
                'user': UserSerializer(user).data,
                'tokens': tokens,
            },
        }, status=status.HTTP_201_CREATED)


@extend_schema(tags=['Authentication'])
class LoginView(APIView):
    permission_classes = [AllowAny]

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
                'user': UserSerializer(user).data,
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

# Google OAuth 2.0 Setup Guide

## Overview

This implementation adds "Sign in with Google" functionality using:
- Backend: Django REST Framework with JWT authentication
- Frontend: React with @react-oauth/google
- Token verification: google-auth library (no client secret needed on backend)

## Backend Setup

### 1. Environment Variables

Add to your `.env` file:

```bash
GOOGLE_OAUTH_CLIENT_ID=YOUR_GOOGLE_CLIENT_ID_HERE
```

Get your Google Client ID from:
1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a new project
3. Enable Google+ API
4. Create OAuth 2.0 credentials (Web Application)
5. Add authorized redirect URIs:
   - http://localhost:5173 (local dev)
   - http://localhost:5174 (local dev)
   - https://yourdomain.com (production)
6. Copy the Client ID

### 2. Install Dependencies

```bash
pip install google-auth==2.27.0
```

### 3. Files Created/Modified

- **services/google_oauth_service.py** - Token verification and user creation
- **apps/authentication/views.py** - Added GoogleOAuthView
- **apps/authentication/serializers.py** - Added GoogleOAuthSerializer
- **apps/authentication/urls.py** - Added /auth/google/ endpoint

### 4. API Endpoint

**POST** `/api/v1/auth/google/`

Request:
```json
{
  "id_token": "google-id-token-from-frontend"
}
```

Response:
```json
{
  "success": true,
  "message": "Login successful via Google.",
  "data": {
    "user": {
      "id": "...",
      "email": "user@example.com",
      "first_name": "John",
      "last_name": "Doe",
      ...
    },
    "tokens": {
      "access": "jwt-access-token",
      "refresh": "jwt-refresh-token"
    }
  }
}
```

### 5. How It Works

1. **Frontend sends ID token** - GoogleOAuthProvider captures ID token from Google
2. **Backend verifies token** - Uses Google's public certificates via google-auth library
3. **Extract user info** - email, name, google_sub from token payload
4. **Get or create user** - Checks if user exists by email, creates if not
5. **Return JWT tokens** - Frontend stores access + refresh tokens in localStorage

### 6. Security Notes

- **Never use Google client secret in backend** ✅ Correctly uses GOOGLE_OAUTH_CLIENT_ID only
- **ID token verified using Google's certificates** ✅ google-auth library handles this
- **Email marked as verified** ✅ Google verifies emails, so email_verified=True
- **HTTPS in production** ⚠️ Ensure production uses HTTPS for tokens

## Frontend Setup

### 1. Environment Variables

Add to `.env` file:

```bash
VITE_GOOGLE_CLIENT_ID=YOUR_GOOGLE_CLIENT_ID_HERE
```

### 2. Install Dependencies

```bash
npm install @react-oauth/google
```

### 3. Files Created/Modified

- **.env** - Added VITE_GOOGLE_CLIENT_ID
- **src/main.jsx** - Wrapped app with GoogleOAuthProvider
- **src/api/authApi.js** - Added googleOAuth() method
- **src/hooks/useAuth.js** - Added useGoogleOAuth() hook
- **src/features/auth/components/LoginForm.jsx** - Added GoogleLogin component

### 4. How It Works

1. **GoogleOAuthProvider wraps app** - Initializes Google OAuth with Client ID
2. **GoogleLogin component** - Popup button on login page
3. **User clicks button** - Google popup opens
4. **User authenticates** - Google returns ID token in credentialResponse
5. **Send to backend** - POST /api/v1/auth/google/ with id_token
6. **Store tokens** - Save access + refresh tokens in localStorage
7. **Redirect to dashboard** - useGoogleOAuth hook handles navigation

## Testing

### Local Development

1. **Set GOOGLE_OAUTH_CLIENT_ID** in both backend `.env` and frontend `.env`
2. **Start backend**: `python manage.py runserver`
3. **Start frontend**: `npm run dev`
4. **Visit login page** and test Google button

### Test Google OAuth Locally

Use a test Google account or create a test project in Google Cloud Console.

### Common Issues

**Issue**: "Invalid audience" error
- **Fix**: Ensure GOOGLE_OAUTH_CLIENT_ID matches your Google project

**Issue**: CORS error
- **Fix**: Check frontend origin is in Google Cloud Console authorized origins

**Issue**: ID token not returned
- **Fix**: Ensure GoogleOAuthProvider is wrapping the entire app

## Production Setup

### 1. Update Environment Variables

In your deployment platform (Vercel, Render, etc.):

**Frontend (Vercel)**:
- `VITE_GOOGLE_CLIENT_ID` - Your production Google Client ID
- `VITE_API_URL` - Backend API URL (https://your-backend.com/api/v1)

**Backend (Render)**:
- `GOOGLE_OAUTH_CLIENT_ID` - Your production Google Client ID
- `ALLOWED_HOSTS` - Include your frontend domains

### 2. Google Cloud Console

1. Add production URLs to authorized origins
2. Add production URLs to authorized redirect URIs
3. Use same GOOGLE_OAUTH_CLIENT_ID for both dev and prod (or create separate credentials)

### 3. HTTPS Requirement

Google OAuth only works over HTTPS in production. Ensure:
- Frontend deployed on HTTPS
- Backend deployed on HTTPS
- Cookies/tokens are secure-only

## Architecture

```
User (Browser)
  ↓
GoogleLogin Component (frontend)
  ↓
Google OAuth Popup
  ↓
User Authenticates
  ↓
Google returns ID token → credentialResponse.credential
  ↓
POST /api/v1/auth/google/ {id_token}
  ↓
Backend: verify_google_token()
  Uses: GOOGLE_OAUTH_CLIENT_ID + google.auth library
  ↓
Extract: email, name, google_sub
  ↓
get_or_create_google_user()
  ↓
_get_tokens_for_user()
  Returns: JWT access + refresh tokens
  ↓
Frontend: Store in localStorage
  ↓
Redirect to /dashboard
```

## FAQ

**Q: Do I need to store Google client secret on backend?**
A: No! Only use GOOGLE_OAUTH_CLIENT_ID. The google-auth library verifies using Google's public certificates.

**Q: What about user profile picture?**
A: Currently not stored. Extend google_oauth_service.py to save picture field if needed.

**Q: Can I use multiple Google projects?**
A: Yes, but use separate GOOGLE_OAUTH_CLIENT_IDs for dev/prod or different apps.

**Q: How do I link Google login to existing accounts?**
A: Modify get_or_create_google_user() to check for existing user by email first, then create Google linkage.

**Q: Token expiration?**
A: JWT tokens expire based on settings in settings/base.py. Refresh token endpoint handles renewal.

## Links

- [Google Identity Services](https://developers.google.com/identity)
- [Google Cloud Console](https://console.cloud.google.com)
- [@react-oauth/google](https://www.npmjs.com/package/@react-oauth/google)
- [google-auth-library-python](https://google-auth.readthedocs.io/)
- [Django REST SimpleJWT](https://django-rest-framework-simplejwt.readthedocs.io/)

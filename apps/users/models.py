import uuid
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.db import models
from apps.core.models import BaseModel
from apps.core.validators import validate_image_size
from utils.upload_paths import (
    user_avatar_path, identity_photo_front_path, identity_photo_back_path,
    organization_logo_path, organization_registration_document_path, organization_photo_path,
)


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Email is required.')
        email = self.normalize_email(email)
        extra_fields.setdefault('is_active', True)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', User.Role.ADMIN)
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    class Role(models.TextChoices):
        ADMIN = 'admin', 'Admin'
        USER = 'user', 'User'
        PREMIUM = 'premium', 'Premium User'
        MODERATOR = 'moderator', 'Moderator'
        FINANCE_OFFICER = 'finance_officer', 'Finance Officer'

    class AccountType(models.TextChoices):
        # Vestigial as of the individual+organization-membership redesign --
        # every account registers (and stays) INDIVIDUAL now; an
        # organization is a separate multi-member entity an individual
        # creates/joins afterward (see apps.organizations), not a type of
        # User row. ORGANIZATION is kept only so existing data/migrations
        # referencing it stay meaningful; nothing sets it going forward.
        INDIVIDUAL = 'individual', 'Individual'
        ORGANIZATION = 'organization', 'Organization'

    class Region(models.TextChoices):
        BANJUL = 'banjul', 'Banjul'
        KANIFING = 'kanifing', 'Kanifing'
        BRIKAMA = 'brikama', 'Brikama'
        MANSAKONKO = 'mansakonko', 'Mansakonko'
        KEREWAN = 'kerewan', 'Kerewan'
        KUNTAUR = 'kuntaur', 'Kuntaur'
        JANJANBUREH = 'janjanbureh', 'Janjanbureh'
        BASSE = 'basse', 'Basse'

    class PaymentProvider(models.TextChoices):
        # ModemPay is the payment gateway, not itself a provider — these are
        # the underlying networks it processes payments through.
        WAVE = 'wave', 'Wave'
        APS = 'aps', 'APS Wallet'
        AFRIMONEY = 'afrimoney', 'Afrimoney'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=150, blank=True)
    last_name = models.CharField(max_length=150, blank=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.USER)
    account_type = models.CharField(max_length=20, choices=AccountType.choices, default=AccountType.INDIVIDUAL)
    avatar = models.ImageField(upload_to=user_avatar_path, null=True, blank=True, validators=[validate_image_size])
    phone = models.CharField(max_length=20, blank=True)
    bio = models.TextField(blank=True)
    region = models.CharField(max_length=20, choices=Region.choices, blank=True)
    default_payment_provider = models.CharField(
        max_length=20, choices=PaymentProvider.choices, blank=True,
    )
    default_payment_phone = models.CharField(max_length=20, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    email_verified = models.BooleanField(default=False)
    is_verified = models.BooleanField(default=False)
    # Set only by _anonymize_account (services/user_service.py) -- distinct
    # from is_active, which also covers a plain deactivation an admin can
    # reverse. A deleted account is never reactivated, so admin list views
    # (get_regular_users/get_staff_users) filter this out permanently
    # instead of relying on matching the deleted-{id}@deleted.sada.gm email
    # pattern those accounts get renamed to.
    is_deleted = models.BooleanField(default=False)
    # Google's unique, stable subject identifier for this account — set on
    # Google sign-in/link, null for accounts that have never used Google.
    # Distinct from email match: lets an account keep working with Google
    # even if the user later changes their email on either side.
    google_sub = models.CharField(max_length=255, null=True, blank=True, unique=True)

    # Public fundraiser profile preferences
    show_total_raised = models.BooleanField(
        default=True,
        help_text='Whether total funds raised is shown on your public fundraiser profile.',
    )

    # Notification settings
    notify_donations_received = models.BooleanField(default=True)
    notify_campaign_approved = models.BooleanField(default=True)
    notify_campaign_rejected = models.BooleanField(default=True)
    notify_goal_reached = models.BooleanField(default=True)
    notify_new_comment = models.BooleanField(default=False)
    notify_new_update = models.BooleanField(default=False)
    notify_marketing = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'User'
        verbose_name_plural = 'Users'

    def __str__(self):
        return self.email

    @property
    def full_name(self):
        # Always this user's own name now -- an organization's display name
        # is Organization.organization_name, a separate concept reached via
        # membership, never a stand-in for any one member's own name.
        return f'{self.first_name} {self.last_name}'.strip() or self.email

    @property
    def organizations(self):
        """Every Organization this user is currently a member of."""
        from apps.users.models import Organization
        return Organization.objects.filter(memberships__user=self)

    @property
    def is_admin(self):
        return self.role == self.Role.ADMIN

    @property
    def is_premium(self):
        return self.role in (self.Role.PREMIUM, self.Role.ADMIN)

    @property
    def is_moderator(self):
        return self.role in (self.Role.MODERATOR, self.Role.ADMIN)

    @property
    def is_google_linked(self):
        return bool(self.google_sub)


class IdentityVerification(BaseModel):
    """A user's submission of a government ID for manual admin review.

    Distinct from email_verified (proves email ownership, automatic) —
    is_verified on User only flips to True once an admin approves one of
    these requests.
    """
    class IdType(models.TextChoices):
        NATIONAL_ID = 'national_id', 'National ID Card'
        PASSPORT = 'passport', 'Passport'
        DRIVERS_LICENSE = 'drivers_license', "Driver's License"

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending Review'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='verification_requests')
    id_type = models.CharField(max_length=20, choices=IdType.choices)
    id_number = models.CharField(max_length=50)
    id_photo_front = models.ImageField(upload_to=identity_photo_front_path, validators=[validate_image_size])
    id_photo_back = models.ImageField(upload_to=identity_photo_back_path, null=True, blank=True, validators=[validate_image_size])
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    rejection_reason = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_verifications',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Identity Verification'
        verbose_name_plural = 'Identity Verifications'

    def __str__(self):
        return f'{self.user.email} — {self.status}'


class TermsAcceptance(BaseModel):
    """Records that a user explicitly agreed to the Terms of Service (and,
    via the same signup checkbox, the Privacy Policy it links to) at a
    specific moment and against a specific version of that content -- so
    a dispute or regulator asking "did this user actually agree, and to
    which version" has an answer instead of nothing.

    `terms_version` is a short hash of LegalContent.terms_content's text at
    acceptance time, not a version *number* -- there's no separate version
    field on that admin-edited singleton row, and its own updated_at covers
    all four legal pages (Help/Trust & Safety/Privacy/Terms) at once, so it
    can't tell you whether the *Terms* text specifically changed. Hashing
    the actual text pins down exactly what was agreed to regardless of what
    else on that row was edited before or after.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='terms_acceptances')
    terms_version = models.CharField(max_length=64)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Terms Acceptance'
        verbose_name_plural = 'Terms Acceptances'

    def __str__(self):
        return f'{self.user.email} accepted terms {self.terms_version} at {self.created_at}'


class Organization(BaseModel):
    """A real multi-member entity — no longer 1:1 with a single User (see
    apps.organizations for OrganizationMembership/OrganizationRole, which
    is what actually grants members access). `created_by` is who registered
    it, kept for audit/display only; it carries no special access on its
    own beyond whatever OrganizationMembership role that user currently
    holds (see OrganizationMembership's docstring — ownership is
    transferable, so created_by intentionally never gates anything)."""
    organization_name = models.CharField(max_length=200)
    organization_type = models.ForeignKey(
        'organizations.OrganizationType', on_delete=models.PROTECT, related_name='organizations',
    )
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_organizations',
    )
    # No contact_person_name field -- a "contact person" is a real member
    # (OrganizationMembership.is_contact_person), not free text. The creator
    # is flagged as one automatically at creation (see
    # organization_service.create_organization); any other member can be
    # flagged too (organization_service.set_contact_person), so "who do we
    # call" always resolves to an actual person with their own name/email/
    # phone on their User record, not a name that silently drifts from
    # reality as membership changes.
    # The organization's own primary and second numbers -- previously
    # implicit as "phone lives on the org's one User", but now that an org
    # has multiple members it needs its own, not borrowed from whichever
    # member happens to hold it.
    phone = models.CharField(max_length=20, blank=True)
    phone_2 = models.CharField(max_length=20)
    # Optional — used for full account recovery (password reset) and CC'd
    # on withdrawal/payout notifications, in addition to the member who
    # requested the payout.
    recovery_email_1 = models.EmailField(blank=True)
    recovery_email_2 = models.EmailField(blank=True)
    logo = models.ImageField(upload_to=organization_logo_path, null=True, blank=True, validators=[validate_image_size])
    # Distinct from any individual member's own User.is_verified -- an org's
    # identity verification (OrganizationVerification) is about the org
    # entity, not whichever member happened to submit it.
    is_verified = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'Organization'
        verbose_name_plural = 'Organizations'

    def __str__(self):
        return self.organization_name


class OrganizationVerification(BaseModel):
    """An organization's submission of registration proof for manual admin
    review — the organization analog of IdentityVerification, but scoped to
    the organization's own legal existence (a registration certificate),
    not any individual member's personal ID — an org isn't verified by
    checking who happens to be submitting the paperwork today. Approval
    flips Organization.is_verified, same is_verified-flips-on-approve
    invariant as IdentityVerification, just on a different model (see
    verification_service)."""
    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending Review'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='verification_requests')
    submitted_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='organization_verification_requests')
    # The registration/certificate number printed on the document itself --
    # lets admin reviewers cross-check it without opening the image.
    registration_number = models.CharField(max_length=100)
    # Proof the organization is real — a registration certificate, government
    # letter, etc.
    registration_document = models.ImageField(upload_to=organization_registration_document_path, validators=[validate_image_size])
    # A photo of the organization (premises, event, logo) — copied onto
    # Organization.logo on approval.
    organization_photo = models.ImageField(upload_to=organization_photo_path, validators=[validate_image_size])
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    rejection_reason = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_organization_verifications',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Organization Verification'
        verbose_name_plural = 'Organization Verifications'

    def __str__(self):
        return f'{self.organization.organization_name} — {self.status}'


class OrganizationChangeRequest(BaseModel):
    """A request to change one of an organization's account-recovery-
    critical fields (primary/second phone, either recovery email) --
    every field here lives on Organization now (previously "primary phone"
    meant the org's one User.phone; that stopped making sense once an org
    could have multiple members, so Organization gained its own `phone`).

    These fields are never editable directly — a single compromised or
    careless member could otherwise quietly redirect account recovery and
    withdrawal notifications to themselves. Each request targets exactly one
    field; phone changes need admin approval, recovery-email changes are
    self-confirmed by the proposed address instead (see
    organization_change_service).
    """
    class Field(models.TextChoices):
        PHONE = 'phone', 'Primary Phone Number'
        PHONE_2 = 'phone_2', 'Second Phone Number'
        RECOVERY_EMAIL_1 = 'recovery_email_1', 'Recovery Email 1'
        RECOVERY_EMAIL_2 = 'recovery_email_2', 'Recovery Email 2'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending Review'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='change_requests')
    submitted_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='organization_change_requests')
    field_name = models.CharField(max_length=20, choices=Field.choices)
    # Snapshot of the value at request time, for the admin to compare
    # against — not re-read live, since it could change before review.
    current_value = models.CharField(max_length=255, blank=True)
    proposed_value = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    rejection_reason = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_organization_change_requests',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Organization Change Request'
        verbose_name_plural = 'Organization Change Requests'

    def __str__(self):
        return f'{self.organization.organization_name} — {self.field_name} — {self.status}'

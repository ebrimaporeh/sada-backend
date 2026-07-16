from django.db import models
from django.utils.text import slugify
from django.conf import settings
from apps.core.models import BaseModel
from apps.core.validators import validate_image_size
from utils.upload_paths import (
    category_image_path, campaign_cover_image_path, campaign_gallery_image_path, campaign_update_image_path,
)


class Category(BaseModel):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=50, blank=True)
    image = models.ImageField(upload_to=category_image_path, null=True, blank=True, validators=[validate_image_size])
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Category'
        verbose_name_plural = 'Categories'

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class Campaign(BaseModel):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'Draft'
        PENDING = 'pending', 'Pending Review'
        APPROVED = 'approved', 'Approved'
        ACTIVE = 'active', 'Active'
        COMPLETED = 'completed', 'Completed'
        REJECTED = 'rejected', 'Rejected'
        SUSPENDED = 'suspended', 'Suspended'

    class Region(models.TextChoices):
        BANJUL = 'banjul', 'Banjul'
        KANIFING = 'kanifing', 'Kanifing'
        BRIKAMA = 'brikama', 'Brikama'
        MANSAKONKO = 'mansakonko', 'Mansakonko'
        KEREWAN = 'kerewan', 'Kerewan'
        KUNTAUR = 'kuntaur', 'Kuntaur'
        JANJANBUREH = 'janjanbureh', 'Janjanbureh'
        BASSE = 'basse', 'Basse'

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='campaigns',
    )
    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='campaigns',
    )
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True)
    short_description = models.CharField(max_length=500)
    story = models.TextField()
    goal = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default='GMD')
    raised = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    donors_count = models.PositiveIntegerField(default=0)
    views_count = models.PositiveIntegerField(default=0)
    deadline = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    beneficiary = models.CharField(max_length=200, blank=True)
    beneficiary_relationship = models.CharField(max_length=100, blank=True)
    region = models.CharField(max_length=20, choices=Region.choices, blank=True)
    is_urgent = models.BooleanField(default=False)
    is_featured = models.BooleanField(default=False)
    is_anonymous = models.BooleanField(default=False)
    cover_image = models.ImageField(upload_to=campaign_cover_image_path, null=True, blank=True, validators=[validate_image_size])
    rejection_reason = models.TextField(blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Campaign'
        verbose_name_plural = 'Campaigns'

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.title)
            slug = base
            n = 1
            while Campaign.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f'{base}-{n}'
                n += 1
            self.slug = slug
        super().save(*args, **kwargs)

    @property
    def progress_percent(self):
        if not self.goal:
            return 0
        return min(int((self.raised / self.goal) * 100), 100)

    @property
    def is_active(self):
        return self.status == self.Status.ACTIVE

    @property
    def is_funded(self):
        return self.raised >= self.goal


class CampaignImage(BaseModel):
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to=campaign_gallery_image_path, validators=[validate_image_size])
    order = models.PositiveSmallIntegerField(default=0)
    is_cover = models.BooleanField(default=False)

    class Meta:
        ordering = ['order']


class CampaignUpdate(BaseModel):
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='updates')
    title = models.CharField(max_length=200)
    content = models.TextField()
    posted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
    )

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.campaign.title}: {self.title}'


class CampaignUpdateImage(BaseModel):
    update = models.ForeignKey(CampaignUpdate, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to=campaign_update_image_path, validators=[validate_image_size])
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['order']


class CampaignReport(BaseModel):
    class Reason(models.TextChoices):
        FRAUDULENT = 'fraudulent', 'Fraudulent activity'
        MISLEADING = 'misleading', 'Misleading information'
        INAPPROPRIATE = 'inappropriate', 'Inappropriate content'
        SPAM = 'spam', 'Spam or scam'
        DUPLICATE = 'duplicate', 'Duplicate campaign'
        OTHER = 'other', 'Other'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending Review'
        INVESTIGATING = 'investigating', 'Under Investigation'
        RESOLVED = 'resolved', 'Resolved'
        DISMISSED = 'dismissed', 'Dismissed'

    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name='reports')
    reported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='campaign_reports',
    )
    reporter_name = models.CharField(max_length=200, blank=True)
    reporter_phone = models.CharField(max_length=20, blank=True)
    reason = models.CharField(max_length=20, choices=Reason.choices)
    description = models.TextField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    admin_notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.campaign.title}: {self.reason}'

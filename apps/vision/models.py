from django.db import models
from django.utils.text import slugify
from apps.core.models import BaseModel


class VisionTopic(BaseModel):
    """An admin-edited, publicly-readable document describing one area of
    the platform's roadmap -- e.g. "Entity & Account Architecture",
    "Organizations & Osusu", "Investment Platform". Each topic is broken
    into the same four phases so a reader can always find "what exists
    today" vs. "what's planned," regardless of which topic they're on.

    Content fields are markdown (rendered the same way as Legal/Help
    content, see MarkdownContent on the frontend) and deliberately not
    split further per phase (e.g. into separate "technical"/"business"/
    "legal" fields) -- the ask was for each phase's writeup to weave those
    angles together in prose, not to fill in a rigid template section by
    section.
    """
    slug = models.SlugField(max_length=120, unique=True)
    title = models.CharField(max_length=200)
    # Short teaser shown on the public index page and in the admin list --
    # distinct from current_state, which is the actual documentation.
    summary = models.CharField(max_length=300, blank=True)
    order = models.PositiveSmallIntegerField(default=0)
    # Drafts are editable and previewable by admins but return 404 on the
    # public endpoints -- same "write now, publish when ready" model as a
    # campaign's own draft status.
    is_published = models.BooleanField(default=False)

    current_state = models.TextField(blank=True)
    implementation = models.TextField(blank=True)
    short_term_vision = models.TextField(blank=True)
    long_term_vision = models.TextField(blank=True)

    class Meta:
        ordering = ['order', 'title']
        verbose_name = 'Vision Topic'
        verbose_name_plural = 'Vision Topics'

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.title)
            slug = base
            n = 1
            while VisionTopic.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f'{base}-{n}'
                n += 1
            self.slug = slug
        super().save(*args, **kwargs)

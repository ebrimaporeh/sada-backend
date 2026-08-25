import uuid
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('users', '0018_backfill_is_deleted'),
    ]

    operations = [
        migrations.CreateModel(
            name='OrganizationType',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('slug', models.SlugField(max_length=40, unique=True)),
                ('name', models.CharField(max_length=100)),
                ('description', models.TextField(blank=True)),
                ('is_visible', models.BooleanField(default=True, help_text='Whether this type is selectable when creating a new organization.')),
            ],
            options={
                'verbose_name': 'Organization Type',
                'verbose_name_plural': 'Organization Types',
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='OrganizationRole',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(max_length=50)),
                ('permissions', models.JSONField(blank=True, default=list)),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='roles', to='users.organization')),
            ],
            options={
                'verbose_name': 'Organization Role',
                'verbose_name_plural': 'Organization Roles',
                'ordering': ['name'],
                'unique_together': {('organization', 'name')},
            },
        ),
        migrations.CreateModel(
            name='OrganizationMembership',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='memberships', to='users.organization')),
                ('role', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='memberships', to='organizations.organizationrole')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='organization_memberships', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Organization Membership',
                'verbose_name_plural': 'Organization Memberships',
                'ordering': ['-created_at'],
                'unique_together': {('user', 'organization')},
            },
        ),
        migrations.CreateModel(
            name='OrganizationInvitation',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('email', models.EmailField(max_length=254)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('accepted', 'Accepted'), ('rejected', 'Rejected')], default='pending', max_length=20)),
                ('responded_at', models.DateTimeField(blank=True, null=True)),
                ('invited_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='sent_organization_invitations', to=settings.AUTH_USER_MODEL)),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='invitations', to='users.organization')),
                ('role', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='invitations', to='organizations.organizationrole')),
            ],
            options={
                'verbose_name': 'Organization Invitation',
                'verbose_name_plural': 'Organization Invitations',
                'ordering': ['-created_at'],
            },
        ),
    ]

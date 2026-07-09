import requests
from django.core.management.base import BaseCommand
from django.core.files.base import ContentFile
from apps.campaigns.models import Category

CATEGORIES = [
    {
        'name': 'Agriculture & Food',
        'slug': 'agriculture-food',
        'description': 'Support farming initiatives, food security, and agricultural development projects',
        'image': 'https://images.unsplash.com/photo-1574943320219-553eb213f72d?w=500&h=500&fit=crop',
    },
    {
        'name': 'Business',
        'slug': 'business',
        'description': 'Funding for small businesses, entrepreneurship, and economic development',
        'image': 'https://images.unsplash.com/photo-1552664730-d307ca884978?w=500&h=500&fit=crop',
    },
    {
        'name': 'Charity',
        'slug': 'charity',
        'description': 'General charitable causes and community welfare initiatives',
        'image': 'https://images.unsplash.com/photo-1469571486292-0ba58fe66842?w=500&h=500&fit=crop',
    },
    {
        'name': 'Community Projects',
        'slug': 'community-projects',
        'description': 'Community development, infrastructure, and local improvement projects',
        'image': 'https://images.unsplash.com/photo-1552664730-d307ca884978?w=500&h=500&fit=crop',
    },
    {
        'name': 'Disaster Relief',
        'slug': 'disaster-relief',
        'description': 'Emergency aid and relief for natural disasters and crises',
        'image': 'https://images.unsplash.com/photo-1496148128662-aaa071300c2c?w=500&h=500&fit=crop',
    },
    {
        'name': 'Education',
        'slug': 'education',
        'description': 'School fees, scholarships, educational programs, and learning resources',
        'image': 'https://images.unsplash.com/photo-1427504494785-cddc1162f663?w=500&h=500&fit=crop',
    },
    {
        'name': 'Medical & Health',
        'slug': 'medical-health',
        'description': 'Healthcare, medical treatments, hospital bills, and health awareness',
        'image': 'https://images.unsplash.com/photo-1576091160550-2173dba999ef?w=500&h=500&fit=crop',
    },
    {
        'name': 'Memorial',
        'slug': 'memorial',
        'description': 'Tribute projects and memorials for loved ones',
        'image': 'https://images.unsplash.com/photo-1516567867245-ad8e0f01bd2c?w=500&h=500&fit=crop',
    },
    {
        'name': 'Other',
        'slug': 'other',
        'description': 'Other fundraising causes not covered by specific categories',
        'image': 'https://images.unsplash.com/photo-1531482615713-2afd69097998?w=500&h=500&fit=crop',
    },
    {
        'name': 'Religious',
        'slug': 'religious',
        'description': 'Religious institutions, faith-based projects, and spiritual initiatives',
        'image': 'https://images.unsplash.com/photo-1529156069898-49953e39b3ac?w=500&h=500&fit=crop',
    },
    {
        'name': 'Women & Girls',
        'slug': 'women-girls',
        'description': 'Empowerment and support programs for women and girls',
        'image': 'https://images.unsplash.com/photo-1552664730-d307ca884978?w=500&h=500&fit=crop',
    },
]


class Command(BaseCommand):
    help = 'Seed categories with proper names, descriptions, and images from Unsplash'

    def handle(self, *args, **options):
        self.stdout.write('Starting category seeding...\n')

        # First, clean up duplicate categories (keep only the ones we want)
        slugs_to_keep = {cat['slug'] for cat in CATEGORIES}

        # Delete categories with duplicate names that aren't in our seed list
        for cat_data in CATEGORIES:
            duplicate_categories = Category.objects.filter(
                name=cat_data['name']
            ).exclude(slug=cat_data['slug'])

            if duplicate_categories.exists():
                count = duplicate_categories.count()
                duplicate_categories.delete()
                self.stdout.write(
                    self.style.WARNING(f'✓ Cleaned up {count} duplicate(s) of "{cat_data["name"]}"')
                )

        # Now seed/update categories
        for cat_data in CATEGORIES:
            try:
                category, created = Category.objects.update_or_create(
                    slug=cat_data['slug'],
                    defaults={
                        'name': cat_data['name'],
                        'description': cat_data['description'],
                    }
                )

                # Download and save image if not already present
                if not category.image:
                    self.stdout.write(f'Downloading image for {category.name}...')
                    try:
                        response = requests.get(cat_data['image'], timeout=10)
                        if response.status_code == 200:
                            file_name = f'{cat_data["slug"]}.jpg'
                            category.image.save(
                                file_name,
                                ContentFile(response.content),
                                save=True
                            )
                            self.stdout.write(
                                self.style.SUCCESS(f'✓ Downloaded image for {category.name}')
                            )
                        else:
                            self.stdout.write(
                                self.style.WARNING(f'✗ Failed to download image for {category.name} (Status: {response.status_code})')
                            )
                    except Exception as e:
                        self.stdout.write(
                            self.style.WARNING(f'✗ Error downloading image for {category.name}: {str(e)}')
                        )

                if created:
                    self.stdout.write(
                        self.style.SUCCESS(f'✓ Created category: {category.name}')
                    )
                else:
                    self.stdout.write(
                        self.style.SUCCESS(f'✓ Updated category: {category.name}')
                    )

            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'✗ Error processing {cat_data["name"]}: {str(e)}')
                )

        self.stdout.write(self.style.SUCCESS('\n✓ Category seeding completed!'))

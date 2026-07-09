import os
import requests
from io import BytesIO
from django.core.management.base import BaseCommand
from django.core.files.base import ContentFile
from apps.campaigns.models import Category

CATEGORY_IMAGES = {
    'agriculture-food': 'https://images.unsplash.com/photo-1488459716781-6f3ee409e64d?w=400&h=400&fit=crop',
    'business': 'https://images.unsplash.com/photo-1552664730-d307ca884978?w=400&h=400&fit=crop',
    'charity': 'https://images.unsplash.com/photo-1559027615-cd007e8eead6?w=400&h=400&fit=crop',
    'community-projects': 'https://images.unsplash.com/photo-1552664730-d307ca884978?w=400&h=400&fit=crop',
    'disaster-relief': 'https://images.unsplash.com/photo-1496148128662-aaa071300c2c?w=400&h=400&fit=crop',
    'education': 'https://images.unsplash.com/photo-1427504494785-cddc1162f663?w=400&h=400&fit=crop',
    'medical-health': 'https://images.unsplash.com/photo-1576091160550-2173dba999ef?w=400&h=400&fit=crop',
    'memorial': 'https://images.unsplash.com/photo-1516567867245-ad8e0f01bd2c?w=400&h=400&fit=crop',
    'other': 'https://images.unsplash.com/photo-1531482615713-2afd69097998?w=400&h=400&fit=crop',
    'religious': 'https://images.unsplash.com/photo-1559027615-cd007e8eead6?w=400&h=400&fit=crop',
    'women-girls': 'https://images.unsplash.com/photo-1552664730-d307ca884978?w=400&h=400&fit=crop',
}


class Command(BaseCommand):
    help = 'Seed categories with images from Unsplash'

    def handle(self, *args, **options):
        for slug, image_url in CATEGORY_IMAGES.items():
            try:
                category = Category.objects.get(slug=slug)
                if not category.image:
                    self.stdout.write(f'Downloading image for {category.name}...')
                    response = requests.get(image_url, timeout=10)
                    if response.status_code == 200:
                        file_name = f'{slug}.jpg'
                        category.image.save(
                            file_name,
                            ContentFile(response.content),
                            save=True
                        )
                        self.stdout.write(
                            self.style.SUCCESS(f'✓ Updated {category.name} with image')
                        )
                    else:
                        self.stdout.write(
                            self.style.WARNING(f'✗ Failed to download image for {category.name}')
                        )
                else:
                    self.stdout.write(f'✓ {category.name} already has an image')
            except Category.DoesNotExist:
                self.stdout.write(
                    self.style.WARNING(f'✗ Category with slug "{slug}" not found')
                )
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'✗ Error updating {slug}: {str(e)}')
                )

        self.stdout.write(self.style.SUCCESS('Done!'))

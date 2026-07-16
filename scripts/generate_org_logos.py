"""Generates simple colored initials-badge logos locally for each seeded
organization — deliberately not pulled from the internet, since searching
for "university seal" / "government emblem" etc. kept surfacing real
institutions' actual trademarked logos and, in one case, a photo of real
sitting heads of state. A generated placeholder avoids that entirely."""
import os
from PIL import Image, ImageDraw, ImageFont

FONT_PATH = '/System/Library/Fonts/Supplemental/Arial Bold.ttf'
SIZE = 512
LOCAL_DIR = os.path.join(os.path.dirname(__file__), '..', 'media', 'profile_seed_images')
os.makedirs(LOCAL_DIR, exist_ok=True)

# email -> (initials, background color)
ORGS = {
    'bakau.mosque@example.gm': ('BM', (30, 90, 70)),
    'naatip@example.gm': ('NA', (120, 40, 40)),
    'serrekunda.cda@example.gm': ('SC', (40, 70, 130)),
    'utgsu@example.gm': ('SU', (150, 100, 20)),
    'whatsongambia@example.gm': ('WG', (100, 40, 120)),
}


def generate(email, initials, color):
    img = Image.new('RGB', (SIZE, SIZE), color)
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(FONT_PATH, 200)
    bbox = draw.textbbox((0, 0), initials, font=font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((SIZE - w) / 2 - bbox[0], (SIZE - h) / 2 - bbox[1]), initials, fill='white', font=font)
    path = os.path.join(LOCAL_DIR, f'{email.split("@")[0]}_logo.png')
    img.save(path)
    return path


if __name__ == '__main__':
    for email, (initials, color) in ORGS.items():
        path = generate(email, initials, color)
        print(f'{email} -> {path}')

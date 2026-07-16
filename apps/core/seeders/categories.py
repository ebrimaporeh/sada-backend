CATEGORIES_DATA = [
    dict(name='Medical & Health',    slug='medical',    icon='heart',     description='Medical bills, surgeries, and health emergencies.'),
    dict(name='Education',           slug='education',  icon='book',      description='School fees, scholarships, and educational needs.'),
    dict(name='Business',            slug='business',   icon='briefcase', description='Small business start-ups and livelihood support.'),
    dict(name='Religious',           slug='religious',  icon='moon',      description='Mosques, churches, and places of worship.'),
    dict(name='Community Projects',  slug='community',  icon='users',     description='Local community development and infrastructure.'),
    dict(name='Disaster Relief',     slug='disaster',   icon='alert',     description='Floods, fires, and urgent emergencies.'),
    dict(name='Youth & Sports',      slug='sports',     icon='zap',       description='Youth development, sports, and fitness.'),
    dict(name='Memorial',            slug='memorial',   icon='star',      description='Honouring loved ones and keeping legacies alive.'),
    dict(name='Charity',             slug='charity',    icon='gift',      description='General charitable causes and giving.'),
    dict(name='Agriculture & Food',  slug='agriculture',icon='leaf',      description='Farming, food security, and rural livelihoods.'),
    dict(name='Women & Girls',       slug='women',      icon='award',     description='Empowering women and girls across The Gambia.'),
    dict(name='Other',               slug='other',      icon='more',      description='Other causes not listed above.'),
]


def seed_categories(stdout) -> dict:
    """Creates CATEGORIES_DATA, returns {slug: Category} for downstream seeders."""
    from apps.campaigns.models import Category

    created = {}
    for data in CATEGORIES_DATA:
        obj, made = Category.objects.get_or_create(slug=data['slug'], defaults=data)
        if made:
            stdout.write(f'  + {obj.name}')
        created[obj.slug] = obj
    return created

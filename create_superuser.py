import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from accounts.models import CustomUserModel

if not CustomUserModel.objects.filter(username='admin').exists():
    CustomUserModel.objects.create_superuser(
        username='admin',
        email='admin@example.com',
        password='admin@123'
    )
    print('Superuser created successfully')
else:
    print('Superuser already exists')
from django.urls import path
from . import views

app_name = 'social_accounts'

urlpatterns = [
    path('connect-mock/', views.connect_mock_social, name='connect_mock'),
]
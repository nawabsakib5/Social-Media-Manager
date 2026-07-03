from django.urls import path
from . import views

app_name = 'social_accounts'

urlpatterns = [
    path('connect-mock/', views.connect_mock_social, name='connect_mock'),
    path('login/', views.facebook_login, name='facebook_login'),
    path('callback/', views.facebook_callback, name='facebook_callback'),
]
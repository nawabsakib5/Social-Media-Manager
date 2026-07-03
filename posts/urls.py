from django.urls import path
from . import views
from social_accounts import views as social_views  # Imported social views

urlpatterns = [
    path('', views.post_list, name='post_list'),
    path('new/', views.post_create, name='post_create'),
    path('accounts/', social_views.account_list, name='account_list'),
    
    path('accounts/connect/', social_views.facebook_login, name='account_create'),
]
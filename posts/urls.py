from django.urls import path, include
from . import views

urlpatterns = [
    path('dashboard/', views.dashboard, name='dashboard'),
    path('', views.post_list, name='post_list'),
    path('new/', views.post_create, name='post_create'),
    path('<int:post_id>/', views.post_detail, name='post_detail'),
    path('<int:post_id>/edit/', views.post_edit, name='post_edit'),
    path('<int:post_id>/delete/', views.post_delete, name='post_delete'),
    path('<int:post_id>/publish-now/', views.post_publish_now, name='post_publish_now'),
    path('<int:post_id>/platform/<int:ps_id>/delete/', views.platform_delete, name='platform_delete'),
    path('<int:post_id>/platform/<int:ps_id>/edit/', views.platform_edit, name='platform_edit'),
    path('accounts/', include('social_accounts.urls')),
]
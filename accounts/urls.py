from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    path('users/', views.user_list, name='user_list'),
    path('users/invite/', views.invite_member, name='invite_member'),
    path('users/remove/<int:user_id>/', views.remove_user, name='remove_user'),
    path('change-password/', views.change_password, name='change_password'),
    path('logout/', views.logoutpage, name='logout'), 
    path('users/invite/accept/<str:token>/', views.accept_invitation, name='accept_invitation'),
    path('users/<int:user_id>/', views.user_detail, name='user_detail'),
    path('connect/', views.connect_social_account, name='connect_social_account'),
    path('users/<int:user_id>/change-password/', views.admin_change_password, name='admin_change_password'),
    path('users/<int:user_id>/toggle-status/', views.toggle_user_status, name='toggle_user_status'),
    path('users/<int:user_id>/change-role/', views.change_user_role, name='change_user_role'),
]
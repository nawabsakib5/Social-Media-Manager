from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    path('users/',                    views.user_list,    name='user_list'),
    path('users/invite/',             views.invite_member, name='invite_member'),
    path('users/remove/<int:user_id>/', views.remove_user, name='remove_user'),
]
from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    path('invite/', views.invite_team_member, name='invite_member'),
]
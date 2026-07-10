from django.urls import path
from . import views

app_name = 'social_accounts'

urlpatterns = [
    path('',                      views.account_list,      name='account_list'),
    path('login/',                views.facebook_login,    name='facebook_login'),
    path('callback/',             views.facebook_callback, name='facebook_callback'),
    path('<str:platform>/',       views.workspace,         name='workspace'),
]
from django.urls import path
from . import views

app_name = 'social_accounts'

urlpatterns = [
    path('',                                views.account_list,         name='account_list'),
    path('login/',                          views.facebook_login,       name='facebook_login'),
    path('callback/',                       views.facebook_callback,    name='facebook_callback'),
    path('reply/messenger/',               views.send_messenger_reply, name='messenger_reply'),
    path('reply/<str:platform>/<str:comment_id>/', views.post_comment_reply, name='comment_reply'),
    path('<str:platform>/',                 views.workspace,            name='workspace'),
]
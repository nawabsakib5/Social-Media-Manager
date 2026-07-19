
from django.urls import path
from . import views

app_name = 'social_accounts'

urlpatterns = [
    path('', views.account_list, name='account_list'),
    path('workspace/', views.workspace, name='workspace'),
    path('workspace/<int:account_id>/', views.workspace, name='workspace'),
    path('facebook/login/', views.facebook_login, name='facebook_login'),
    path('callback/', views.facebook_callback, name='facebook_callback'),
    path('reply/<str:platform>/<str:comment_id>/', views.post_comment_reply, name='post_comment_reply'),
    path('messenger/reply/', views.send_messenger_reply, name='send_messenger_reply'),
    path('disconnect/<int:account_id>/', views.disconnect_account, name='disconnect_account'),
    path('twitter/login/', views.twitter_login, name='twitter_login'),
    path('twitter/callback/', views.twitter_callback, name='twitter_callback'),
]
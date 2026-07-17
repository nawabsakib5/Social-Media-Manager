# inbox/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('', views.inbox_list, name='inbox_list'),
    path('sync/', views.sync_inbox_data, name='sync_inbox'),
    path('<int:item_id>/reply/', views.send_inbox_reply, name='send_inbox_reply'),
    path('<int:item_id>/mark-read/', views.mark_read_ajax, name='mark_read_ajax'),
]
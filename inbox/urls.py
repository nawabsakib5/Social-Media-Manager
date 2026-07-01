from django.urls import path
from . import views

urlpatterns = [
    path('', views.inbox_list, name='inbox_list'),
    path('<int:item_id>/reply/', views.inbox_reply, name='inbox_reply'),
]
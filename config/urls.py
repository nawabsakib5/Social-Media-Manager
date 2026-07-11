from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView
from accounts import views as account_views

urlpatterns = [
    path('', RedirectView.as_view(url='/posts/', permanent=False)), 
    path('admin/', admin.site.urls),
    path('posts/', include('posts.urls')),
    path('inbox/', include('inbox.urls')),
    path('social/', include('social_accounts.urls')),
    path('accounts/', include('accounts.urls')),
    path('login/',  account_views.Login,      name='login'),
    path('logout/', account_views.logoutpage, name='logout'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
from django import forms
from .models import SocialAccount

class SocialAccountForm(forms.ModelForm):
    class Meta:
        model = SocialAccount
        fields = ['platform', 'account_name', 'status']
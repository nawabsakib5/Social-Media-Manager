from django import forms
from .models import Post
from social_accounts.models import SocialAccount

class PostForm(forms.ModelForm):
    class Meta:
        model = Post
        fields = ['social_account', 'content', 'media_file', 'scheduled_time', 'status']
        widgets = {
            'scheduled_time': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }

    def __init__(self, *args, **kwargs):
        team = kwargs.pop('team', None)
        super().__init__(*args, **kwargs)
        
        self.fields['social_account'].queryset = SocialAccount.objects.filter(
            status='connected'
        )
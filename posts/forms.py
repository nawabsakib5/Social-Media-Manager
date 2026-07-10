from django import forms
from .models import Post
from social_accounts.models import SocialAccount


class PostForm(forms.ModelForm):
    social_accounts = forms.ModelMultipleChoiceField(
        queryset=SocialAccount.objects.filter(status='connected'),
        widget=forms.CheckboxSelectMultiple,
        required=True,
        label='Select Platforms'
    )

    class Meta:
        model = Post
        fields = ['social_accounts', 'content', 'media_file', 'scheduled_time']
        widgets = {
            'scheduled_time': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }
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

    def __init__(self, *args, **kwargs):
        team = kwargs.pop('team', None)
        super().__init__(*args, **kwargs)
        if team:
            self.fields['social_accounts'].queryset = SocialAccount.objects.filter(
                status='connected',
                team=team
            )
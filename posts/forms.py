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
        
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        self.fields['content'].required = False 
        self.fields['content'].label = 'Content'
        
        
        if user:
            if user.is_superuser or getattr(user, 'user_type', None) == 'admin':
                
                self.fields['social_accounts'].queryset = SocialAccount.objects.filter(status='connected')
            else:
                
                self.fields['social_accounts'].queryset = SocialAccount.objects.filter(
                    status='connected',
                    permitted_users=user
                )
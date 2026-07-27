from django import forms
from .models import Post
from social_accounts.models import SocialAccount


class PostForm(forms.ModelForm):
    POST_TYPE_CHOICES = [
        ('instant', 'Publish Now'),
        ('scheduled', 'Schedule for Later'),
    ]

    post_type = forms.ChoiceField(
        choices=POST_TYPE_CHOICES,
        initial='instant',
        required=True,
        label='Post Type',
        widget=forms.RadioSelect
    )

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
            'scheduled_time': forms.DateTimeInput(
                attrs={'type': 'datetime-local'},
                format='%Y-%m-%dT%H:%M'
            ),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        self.fields['content'].required = False
        self.fields['content'].label = 'Content'
        self.fields['scheduled_time'].required = False

        if user:
            if user.is_superuser or getattr(user, 'user_type', None) == 'admin':
                self.fields['social_accounts'].queryset = SocialAccount.objects.filter(
                    status='connected'
                )
            else:
                self.fields['social_accounts'].queryset = SocialAccount.objects.filter(
                    status='connected',
                    permitted_users=user
                )

    def clean(self):
        cleaned_data = super().clean()
        post_type = cleaned_data.get('post_type')
        scheduled_time = cleaned_data.get('scheduled_time')

        # Schedule নির্বাচন করলে scheduled_time অবশ্যই দিতে হবে
        if post_type == 'scheduled' and not scheduled_time:
            self.add_error('scheduled_time', 'Please select a date and time for scheduling.')

        return cleaned_data
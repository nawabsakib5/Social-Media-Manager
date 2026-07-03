from django import forms

class TeamInviteForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter team member\'s Gmail address'
        }),
        label="Gmail Address"
    )
    role = forms.ChoiceField(
        choices=[('editor', 'Editor'), ('viewer', 'Viewer')],
        widget=forms.Select(attrs={'class': 'form-control'}),
        initial='editor',
        label="Assigned Role"
    )
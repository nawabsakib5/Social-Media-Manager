from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.utils.crypto import get_random_string
from django.core.mail import send_mail
from django.conf import settings
from .models import TeamMember, Team
from .forms import TeamInviteForm

@login_required
def invite_team_member(request):
    # 1. Retrieve the logged-in user's active team membership
    membership = request.user.teammemberships.first()
    if not membership or membership.role != 'admin':
        messages.error(request, "Access Denied: Only the team Admin can invite new members.")
        return redirect('post_list')
    
    active_team = membership.team

    if request.method == 'POST':
        form = TeamInviteForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            role = form.cleaned_data['role']

            # 2. Check if the User already exists in our database
            user_exists = User.objects.filter(email=email).exists()
            
            if user_exists:
                invited_user = User.objects.get(email=email)
                # Check if they are already in the same team
                if TeamMember.objects.filter(user=invited_user, team=active_team).exists():
                    messages.warning(request, f"'{email}' is already a member of this team.")
                    return redirect('accounts:invite_member')
                
                # Link existing user to this team
                TeamMember.objects.create(
                    user=invited_user,
                    team=active_team,
                    role=role
                )
                
                # Send simple notification email to the existing user
                subject = f"You've been added to {active_team.name}"
                message = f"Hello,\n\nYou have been added to the team '{active_team.name}' as a {role.upper()}.\nYou can now log in to view your dashboard."
                send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [email])
                
                messages.success(request, f"Successfully linked existing user {email} to your team!")
            else:
                # 3. Generate a secure random password for the new user
                auto_password = get_random_string(length=12)

                # 4. Create the new Django User (Gmail as username & email)
                invited_user = User.objects.create_user(
                    username=email,
                    email=email,
                    password=auto_password
                )

                # 5. Bind the new user to the Admin's active team
                TeamMember.objects.create(
                    user=invited_user,
                    team=active_team,
                    role=role
                )

                # 6. Compose and send the welcome email with auto-generated credentials
                subject = f"Welcome to {active_team.name} - SaaS Invitation"
                message = (
                    f"Hello,\n\n"
                    f"You have been invited to join the team '{active_team.name}' on SaaS Manager as an '{role.upper()}'.\n\n"
                    f"Here are your login credentials:\n"
                    f"Login URL: http://localhost:8000/login/\n"
                    f"Username (Gmail): {email}\n"
                    f"Temporary Password: {auto_password}\n\n"
                    f"For security, please log in and change your password immediately.\n\n"
                    f"Best regards,\n"
                    f"The {active_team.name} Team"
                )
                
                try:
                    send_mail(
                        subject,
                        message,
                        settings.DEFAULT_FROM_EMAIL,
                        [email],
                        fail_silently=False,
                    )
                    messages.success(request, f"Success: Invited {email}. Login credentials have been sent via email!")
                except Exception as e:
                    messages.warning(request, f"User created, but email failed to send. Generated Password is: {auto_password}. Error: {str(e)}")
            
            return redirect('post_list')
    else:
        form = TeamInviteForm()

    return render(request, 'accounts/invite_member.html', {
        'form': form, 
        'active_team': active_team
    })
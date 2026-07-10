from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.contrib import messages
from django.utils.crypto import get_random_string
from django.core.mail import send_mail
from django.conf import settings

MAX_USERS = 50


def is_admin(user):
    return user.is_superuser or user.is_staff


@login_required
@user_passes_test(is_admin, login_url='post_list')
def user_list(request):
    users = User.objects.all().order_by('date_joined')
    return render(request, 'accounts/user_list.html', {
        'users': users,
        'max_users': MAX_USERS,
    })


@login_required
@user_passes_test(is_admin, login_url='post_list')
def invite_member(request):
    if User.objects.count() >= MAX_USERS:
        messages.error(request, f"Maximum user limit ({MAX_USERS}) reached.")
        return redirect('accounts:user_list')

    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        if not email:
            messages.error(request, "Email is required.")
            return redirect('accounts:invite_member')

        if User.objects.filter(email=email).exists():
            messages.warning(request, f"{email} already exists.")
            return redirect('accounts:invite_member')

        auto_password = get_random_string(length=12)
        user = User.objects.create_user(
            username=email,
            email=email,
            password=auto_password
        )

        try:
            send_mail(
                subject="Your SocialManager Invitation",
                message=(
                    f"Hello,\n\n"
                    f"You have been invited to SocialManager.\n\n"
                    f"Login URL: {settings.SITE_URL}/login/\n"
                    f"Username: {email}\n"
                    f"Password: {auto_password}\n\n"
                    f"Please change your password after logging in."
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[email],
                fail_silently=False,
            )
            messages.success(request, f"Invitation sent to {email}.")
        except Exception as e:
            messages.warning(request, f"User created. Email failed. Password: {auto_password}")

        return redirect('accounts:user_list')

    return render(request, 'accounts/invite_member.html')


@login_required
@user_passes_test(is_admin, login_url='post_list')
def remove_user(request, user_id):
    if request.method == 'POST':
        try:
            user = User.objects.get(id=user_id)
            if user == request.user:
                messages.error(request, "You cannot remove yourself.")
            else:
                user.delete()
                messages.success(request, f"User removed.")
        except User.DoesNotExist:
            messages.error(request, "User not found.")
    return redirect('accounts:user_list')
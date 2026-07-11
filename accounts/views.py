from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth import login, logout, authenticate, update_session_auth_hash, get_user_model
from django.contrib import messages
from django.utils.crypto import get_random_string
from django.core.mail import send_mail
from django.conf import settings

User = get_user_model()
MAX_USERS = 50


def is_admin(user):
    return user.is_superuser or user.is_staff or getattr(user, 'user_type', None) == 'admin'


# ── Auth ──

def Login(request):
    if request.user.is_authenticated:
        return redirect('/posts/')
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            return redirect('/posts/')
        messages.error(request, "Invalid username or password.")
    return render(request, 'registration/login.html')


def logoutpage(request):
    logout(request)
    return redirect('/login/')


@login_required
def change_password(request):
    if request.method == 'POST':
        old_pass = request.POST.get('old_pass')
        new_pass = request.POST.get('new_pass')
        con_pass = request.POST.get('con_pass')
        if request.user.check_password(old_pass):
            if con_pass == new_pass:
                request.user.set_password(new_pass)
                request.user.save()
                update_session_auth_hash(request, request.user)
                messages.success(request, "Password changed successfully.")
                return redirect('/posts/')
            messages.error(request, "Passwords do not match.")
        else:
            messages.error(request, "Incorrect old password.")
    return render(request, 'accounts/change_password.html')


# ── Admin ──

@login_required
@user_passes_test(is_admin, login_url='/posts/')
def user_list(request):
    users = User.objects.all().order_by('date_joined')
    return render(request, 'accounts/user_list.html', {
        'users': users,
        'max_users': MAX_USERS,
    })


@login_required
@user_passes_test(is_admin, login_url='/posts/')
def invite_member(request):
    if User.objects.count() >= MAX_USERS:
        messages.error(request, f"Maximum user limit ({MAX_USERS}) reached.")
        return redirect('accounts:user_list')

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        email    = request.POST.get('email', '').strip()

        if not email:
            messages.error(request, "Email is required.")
            return redirect('accounts:invite_member')

        if User.objects.filter(email=email).exists():
            messages.warning(request, f"{email} already exists.")
            return redirect('accounts:invite_member')

        auto_password = get_random_string(length=12)
        User.objects.create_user(
            username=username or email,
            email=email,
            password=auto_password,
            user_type='user',
        )

        try:
            send_mail(
                subject="Your SocialManager Invitation",
                message=(
                    f"Hello,\n\n"
                    f"You have been invited to SocialManager.\n\n"
                    f"Login URL: {settings.SITE_URL}/login/\n"
                    f"Username: {username or email}\n"
                    f"Password: {auto_password}\n\n"
                    f"Please change your password after logging in."
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[email],
                fail_silently=False,
            )
            messages.success(request, f"Invitation sent to {email}.")
        except Exception:
            messages.warning(request, f"User created. Email failed. Password: {auto_password}")

        return redirect('accounts:user_list')

    return render(request, 'accounts/invite_member.html')


@login_required
@user_passes_test(is_admin, login_url='/posts/')
def remove_user(request, user_id):
    if request.method == 'POST':
        try:
            user = User.objects.get(id=user_id)
            if user == request.user:
                messages.error(request, "You cannot remove yourself.")
            else:
                user.delete()
                messages.success(request, "User removed.")
        except User.DoesNotExist:
            messages.error(request, "User not found.")
    return redirect('accounts:user_list')
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate, update_session_auth_hash, get_user_model
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib import messages
from django.utils.crypto import get_random_string
from django.core.mail import send_mail
from django.conf import settings
from .models import Invitation  
from social_accounts.models import SocialAccount  

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
        
        permitted_ids = request.POST.getlist('permitted_accounts')

        if not email:
            messages.error(request, "Email is required.")
            return redirect('accounts:invite_member')

        if User.objects.filter(email=email).exists():
            messages.warning(request, f"User with email {email} already exists.")
            return redirect('accounts:invite_member')

        if Invitation.objects.filter(email=email, is_accepted=False).exists():
            messages.warning(request, f"An active invitation has already been sent to {email}.")
            return redirect('accounts:user_list')

        token = get_random_string(length=32)
        
        Invitation.objects.create(
            email=email,
            token=token,
            user_type='user',
            permitted_accounts=[int(pid) for pid in permitted_ids]  
        )

        accept_url = f"{settings.SITE_URL}/accounts/users/invite/accept/{token}/"

        try:
            send_mail(
                subject="Invitation to join SocialManager Workspace",
                message=(
                    f"Hello,\n\n"
                    f"You have been invited to join the SocialManager Workspace.\n\n"
                    f"To accept this invitation and set up your secure account password, please click the link below:\n"
                    f"👉 {accept_url}\n\n"
                    f"This is a one-time secure link. Once you set your password, you will be logged in automatically."
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[email],
                fail_silently=False,
            )
            messages.success(request, f"Invitation link successfully sent to {email}.")
        except Exception as e:
            print(f"\n[TESTING LINK] Email failed to send. Paste this in browser to accept:\n{accept_url}\n")
            messages.warning(request, f"Invitation saved. Mail failed. Test Link printed in terminal console.")

        return redirect('accounts:user_list')

    connected_accounts = SocialAccount.objects.filter(status='connected')
    return render(request, 'accounts/invite_member.html', {
        'connected_accounts': connected_accounts
    })


def accept_invitation(request, token):
    invitation = get_object_or_404(Invitation, token=token, is_accepted=False)
    
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        full_name = request.POST.get('full_name', '').strip()
        password = request.POST.get('password', '').strip()
        phone = request.POST.get('phone', '').strip()
        
        if not username or not password or not full_name:
            messages.error(request, "Username, Full Name and Password are required.")
            return render(request, 'accounts/accept_invitation.html', {'email': invitation.email})
            
        if User.objects.filter(username=username).exists():
            messages.error(request, "Username is already taken. Please choose another.")
            return render(request, 'accounts/accept_invitation.html', {'email': invitation.email})
            
        user = User.objects.create_user(
            username=username,
            email=invitation.email,
            password=password,
            full_name=full_name,
            phone=phone,
            user_type=invitation.user_type
        )
        
        permitted_ids = invitation.permitted_accounts
        if permitted_ids:
            permitted_social_accounts = SocialAccount.objects.filter(id__in=permitted_ids)
            for sa in permitted_social_accounts:
                sa.permitted_users.add(user) 
        
        invitation.is_accepted = True
        invitation.save()
        
        login(request, user)
        messages.success(request, f"Welcome to SocialManager, {user.full_name}! Your account is active.")
        return redirect('/posts/')
        
    return render(request, 'accounts/accept_invitation.html', {'email': invitation.email})


@login_required
@user_passes_test(is_admin, login_url='/posts/')
def remove_user(request, user_id):
    try:
        user = User.objects.get(id=user_id)
        if user == request.user:
            messages.error(request, "You cannot remove yourself.")
        else:
            user.delete()
            messages.success(request, "User removed successfully.")
    except User.DoesNotExist:
        messages.error(request, "User not found.")
        
    return redirect('accounts:user_list')



@login_required
@user_passes_test(is_admin, login_url='/posts/')
def user_detail(request, user_id):
    
    user_obj = get_object_or_404(User, id=user_id)
    all_accounts = SocialAccount.objects.filter(status='connected')
    
    
    if request.method == 'POST' and is_admin(request.user):
        permitted_ids = request.POST.getlist('permitted_accounts')
        
        
        for sa in all_accounts:
            if str(sa.id) in permitted_ids:
                sa.permitted_users.add(user_obj)
            else:
                sa.permitted_users.remove(user_obj)
                
        messages.success(request, f"Permissions successfully updated for {user_obj.full_name or user_obj.username}.")
        return redirect('accounts:user_detail', user_id=user_obj.id)
        
    
    
    user_permitted_ids = SocialAccount.objects.filter(permitted_users=user_obj).values_list('id', flat=True)
    
    
    from posts.models import Post
    user_posts = Post.objects.filter(created_by=user_obj).order_by('-created_at')[:10]
    
    context = {
        'user_obj': user_obj,
        'all_accounts': all_accounts,
        'user_permitted_ids': list(user_permitted_ids),
        'user_posts': user_posts,
    }
    return render(request, 'accounts/user_detail.html', context)
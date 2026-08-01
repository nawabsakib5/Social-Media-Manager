import os
import requests
import cloudinary.uploader
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth import get_user_model 
from django.contrib import messages
from django.utils import timezone
from django.db.models import Count, Q

from .models import Post, PostPlatformStatus
from .forms import PostForm
from .tasks import publish_post_task
from social_accounts.models import SocialAccount
from inbox.models import InboxItem

User = get_user_model() 
MAX_USERS = 50


def is_admin(user):
    return user.is_superuser or user.is_staff or getattr(user, 'user_type', None) == 'admin'


@login_required
def dashboard(request):
    if request.user.is_superuser or getattr(request.user, 'user_type', None) == 'admin':
        accounts = SocialAccount.objects.filter(status='connected')
        posts_query = Post.objects.all()
    else:
        accounts = SocialAccount.objects.filter(permitted_users=request.user, status='connected')
        posts_query = Post.objects.filter(created_by=request.user)

    total_posts = posts_query.count()
    published_posts = posts_query.filter(status='published').count()
    scheduled_posts = posts_query.filter(status='scheduled').count()
    failed_posts = posts_query.filter(status='failed').count()
    total_users_count = User.objects.count()

    channels_data = []
    for acc in accounts:
        post_count = PostPlatformStatus.objects.filter(social_account=acc, status='published').count()
        channels_data.append({
            'account': acc,
            'post_count': post_count,
            'percentage': min(int((post_count / 50) * 100), 100) if post_count > 0 else 0
        })

    recent_posts = posts_query.order_by('-created_at')[:5]

    unread_inbox = 0
    try:
        unread_inbox = InboxItem.objects.filter(social_account__in=accounts, is_read=False).count()
    except Exception:
        pass

    context = {
        'total_posts': total_posts,
        'published_posts': published_posts,
        'scheduled_posts': scheduled_posts,
        'failed_posts': failed_posts,
        'total_users': total_users_count,
        'channels_data': channels_data,
        'recent_posts': recent_posts,
        'unread_inbox': unread_inbox,
        'connected_accounts': accounts,
    }
    return render(request, 'posts/dashboard.html', context)


def _delete_from_platform(platform_status):
    platform = platform_status.social_account.platform
    post_id = platform_status.platform_post_id
    token = platform_status.social_account.access_token

    if not post_id or platform_status.status != 'published':
        return True, "Not published — skipping"

    try:
        if platform == 'facebook':
            res = requests.delete(
                f"https://graph.facebook.com/v22.0/{post_id}",
                params={'access_token': token},
                timeout=15
            ).json()
            if res.get('success') or res.get('id'):
                return True, "Deleted from Facebook ✓"
            error = res.get('error', {}).get('message', 'Unknown error')
            return False, f"Facebook delete failed: {error}"
        elif platform == 'instagram':
            return True, "Instagram: please delete manually from the app"
        return True, f"{platform}: deletion not supported"
    except requests.RequestException as e:
        return False, f"Network error: {e}"


def _update_on_platform(platform_status, new_content):
    platform = platform_status.social_account.platform
    post_id = platform_status.platform_post_id
    token = platform_status.social_account.access_token

    if not post_id or platform_status.status != 'published':
        return True, "Not published — skipping"

    try:
        if platform == 'facebook':
            res = requests.post(
                f"https://graph.facebook.com/v22.0/{post_id}",
                data={'message': new_content, 'access_token': token},
                timeout=15
            ).json()
            if res.get('success') or res.get('id'):
                return True, "Updated on Facebook ✓"
            error = res.get('error', {}).get('message', 'Unknown error')
            return False, f"Facebook update failed: {error}"
        elif platform == 'instagram':
            return False, "Instagram caption edit requires manual update"
        return True, f"{platform}: editing not supported"
    except requests.RequestException as e:
        return False, f"Network error: {e}"


@login_required
def post_list(request):
    posts = (
        Post.objects.all()
        .prefetch_related('platform_statuses__social_account', 'social_accounts')
        .order_by('-created_at')
    )
    return render(request, 'posts/post_list.html', {'posts': posts})


@login_required
def post_create(request):
    if request.method == 'POST':
        form = PostForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            post = form.save(commit=False)
            post.created_by = request.user

            post_type = request.POST.get('post_type', 'instant')
            if post_type == 'scheduled':
                post.status = 'scheduled'
            else:
                post.scheduled_time = timezone.now()
                post.status = 'processing'

            post.save()

            uploaded_files = request.FILES.getlist('media_files')
            video_extensions = ['.mp4', '.mov', '.avi', '.mkv', '.webm']

            for i, uploaded_file in enumerate(uploaded_files):
                if uploaded_file.size == 0:
                    continue
                filename = uploaded_file.name.lower()
                is_video = any(filename.endswith(ext) for ext in video_extensions)
                resource_type = 'video' if is_video else 'image'

                try:
                    upload_res = cloudinary.uploader.upload(
                        uploaded_file,
                        folder='post_media/',
                        resource_type=resource_type
                    )
                    secure_url = upload_res.get('secure_url')
                    if secure_url:
                        from .models import PostMedia
                        PostMedia.objects.create(
                            post=post,
                            url=secure_url,
                            media_type='video' if is_video else 'image',
                            order=i
                        )
                except Exception as e:
                    print(f"[Cloudinary Upload Error]: {e}")

            selected_accounts = form.cleaned_data['social_accounts']
            if not selected_accounts:
                messages.warning(request, "No platform selected.")
                return redirect('post_create')

            initial_status = 'processing' if post_type == 'instant' else 'scheduled'
            for account in selected_accounts:
                PostPlatformStatus.objects.create(
                    post=post,
                    social_account=account,
                    status=initial_status
                )

            if post_type == 'instant':
                for account in selected_accounts:
                    publish_post_task.delay(post.id, account.id)
                messages.success(request, f"Publishing to {len(selected_accounts)} platform(s)...")
            else:
                messages.success(request, f"Post scheduled for {post.scheduled_time}.")

            return redirect('post_list')
    else:
        form = PostForm(user=request.user)

    return render(request, 'posts/post_form.html', {'form': form})


@login_required
def post_detail(request, post_id):
    post = get_object_or_404(
        Post.objects.prefetch_related('platform_statuses__social_account', 'social_accounts'),
        id=post_id
    )
    return render(request, 'posts/post_detail.html', {'post': post})


@login_required
def post_edit(request, post_id):
    post = get_object_or_404(Post, id=post_id)

    if request.method == 'POST':
        form = PostForm(request.POST, request.FILES, instance=post, user=request.user)
        if form.is_valid():
            new_content = form.cleaned_data.get('content', '')

            platform_results = []
            for ps in post.platform_statuses.filter(status='published'):
                success, msg = _update_on_platform(ps, new_content)
                platform_results.append(msg)

            post = form.save(commit=False)
            post.save()
            form.save_m2m()

            post.platform_statuses.all().delete()
            for account in form.cleaned_data['social_accounts']:
                PostPlatformStatus.objects.create(
                    post=post,
                    social_account=account,
                    status='scheduled'
                )

            if platform_results:
                messages.info(request, " | ".join(platform_results))
            messages.success(request, "Post updated successfully.")
            return redirect('post_detail', post_id=post.id)
    else:
        form = PostForm(instance=post, user=request.user)

    return render(request, 'posts/post_form.html', {
        'form': form,
        'post': post,
        'editing': True
    })


@login_required
def post_delete(request, post_id):
    post = get_object_or_404(Post, id=post_id)
    if request.method == 'POST':
        results = []
        for ps in post.platform_statuses.all():
            success, msg = _delete_from_platform(ps)
            results.append(msg)

        post.delete()

        if results:
            messages.info(request, " | ".join(results))
        messages.success(request, "Post deleted from SocialManager.")
        return redirect('post_list')
    return redirect('post_detail', post_id=post_id)


@login_required
def post_publish_now(request, post_id):
    post = get_object_or_404(Post, id=post_id)
    if request.method == 'POST':
        accounts = post.social_accounts.all()
        if not accounts:
            messages.error(request, "No platforms selected for this post.")
            return redirect('post_detail', post_id=post_id)

        post.scheduled_time = timezone.now()
        post.status = 'published'
        post.save(update_fields=['scheduled_time', 'status'])

        for account in accounts:
            PostPlatformStatus.objects.filter(
                post=post, social_account=account
            ).update(status='published')
            publish_post_task.delay(post.id, account.id)

        messages.success(request, f"Publishing to {accounts.count()} platform(s) now.")
    return redirect('post_detail', post_id=post_id)


@login_required
def platform_delete(request, post_id, ps_id):
    """একটি নির্দিষ্ট platform থেকে post delete করা"""
    if request.method != 'POST':
        return redirect('post_detail', post_id=post_id)

    post = get_object_or_404(Post, id=post_id)
    ps = get_object_or_404(PostPlatformStatus, id=ps_id, post=post)
    account_name = ps.social_account.account_name

    if ps.status != 'published' or not ps.platform_post_id:
        messages.warning(request, f"{account_name}: Not published, nothing to delete.")
        return redirect('post_detail', post_id=post_id)

    try:
        from integrations import get_social_adapter
        adapter = get_social_adapter(ps.social_account)
        success, result = adapter.delete_post(post, ps)

        if success:
            ps.status = 'failed'
            ps.error_message = 'Deleted from platform'
            ps.platform_post_id = None
            ps.save()
            messages.success(request, f"✓ Deleted from {account_name}.")
        else:
            messages.error(request, f"Failed to delete from {account_name}: {result}")

    except Exception as e:
        messages.error(request, f"Error: {str(e)}")

    return redirect('post_detail', post_id=post_id)


@login_required
def platform_edit(request, post_id, ps_id):
    
    if request.method != 'POST':
        return redirect('post_detail', post_id=post_id)

    post = get_object_or_404(Post, id=post_id)
    ps = get_object_or_404(PostPlatformStatus, id=ps_id, post=post)
    new_content = request.POST.get('new_content', '').strip()
    account_name = ps.social_account.account_name

    if ps.status != 'published' or not ps.platform_post_id:
        messages.warning(request, f"{account_name}: Post not published yet.")
        return redirect('post_detail', post_id=post_id)

    try:
        from integrations import get_social_adapter
        adapter = get_social_adapter(ps.social_account)
        success, result = adapter.update_post(post, ps, new_content)

        if success:
            post.content = new_content
            post.save(update_fields=['content'])
            messages.success(request, f"✓ Caption updated on {account_name}.")
        else:
            messages.error(request, f"Failed to update {account_name}: {result}")

    except Exception as e:
        messages.error(request, f"Error: {str(e)}")

    return redirect('post_detail', post_id=post_id)
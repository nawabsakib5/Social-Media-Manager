from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from .models import Post, PostPlatformStatus
from .forms import PostForm
from .tasks import publish_post_task
import requests


def _delete_from_platform(platform_status):
    """Delete a post from its social media platform."""
    platform = platform_status.social_account.platform
    post_id = platform_status.platform_post_id
    token = platform_status.social_account.access_token

    if not post_id or platform_status.status != 'published':
        return True, "Not published — skipping"

    try:
        if platform == 'facebook':
            res = requests.delete(
                f"https://graph.facebook.com/v21.0/{post_id}",
                params={'access_token': token},
                timeout=15
            ).json()
            if res.get('success'):
                return True, "Deleted from Facebook ✓"
            error = res.get('error', {}).get('message', 'Unknown error')
            return False, f"Facebook delete failed: {error}"

        elif platform == 'instagram':
            # Instagram API does not support post deletion
            return True, "Instagram: please delete manually from the app"

        return True, f"{platform}: deletion not supported"

    except requests.RequestException as e:
        return False, f"Network error: {e}"


def _update_on_platform(platform_status, new_content):
    """Update post caption on its social media platform."""
    platform = platform_status.social_account.platform
    post_id = platform_status.platform_post_id
    token = platform_status.social_account.access_token

    if not post_id or platform_status.status != 'published':
        return True, "Not published — skipping"

    try:
        if platform == 'facebook':
            res = requests.post(
                f"https://graph.facebook.com/v21.0/{post_id}",
                data={'message': new_content, 'access_token': token},
                timeout=15
            ).json()
            if res.get('success'):
                return True, "Updated on Facebook ✓"
            error = res.get('error', {}).get('message', 'Unknown error')
            return False, f"Facebook update failed: {error}"

        elif platform == 'instagram':
            # Instagram API does not support caption editing
            return False, "Instagram caption edit requires manual update — open Instagram app"

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
        form = PostForm(request.POST, request.FILES)
        if form.is_valid():
            post = form.save(commit=False)
            post.created_by = request.user
            post.save()

            selected_accounts = form.cleaned_data['social_accounts']
            if not selected_accounts:
                messages.warning(request, "No platform selected.")
                return redirect('post_create')

            for account in selected_accounts:
                PostPlatformStatus.objects.get_or_create(
                    post=post,
                    social_account=account,
                    defaults={'status': 'scheduled'}
                )

            post_type = request.POST.get('post_type', 'scheduled')
            if post_type == 'instant':
                post.scheduled_time = timezone.now()
                post.status = 'scheduled'
                post.save(update_fields=['scheduled_time', 'status'])
                for account in selected_accounts:
                    publish_post_task.delay(post.id, account.id)
                messages.success(request, f"Publishing to {len(selected_accounts)} platform(s).")
            else:
                post.status = 'scheduled'
                post.save(update_fields=['status'])
                messages.success(request, f"Scheduled for {post.scheduled_time}.")

            return redirect('post_list')
    else:
        form = PostForm()
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
        form = PostForm(request.POST, request.FILES, instance=post)
        if form.is_valid():
            new_content = form.cleaned_data.get('content', '')

            # Update on platforms if already published
            platform_results = []
            for ps in post.platform_statuses.filter(status='published'):
                success, msg = _update_on_platform(ps, new_content)
                platform_results.append(msg)

            post = form.save(commit=False)
            post.save()
            form.save_m2m()

            # Rebuild platform statuses
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
        form = PostForm(instance=post)

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
        post.status = 'scheduled'
        post.save(update_fields=['scheduled_time', 'status'])

        for account in accounts:
            PostPlatformStatus.objects.filter(
                post=post, social_account=account
            ).update(status='scheduled')
            publish_post_task.delay(post.id, account.id)

        messages.success(request, f"Publishing to {accounts.count()} platform(s) now.")
    return redirect('post_detail', post_id=post_id)
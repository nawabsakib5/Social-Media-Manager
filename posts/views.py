from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from .models import Post, PostPlatformStatus
from .forms import PostForm
from .tasks import publish_post_task


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

    if post.status == 'published':
        messages.error(request, "Published posts cannot be edited.")
        return redirect('post_detail', post_id=post_id)

    if request.method == 'POST':
        form = PostForm(request.POST, request.FILES, instance=post)
        if form.is_valid():
            post = form.save(commit=False)
            post.status = 'scheduled'
            post.save()
            form.save_m2m()

            # Update platform statuses
            post.platform_statuses.all().delete()
            for account in form.cleaned_data['social_accounts']:
                PostPlatformStatus.objects.create(
                    post=post,
                    social_account=account,
                    status='scheduled'
                )

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
        post.delete()
        messages.success(request, "Post deleted.")
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
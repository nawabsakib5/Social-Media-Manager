from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from .models import Post, PostPlatformStatus
from .forms import PostForm
from .tasks import publish_post_task


@login_required
def post_list(request):
    posts = (
        Post.objects
        .all()
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
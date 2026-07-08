from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from .models import Post
from .forms import PostForm
from .tasks import publish_post_task
from accounts.models import Team, TeamMember


def get_or_create_user_team(user):
    membership = user.teammemberships.first()
    if membership:
        return membership.team
    workspace_name = f"{user.username}'s Workspace"
    team, created = Team.objects.get_or_create(name=workspace_name)
    role = 'admin' if user.is_superuser or user.is_staff else 'editor'
    TeamMember.objects.get_or_create(user=user, team=team, defaults={'role': role})
    return team


@login_required
def post_list(request):
    active_team = get_or_create_user_team(request.user)
    posts = Post.objects.all().order_by('-created_at')
    return render(request, 'posts/post_list.html', {
        'posts': posts,
        'active_team': active_team
    })


@login_required
def post_create(request):
    active_team = get_or_create_user_team(request.user)

    if request.method == 'POST':
        form = PostForm(request.POST, request.FILES, team=active_team)
        if form.is_valid():
            post = form.save(commit=False)
            post.created_by = request.user
            post_type = request.POST.get('post_type', 'scheduled')

            if post_type == 'instant':
                post.status = 'scheduled'
                post.scheduled_time = timezone.now()
                post.save()
                publish_post_task.delay(post.id)
            else:
                post.status = 'scheduled'
                post.save()

            return redirect('post_list')
    else:
        form = PostForm(team=active_team)

    return render(request, 'posts/post_form.html', {'form': form})
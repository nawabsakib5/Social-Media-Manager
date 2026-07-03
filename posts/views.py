from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from .models import Post
from .forms import PostForm
from .tasks import publish_post_task
from accounts.models import Team, TeamMember  # Imported accounts models

def get_or_create_user_team(user):
    """
    Auto-Healing Helper: Automatically creates a default workspace for the user
    if they don't have one, making the system 100% manual-setup free.
    """
    membership = user.teammemberships.first()
    if membership:
        return membership.team
    
    # Auto-create a workspace named after their username
    workspace_name = f"{user.username}'s Workspace"
    team, created = Team.objects.get_or_create(name=workspace_name)
    
    # Superuser/Staff will be Admin, invited users will be Editors
    role = 'admin' if user.is_superuser or user.is_staff else 'editor'
    
    TeamMember.objects.get_or_create(
        user=user,
        team=team,
        defaults={'role': role}
    )
    return team

@login_required
def post_list(request):
    # Auto-resolves or silently heals the user's workspace
    active_team = get_or_create_user_team(request.user)
        
    posts = Post.objects.filter(social_account__team=active_team).order_by('-created_at')
    return render(request, 'posts/post_list.html', {
        'posts': posts,
        'active_team': active_team
    })


@login_required
def post_create(request):
    # Auto-resolves or silently heals the user's workspace
    active_team = get_or_create_user_team(request.user)

    if request.method == 'POST':
        form = PostForm(request.POST, request.FILES, team=active_team)
        if form.is_valid():
            post = form.save(commit=False)
            post.created_by = request.user
            post.save()
            
            # Trigger the Celery background task to publish the post
            publish_post_task.delay(post.id)
            
            return redirect('post_list')
    else:
        form = PostForm(team=active_team)
        
    return render(request, 'posts/post_form.html', {'form': form})
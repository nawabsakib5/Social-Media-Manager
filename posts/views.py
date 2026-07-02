from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from .models import Post
from .forms import PostForm
from .tasks import publish_post_task  

@login_required
def post_list(request):
    membership = request.user.teammemberships.first()
    active_team = membership.team if membership else None
    
    if not active_team:
        return render(request, 'posts/no_team.html')
        
    posts = Post.objects.filter(social_account__team=active_team).order_by('-created_at')
    return render(request, 'posts/post_list.html', {
        'posts': posts,
        'active_team': active_team
    })


@login_required
def post_create(request):
    membership = request.user.teammemberships.first()
    active_team = membership.team if membership else None
    
    if not active_team:
        # Safely redirect to post_list, which will render the no_team.html template
        return redirect('post_list')

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
        form = Form = PostForm(team=active_team)
        
    return render(request, 'posts/post_form.html', {'form': form})
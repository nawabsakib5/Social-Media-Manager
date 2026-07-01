from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import InboxItem
from .forms import ReplyForm


@login_required
def inbox_list(request):
    items = InboxItem.objects.all().order_by('-received_at')
    return render(request, 'inbox/inbox_list.html', {'items': items})


@login_required
def inbox_reply(request, item_id):
    item = get_object_or_404(InboxItem, id=item_id)
    if request.method == 'POST':
        form = ReplyForm(request.POST)
        if form.is_valid():
            reply = form.save(commit=False)
            reply.inbox_item = item
            reply.sent_by = request.user
            reply.save()
            item.is_replied = True
            item.save()
            return redirect('inbox_list')
    else:
        form = ReplyForm()
    return render(request, 'inbox/inbox_reply.html', {'form': form, 'item': item})
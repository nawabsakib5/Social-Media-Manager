from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import Team, TeamMember

@receiver(post_save, sender=User)
def create_default_team(sender, instance, created, **kwargs):
    if created:
       
        team_name = f"{instance.username}'s Team"
        team = Team.objects.create(name=team_name)

        TeamMember.objects.create(
            user=instance,
            team=team,
            role='admin'
        )
@echo off
echo Starting Social Media Manager...

:: Redis (already running as service, no need to start)

:: Terminal 1: Django
start "Django Server" cmd /k "cd /d C:\Users\nawab\Desktop\Social Media Manager && venv\Scripts\activate && python manage.py runserver"

:: Terminal 2: Celery
start "Celery Worker" cmd /k "cd /d C:\Users\nawab\Desktop\Social Media Manager && venv\Scripts\activate && celery -A config worker -l info --pool=solo"

echo All services started!
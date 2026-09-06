import json

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .forms import RegisterForm


def _wants_json(request):
    """True when the caller is an API client (sent JSON) rather than a browser form."""
    return request.content_type == 'application/json'


@csrf_exempt
@require_http_methods(['GET', 'POST'])
def register_view(request):
    """
    GET  -> render the registration page (Sign-up, per the wireframe)
    POST -> POST /auth/register
            Given: a valid new user
            Then: 201, user created, password/hash never returned
    """
    if request.method == 'GET':
        if request.user.is_authenticated:
            return redirect('learning:next_lesson')
        return render(request, 'accounts/register.html', {'form': RegisterForm()})

    # POST
    if _wants_json(request):
        data = json.loads(request.body or '{}')
    else:
        data = request.POST

    form = RegisterForm(data)
    if form.is_valid():
        user = form.save()
        login(request, user)
        payload = {'id': user.id, 'username': user.username, 'email': user.email}
        if _wants_json(request):
            return JsonResponse(payload, status=201)
        return redirect('learning:profile_setup')

    if _wants_json(request):
        return JsonResponse({'errors': form.errors}, status=400)
    return render(request, 'accounts/register.html', {'form': form})


@csrf_exempt
@require_http_methods(['GET', 'POST'])
def login_view(request):
    """
    GET  -> render the login page
    POST -> POST /auth/login
            Given: correct username/password -> 200 + session cookie
            Given: wrong credentials -> 401
    """
    if request.method == 'GET':
        if request.user.is_authenticated:
            return redirect('learning:next_lesson')
        return render(request, 'accounts/login.html')

    if _wants_json(request):
        data = json.loads(request.body or '{}')
    else:
        data = request.POST

    username = data.get('username', '')
    password = data.get('password', '')
    user = authenticate(request, username=username, password=password)

    if user is None:
        if _wants_json(request):
            return JsonResponse({'error': 'Invalid username or password'}, status=401)
        return render(request, 'accounts/login.html', {'error': 'Invalid username or password'})

    login(request, user)
    if _wants_json(request):
        return JsonResponse({'id': user.id, 'username': user.username}, status=200)
    return redirect('learning:next_lesson')


@login_required
def logout_view(request):
    """GET /auth/logout — ends the session and returns to the home page."""
    logout(request)
    return redirect('home')

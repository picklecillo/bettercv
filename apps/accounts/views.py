import json
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth import (
    authenticate,
    get_user_model,
    login,
    logout,
)
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
import sesame.utils

from .credits import grant_credits
from .forms import LoginForm, MagicLinkForm, RegisterForm
from .lemon_squeezy import build_checkout_url, verify_webhook_signature
from .models import CreditTransaction, UserProfile

User = get_user_model()

SIGNUP_CREDITS = 10


# ── Registration ────────────────────────────────────────────────────────────

def register(request):
    if request.user.is_authenticated:
        return redirect('/home/')
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            password = form.cleaned_data['password1']
            user = User.objects.create_user(
                username=email,
                email=email,
                password=password,
            )
            grant_credits(
                user,
                SIGNUP_CREDITS,
                f'Welcome bonus — {SIGNUP_CREDITS} free credits',
                tx_type=CreditTransaction.TxType.SIGNUP_BONUS,
            )
            login(request, user, backend='apps.accounts.backends.EmailBackend')
            return redirect('/home/')
    else:
        form = RegisterForm()
    return render(request, 'accounts/register.html', {'form': form})


# ── Login ────────────────────────────────────────────────────────────────────

def login_view(request):
    if request.user.is_authenticated:
        return redirect('/home/')
    error = None
    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            user = authenticate(
                request,
                email=form.cleaned_data['email'],
                password=form.cleaned_data['password'],
            )
            if user is not None:
                login(request, user)
                next_url = request.GET.get('next', '/home/')
                return redirect(next_url)
            error = "Invalid email or password."
    else:
        form = LoginForm()
    magic_form = MagicLinkForm()
    return render(request, 'accounts/login.html', {
        'form': form,
        'magic_form': magic_form,
        'error': error,
    })


# ── Logout ───────────────────────────────────────────────────────────────────

@require_POST
def logout_view(request):
    logout(request)
    return redirect('/')


# ── Magic link ───────────────────────────────────────────────────────────────

@require_POST
def send_magic_link(request):
    form = MagicLinkForm(request.POST)
    if not form.is_valid():
        return HttpResponse(
            '<p class="magic-error">Please enter a valid email address.</p>',
            content_type='text/html',
        )
    email = form.cleaned_data['email'].lower()
    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        # Don't reveal whether the email exists
        return render(request, 'accounts/_magic_link_sent.html')

    token_params = sesame.utils.get_parameters(user)
    login_url = request.build_absolute_uri(
        f'/accounts/magic-link/login/?{urlencode(token_params)}'
    )
    user.email_user(
        subject='Your BetterCV login link',
        message=(
            f'Click the link below to sign in to BetterCV.\n\n'
            f'{login_url}\n\n'
            f'This link expires in 15 minutes and can only be used once.'
        ),
    )
    return render(request, 'accounts/_magic_link_sent.html')


@require_GET
def magic_link_login(request):
    user = sesame.utils.get_user(request)
    if user is None:
        return render(request, 'accounts/magic_link_invalid.html', status=400)
    login(request, user, backend='sesame.backends.ModelBackend')
    next_url = request.GET.get('next', '/home/')
    return redirect(next_url)


# ── Account dashboard ────────────────────────────────────────────────────────

@login_required
def account(request):
    try:
        profile = request.user.profile
    except UserProfile.DoesNotExist:
        profile = UserProfile.objects.create(user=request.user)
    transactions = CreditTransaction.objects.filter(user=request.user)[:20]
    return render(request, 'accounts/account.html', {
        'profile': profile,
        'transactions': transactions,
    })


# ── Buy credits ──────────────────────────────────────────────────────────────

@login_required
def buy_credits(request):
    packages = []
    for pkg in settings.CREDIT_PACKAGES:
        packages.append({
            **pkg,
            'checkout_url': build_checkout_url(
                pkg['product_id'],
                pkg['variant_id'],
                request.user.id,
                request.user.email,
            ),
        })
    try:
        current_credits = request.user.profile.credits
    except UserProfile.DoesNotExist:
        current_credits = 0
    return render(request, 'accounts/buy.html', {
        'packages': packages,
        'current_credits': current_credits,
    })


# ── Lemon Squeezy webhook ────────────────────────────────────────────────────

@csrf_exempt
@require_POST
def lemon_squeezy_webhook(request):
    signature = request.headers.get('X-Signature', '')
    if not verify_webhook_signature(request.body, signature):
        return HttpResponse(status=401)

    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return HttpResponse(status=400)

    event_name = payload.get('meta', {}).get('event_name', '')
    if event_name != 'order_created':
        return HttpResponse(status=200)

    meta = payload.get('meta', {})
    custom_data = meta.get('custom_data', {})
    user_id = custom_data.get('user_id')
    data = payload.get('data', {})
    order_id = str(data.get('id', ''))
    first_item = data.get('attributes', {}).get('first_order_item', {})
    variant_id = str(first_item.get('variant_id', ''))

    if not user_id or not order_id or not variant_id:
        return HttpResponse(status=400)

    # Idempotency: ignore already-processed orders
    if CreditTransaction.objects.filter(lemon_order_id=order_id).exists():
        return HttpResponse(status=200)

    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        return HttpResponse(status=404)

    credits_to_grant = None
    for pkg in settings.CREDIT_PACKAGES:
        if str(pkg['variant_id']) == variant_id:
            credits_to_grant = pkg['credits']
            break
    if credits_to_grant is None:
        return HttpResponse(status=400)

    grant_credits(
        user,
        credits_to_grant,
        f'Purchase: {credits_to_grant} credits',
        tx_type=CreditTransaction.TxType.PURCHASE,
        lemon_order_id=order_id,
    )
    return HttpResponse(status=200)


# ── Payment redirect pages ───────────────────────────────────────────────────

@login_required
def payment_success(request):
    try:
        current_credits = request.user.profile.credits
    except UserProfile.DoesNotExist:
        current_credits = 0
    return render(request, 'accounts/payment_success.html', {
        'current_credits': current_credits,
    })


def payment_cancel(request):
    return redirect('/accounts/buy/')

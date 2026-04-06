from django.urls import path

from . import views

urlpatterns = [
    path('register/', views.register, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('magic-link/send/', views.send_magic_link, name='magic-link-send'),
    path('magic-link/login/', views.magic_link_login, name='magic-link-login'),
    path('', views.account, name='account'),
    path('buy/', views.buy_credits, name='buy-credits'),
    path('webhooks/lemon-squeezy/', views.lemon_squeezy_webhook, name='lemon-squeezy-webhook'),
    path('payment/success/', views.payment_success, name='payment-success'),
    path('payment/cancel/', views.payment_cancel, name='payment-cancel'),
]

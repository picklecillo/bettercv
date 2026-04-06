from functools import wraps

from django.conf import settings
from django.http import HttpResponse


def htmx_login_required(view_func):
    """
    Like @login_required, but for HTMX requests returns HX-Redirect instead
    of a 302, so the browser navigates to the login page rather than swapping
    the login page HTML into a panel fragment.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if request.user.is_authenticated:
            return view_func(request, *args, **kwargs)
        login_url = getattr(settings, 'LOGIN_URL', '/accounts/login/')
        next_url = request.get_full_path()
        redirect_url = f'{login_url}?next={next_url}'
        if request.headers.get('HX-Request'):
            response = HttpResponse(status=204)
            response['HX-Redirect'] = redirect_url
            return response
        from django.shortcuts import redirect
        return redirect(redirect_url)
    return wrapper

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password

User = get_user_model()


class RegisterForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={'placeholder': 'you@example.com', 'autocomplete': 'email'}),
    )
    password1 = forms.CharField(
        label='Password',
        widget=forms.PasswordInput(attrs={'placeholder': 'Choose a password', 'autocomplete': 'new-password'}),
    )
    password2 = forms.CharField(
        label='Confirm password',
        widget=forms.PasswordInput(attrs={'placeholder': 'Repeat password', 'autocomplete': 'new-password'}),
    )

    def clean_email(self):
        email = self.cleaned_data['email'].lower()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get('password1')
        p2 = cleaned.get('password2')
        if p1 and p2 and p1 != p2:
            self.add_error('password2', "Passwords do not match.")
        if p1:
            try:
                validate_password(p1)
            except forms.ValidationError as e:
                self.add_error('password1', e)
        return cleaned


class LoginForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={'placeholder': 'you@example.com', 'autocomplete': 'email'}),
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'placeholder': 'Password', 'autocomplete': 'current-password'}),
    )


class MagicLinkForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={'placeholder': 'you@example.com', 'autocomplete': 'email'}),
    )

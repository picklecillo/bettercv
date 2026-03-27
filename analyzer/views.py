from django.shortcuts import render


def index(request):
    return render(request, 'analyzer/index.html')


def analyze(request):
    pass  # Phase 2

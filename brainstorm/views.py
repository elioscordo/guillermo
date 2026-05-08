from django.urls import reverse_lazy
from django.views.generic import CreateView, TemplateView
from unfold.views import UnfoldModelAdminViewMixin
from unfold.forms import UserCreationForm  # Use Unfold's styled form
from .models import ContactRequest

class LandingView(CreateView):
    model = ContactRequest
    template_name = "landing.html"
    fields = ['name', 'email']
    success_url = reverse_lazy("landing")


class AdminSignupView(CreateView):
    title = "Create New Admin User"  # Required for Unfold header
    template_name = "admin/signup.html"
    form_class = UserCreationForm
    success_url = reverse_lazy("admin:index")

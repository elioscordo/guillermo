from django.urls import reverse_lazy, reverse
from django.views.generic import CreateView, TemplateView
from django.contrib import messages
from unfold.views import UnfoldModelAdminViewMixin
from unfold.forms import UserCreationForm  # Use Unfold's styled form
from .models import ContactRequest

class LandingView(CreateView):
    model = ContactRequest
    template_name = "landing.html"
    fields = ['name', 'email']
    
    def form_valid(self, form):
        messages.success(self.request, "Thank you for your interest! We'll be in touch shortly.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("landing") + "#contact"


class AdminSignupView(CreateView):
    title = "Create New Admin User"  # Required for Unfold header
    template_name = "admin/signup.html"
    form_class = UserCreationForm
    success_url = reverse_lazy("admin:index")

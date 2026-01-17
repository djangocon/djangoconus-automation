from django.shortcuts import render, redirect
from django.views.generic import FormView, TemplateView
from django.urls import reverse_lazy
from django.utils import timezone
from django.contrib import messages
from .forms import TravelRegistrationForm
from .models import TravelRegistration


class TravelRegistrationView(FormView):
    """
    View for travel safety registration form.
    
    Allows attendees to register their travel information for safety monitoring.
    On successful form submission, creates a new TravelRegistration with 
    'pending_arrival' status and redirects to success page.
    """
    template_name = 'travel_safety/register.html'
    form_class = TravelRegistrationForm
    success_url = reverse_lazy('travel_safety:success')
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'DjangoCon US Travel Safety Registration'
        return context
    
    def form_valid(self, form):
        # Create the registration with default status
        registration = form.save(commit=False)
        registration.status = 'pending_arrival'
        registration.save()
        
        # Store registration ID in session for success page
        self.request.session['registration_id'] = registration.id
        
        messages.success(
            self.request, 
            f"Thank you, {registration.name}! Your travel safety information has been registered successfully."
        )
        
        return super().form_valid(form)
    
    def form_invalid(self, form):
        messages.error(
            self.request,
            "Please correct the errors below and try again."
        )
        return super().form_invalid(form)


class RegistrationSuccessView(TemplateView):
    """
    Success page displayed after successful travel safety registration.
    
    Shows a confirmation message and summary of submitted information.
    Retrieves registration details from session and clears the session data.
    """
    template_name = 'travel_safety/success.html'
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Registration Successful'
        
        # Get registration details if available
        registration_id = self.request.session.get('registration_id')
        if registration_id:
            try:
                registration = TravelRegistration.objects.get(id=registration_id)
                context['registration'] = registration
                # Clear session after displaying
                del self.request.session['registration_id']
            except TravelRegistration.DoesNotExist:
                pass
        
        return context

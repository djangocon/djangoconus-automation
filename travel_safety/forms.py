from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import TravelRegistration


class TravelRegistrationForm(forms.ModelForm):
    """
    Form for travel safety registration.

    Collects attendee travel information including personal details, flight information,
    and emergency contact details. Includes validation for required fields, phone numbers,
    and ensures departure time is after arrival time when provided.
    """

    class Meta:
        model = TravelRegistration
        fields = [
            "name",
            "email",
            "phone",
            "preferred_contact",
            "arrival_airline",
            "arrival_flight_number",
            "arrival_time",
            "arrival_airport",
            "accommodation",
            "departure_airline",
            "departure_flight_number",
            "departure_time",
            "departure_airport",
            "departure_destination",
            "emergency_contact_name",
            "emergency_contact_phone",
            "emergency_contact_relationship",
            "user_notes",
        ]

        widgets = {
            "name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Full name as it appears on your ID"}
            ),
            "email": forms.EmailInput(attrs={"class": "form-control", "placeholder": "your.email@example.com"}),
            "phone": forms.TextInput(attrs={"class": "form-control", "placeholder": "+1 (555) 123-4567"}),
            "preferred_contact": forms.Select(attrs={"class": "form-select"}),
            "arrival_airline": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "e.g., United Airlines, Delta"}
            ),
            "arrival_flight_number": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "e.g., UA1234, DL567"}
            ),
            "arrival_time": forms.DateTimeInput(attrs={"class": "form-control", "type": "datetime-local"}),
            "arrival_airport": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g., ORD, MDW, RFD"}),
            "departure_airline": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "e.g., United Airlines, Delta (optional)"}
            ),
            "departure_flight_number": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "e.g., UA1234, DL567 (optional)"}
            ),
            "departure_time": forms.DateTimeInput(attrs={"class": "form-control", "type": "datetime-local"}),
            "departure_airport": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "e.g., ORD, MDW, RFD (optional)"}
            ),
            "departure_destination": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Where are you flying to? (optional)"}
            ),
            "emergency_contact_name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Full name of emergency contact"}
            ),
            "emergency_contact_phone": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "+1 (555) 123-4567"}
            ),
            "emergency_contact_relationship": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "e.g., Spouse, Parent, Sibling (optional)"}
            ),
            "accommodation": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "placeholder": "Hotel name, address, or other accommodation details (optional)",
                    "rows": 3,
                }
            ),
            "user_notes": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "placeholder": "Any additional information we should know (optional)",
                    "rows": 3,
                }
            ),
        }

        labels = {
            "name": "Full Name",
            "email": "Email Address",
            "phone": "Phone Number",
            "preferred_contact": "Preferred Contact Method",
            "arrival_airline": "Arrival Airline",
            "arrival_flight_number": "Arrival Flight Number",
            "arrival_time": "Arrival Date & Time",
            "arrival_airport": "Arrival Airport",
            "departure_airline": "Departure Airline (Optional)",
            "departure_flight_number": "Departure Flight Number (Optional)",
            "departure_time": "Departure Date & Time (Optional)",
            "departure_airport": "Departure Airport (Optional)",
            "departure_destination": "Departure Destination (Optional)",
            "emergency_contact_name": "Emergency Contact Name",
            "emergency_contact_phone": "Emergency Contact Phone",
            "emergency_contact_relationship": "Relationship to Emergency Contact (Optional)",
            "accommodation": "Where are you staying in Chicago?",
            "user_notes": "Any notes or other info we should know?",
        }

    def clean_arrival_time(self):
        arrival_time = self.cleaned_data.get("arrival_time")
        if arrival_time and arrival_time < timezone.now():
            raise ValidationError("Arrival time must be in the future.")
        return arrival_time

    def clean_phone(self):
        phone = self.cleaned_data.get("phone")
        if phone:
            # Basic phone validation - remove common formatting characters
            cleaned_phone = "".join(filter(str.isdigit, phone))
            if len(cleaned_phone) < 10:
                raise ValidationError("Please enter a valid phone number with at least 10 digits.")
        return phone

    def clean_emergency_contact_phone(self):
        phone = self.cleaned_data.get("emergency_contact_phone")
        if phone:
            # Basic phone validation - remove common formatting characters
            cleaned_phone = "".join(filter(str.isdigit, phone))
            if len(cleaned_phone) < 10:
                raise ValidationError("Please enter a valid emergency contact phone number with at least 10 digits.")
        return phone

    def clean(self):
        cleaned_data = super().clean()
        departure_time = cleaned_data.get("departure_time")
        arrival_time = cleaned_data.get("arrival_time")

        # If departure time is provided, ensure it's after arrival time
        if departure_time and arrival_time and departure_time <= arrival_time:
            raise ValidationError(
                {
                    "departure_time": "Departure time must be after arrival time.",
                    "arrival_time": "Arrival time must be before departure time.",
                },
            )

        return cleaned_data

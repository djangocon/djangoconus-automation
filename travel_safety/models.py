from django.db import models


class TravelRegistration(models.Model):
    """
    Travel Safety Registration model for DjangoCon US attendees.

    This model stores travel information for conference attendees to enable
    safety monitoring and emergency contact procedures. All data is automatically
    deleted 30 days after the conference.
    """

    STATUS_CHOICES = [
        ("pending_arrival", "Pending Arrival"),
        ("arrived_safely", "Arrived Safely"),
        ("pending_departure", "Pending Departure"),
        ("all_checks_complete", "All Checks Complete"),
        ("check_failed", "Check Failed"),
        ("emergency_contact_notified", "Emergency Contact Notified"),
        ("cancelled", "Cancelled"),
    ]

    CONTACT_CHOICES = [
        ("whatsapp", "WhatsApp"),
        ("signal", "Signal"),
        ("sms", "SMS"),
    ]

    # Personal Information
    name = models.CharField(max_length=200)
    email = models.EmailField()
    phone = models.CharField(max_length=20)
    preferred_contact = models.CharField(max_length=20, choices=CONTACT_CHOICES, default="whatsapp")

    # Arrival Information
    arrival_airline = models.CharField(max_length=100)
    arrival_flight_number = models.CharField(max_length=20)
    arrival_time = models.DateTimeField()
    arrival_airport = models.CharField(max_length=100)

    # Departure Information (optional)
    departure_airline = models.CharField(max_length=100, blank=True, null=True)
    departure_flight_number = models.CharField(max_length=20, blank=True, null=True)
    departure_time = models.DateTimeField(blank=True, null=True)
    departure_airport = models.CharField(max_length=100, blank=True, null=True)
    departure_destination = models.CharField(max_length=100, blank=True, null=True)

    # Accommodation Information (optional)
    accommodation = models.TextField(blank=True, null=True, help_text="Where you are staying in Chicago")

    # Emergency Contact
    emergency_contact_name = models.CharField(max_length=200)
    emergency_contact_phone = models.CharField(max_length=20)
    emergency_contact_relationship = models.CharField(max_length=100, blank=True, null=True)

    # Additional Information (optional)
    user_notes = models.TextField(blank=True, null=True, help_text="Any notes or other info we should know?")

    # Status and Tracking
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default="pending_arrival")
    notes = models.TextField(blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["arrival_time"]
        verbose_name = "Travel Registration"
        verbose_name_plural = "Travel Registrations"

    def __str__(self):
        return f"{self.name} - {self.arrival_time.strftime('%Y-%m-%d %H:%M')}"

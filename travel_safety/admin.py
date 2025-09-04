from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from .models import TravelRegistration


@admin.register(TravelRegistration)
class TravelRegistrationAdmin(admin.ModelAdmin):
    """
    Django admin configuration for TravelRegistration model.
    
    Provides a comprehensive admin interface for organizers to monitor and manage
    travel safety registrations. Includes list view, filtering, search, and 
    organized fieldsets for efficient workflow.
    """
    list_display = [
        'name', 'email', 'arrival_time_formatted', 'departure_time_formatted', 
        'status', 'preferred_contact', 'created_at_formatted'
    ]
    
    list_filter = [
        'status',
        ('arrival_time', admin.DateFieldListFilter),
        ('departure_time', admin.DateFieldListFilter),
        'preferred_contact',
        ('created_at', admin.DateFieldListFilter),
    ]
    
    search_fields = [
        'name', 'email', 'phone', 'arrival_flight_number', 'departure_flight_number',
        'emergency_contact_name', 'emergency_contact_phone', 'accommodation', 'user_notes'
    ]
    
    readonly_fields = ['created_at', 'updated_at']
    
    list_editable = ['status']
    
    ordering = ['arrival_time']
    
    fieldsets = (
        ('Personal Information', {
            'fields': ('name', 'email', 'phone', 'preferred_contact')
        }),
        ('Arrival Flight Information', {
            'fields': ('arrival_airline', 'arrival_flight_number', 'arrival_time', 'arrival_airport')
        }),
        ('Accommodation Information', {
            'fields': ('accommodation',),
            'classes': ('collapse',),
            'description': 'Optional accommodation details provided by attendee'
        }),
        ('Departure Flight Information', {
            'fields': ('departure_airline', 'departure_flight_number', 'departure_time', 
                      'departure_airport', 'departure_destination'),
            'classes': ('collapse',),
            'description': 'Optional departure flight information'
        }),
        ('Emergency Contact', {
            'fields': ('emergency_contact_name', 'emergency_contact_phone', 'emergency_contact_relationship')
        }),
        ('Status & Notes', {
            'fields': ('status', 'user_notes', 'notes'),
            'description': 'Status tracking and notes (user_notes are from attendee, notes are for admin use)'
        }),
        ('System Information', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )
    
    def arrival_time_formatted(self, obj):
        if obj.arrival_time:
            return obj.arrival_time.strftime('%b %d, %Y %I:%M %p')
        return '-'
    arrival_time_formatted.short_description = 'Arrival'
    arrival_time_formatted.admin_order_field = 'arrival_time'
    
    def departure_time_formatted(self, obj):
        if obj.departure_time:
            return obj.departure_time.strftime('%b %d, %Y %I:%M %p')
        return '-'
    departure_time_formatted.short_description = 'Departure'
    departure_time_formatted.admin_order_field = 'departure_time'
    
    def created_at_formatted(self, obj):
        return obj.created_at.strftime('%b %d, %Y %I:%M %p')
    created_at_formatted.short_description = 'Registered'
    created_at_formatted.admin_order_field = 'created_at'
    
    def status_badge(self, obj):
        colors = {
            'pending_arrival': '#f59e0b',  # yellow
            'arrived_safely': '#10b981',   # green
            'pending_departure': '#3b82f6', # blue
            'all_checks_complete': '#059669', # emerald
            'check_failed': '#ef4444',      # red
            'emergency_contact_notified': '#dc2626', # red
            'cancelled': '#6b7280',         # gray
        }
        color = colors.get(obj.status, '#6b7280')
        return format_html(
            '<span style="color: white; background-color: {}; padding: 3px 8px; border-radius: 4px; font-size: 11px;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_badge.short_description = 'Status'
    status_badge.admin_order_field = 'status'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related()
    
    def has_add_permission(self, request):
        # Only allow staff to add registrations through admin
        return request.user.is_staff
    
    def has_change_permission(self, request, obj=None):
        return request.user.is_staff
    
    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser

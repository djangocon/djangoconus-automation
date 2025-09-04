# Travel Safety App

The Travel Safety app enables DjangoCon US organizers to collect and monitor attendee travel information for safety purposes during the conference.

## Overview

This app provides a registration system where attendees can submit their travel details including flight information and emergency contacts. Organizers can then monitor arrivals/departures and perform safety check-ins as needed.

## Key Features

- **Public Registration Form**: Attendees can register their travel information via a web form
- **Comprehensive Data Collection**: Captures personal info, flight details, and emergency contacts
- **Admin Interface**: Full Django admin integration for organizer workflow
- **Data Retention Policy**: Automatic 30-day data deletion after conference
- **Responsive Design**: Mobile-friendly interface using Tailwind CSS

## URLs

- `/travel-safety/` - Registration form
- `/travel-safety/success/` - Success page after registration

## Models

### TravelRegistration

Stores all attendee travel information with the following key fields:

**Personal Information:**
- `name` - Full name
- `email` - Email address  
- `phone` - Phone number
- `preferred_contact` - Contact method preference (WhatsApp, Signal, SMS)

**Arrival Information:**
- `arrival_airline` - Airline name
- `arrival_flight_number` - Flight number
- `arrival_time` - Arrival date/time (US/Chicago timezone)
- `arrival_airport` - Airport code/name

**Departure Information (Optional):**
- `departure_airline` - Airline name
- `departure_flight_number` - Flight number  
- `departure_time` - Departure date/time (US/Chicago timezone)
- `departure_airport` - Airport code/name
- `departure_destination` - Final destination

**Emergency Contact:**
- `emergency_contact_name` - Contact person name
- `emergency_contact_phone` - Contact person phone
- `emergency_contact_relationship` - Relationship to attendee

**Status Tracking:**
- `status` - Current status (see Status Workflow below)
- `notes` - Organizer notes
- `created_at` / `updated_at` - Timestamps

## Status Workflow

The registration status follows this workflow:

1. **Pending Arrival** (default) - Registration submitted, awaiting arrival
2. **Arrived Safely** - Attendee confirmed arrival
3. **Pending Departure** - Arrival confirmed, awaiting departure
4. **All Checks Complete** - Both arrival and departure confirmed
5. **Check Failed** - Unable to confirm safety status
6. **Emergency Contact Notified** - Emergency procedures activated
7. **Cancelled** - Registration cancelled

## Admin Interface

The Django admin provides comprehensive tools for organizers:

### List View Features
- Key information display (name, email, flight times, status)
- Status filtering and search functionality
- Quick status updates via list_editable
- Date-based filtering for arrival/departure times
- Contact method filtering

### Detail View Features
- Organized fieldsets for easy data review:
  - Personal Information
  - Arrival Flight Information
  - Departure Flight Information (collapsible)
  - Emergency Contact
  - Status & Notes
  - System Information (timestamps)

### Search & Filtering
- Search by name, email, phone, flight numbers, emergency contacts
- Filter by status, arrival/departure dates, contact preferences
- Default ordering by arrival time

## Security Features

- **CSRF Protection**: All forms include CSRF tokens
- **Input Validation**: Server-side validation for all fields
- **Data Sanitization**: Proper escaping in templates
- **Access Control**: Admin interface restricted to staff users
- **Permission Levels**: 
  - Staff: Can view and modify registrations
  - Superuser: Can delete registrations

## Data Validation

### Form-Level Validation
- Required field validation
- Email format validation
- Phone number validation (minimum 10 digits)
- Future date validation for arrival times
- Logical validation (departure after arrival)

### Client-Side Features
- HTML5 datetime-local inputs for better UX
- Placeholder text and form labels
- Responsive grid layouts
- Field grouping for clarity

## Usage Instructions

### For Attendees
1. Access the registration URL provided by organizers
2. Fill out all required information
3. Optionally provide departure flight details
4. Submit form and review confirmation

### For Organizers
1. Access Django admin at `/admin/`
2. Navigate to Travel Safety → Travel Registrations
3. Use filters to find specific registrations
4. Update status as attendees are confirmed safe
5. Add notes for any special circumstances
6. Use search to quickly locate specific attendees

### Data Management
- All data automatically deleted 30 days post-conference
- Export functionality available through Django admin
- Bulk status updates supported via admin actions

## Technical Details

- **Framework**: Django 4.2.11
- **Database**: PostgreSQL with proper indexing
- **Frontend**: Tailwind CSS for styling
- **Timezone**: US/Chicago (Central Time)
- **Python**: 3.11 with type hints

## Development

### Running Tests
```bash
just test travel_safety/
```

### Code Quality
```bash
just lint  # Run all pre-commit hooks
just check # Run Django system checks
```

### Database Operations  
```bash
just makemigrations  # Create migrations
just migrate         # Apply migrations
```

## Support

For technical issues or feature requests related to the Travel Safety app, contact the DjangoCon US technical team.
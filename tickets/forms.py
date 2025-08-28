from django import forms


class BulkTicketCreationForm(forms.Form):
    urls = forms.CharField(
        widget=forms.Textarea(
            attrs={
                "rows": 10,
                "cols": 80,
                "placeholder": "Enter one URL per line\nhttps://example.com/ticket1\nhttps://example.com/ticket2",
                "class": "w-full p-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500",
            }
        ),
        label="Ticket URLs",
        help_text="Enter one URL per line. Each line will create a new ticket link.",
    )

    def clean_urls(self):
        """Validate and parse the URLs from the textarea."""
        urls_text = self.cleaned_data["urls"]
        urls = [line.strip() for line in urls_text.splitlines() if line.strip()]

        if not urls:
            raise forms.ValidationError("Please enter at least one URL.")

        # Basic URL validation
        for url in urls:
            if not url.startswith(("http://", "https://")):
                raise forms.ValidationError(f"Invalid URL: {url}. URLs must start with http:// or https://")

        return urls

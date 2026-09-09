from django import forms

from core.models import Project
from frontend.selectors.projects import (
    DEFAULT_PROJECT_SORT,
    PROJECT_SORT_CHOICES,
    PROJECT_SORT_OPTIONS,
)


class ProjectDirectoryFilterForm(forms.Form):
    query = forms.CharField(
        required=False,
        max_length=100,
        label="Search projects",
        widget=forms.TextInput(
            attrs={
                "type": "search",
                "placeholder": "Project name",
                "autocomplete": "off",
            }
        ),
    )
    status = forms.CharField(
        required=False,
        label="Status",
        widget=forms.Select(
            choices=(("", "All statuses"), *Project.Status.choices),
        ),
    )
    priority = forms.CharField(
        required=False,
        label="Priority",
        widget=forms.Select(
            choices=(("", "All priorities"), *Project.Priority.choices),
        ),
    )
    criticality = forms.CharField(
        required=False,
        label="Criticality",
        widget=forms.Select(
            choices=(("", "All criticality levels"), *Project.Criticality.choices),
        ),
    )
    starts_on_or_after = forms.DateField(
        required=False,
        label="Starts on or after",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    ends_on_or_before = forms.DateField(
        required=False,
        label="Ends on or before",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    sort = forms.CharField(
        required=False,
        label="Sort by",
        initial=DEFAULT_PROJECT_SORT,
        widget=forms.Select(choices=PROJECT_SORT_CHOICES),
    )

    @staticmethod
    def _valid_choice(value, choices):
        valid_values = {choice_value for choice_value, _label in choices}
        return value if value in valid_values else ""

    def clean_status(self):
        return self._valid_choice(
            self.cleaned_data["status"],
            Project.Status.choices,
        )

    def clean_priority(self):
        return self._valid_choice(
            self.cleaned_data["priority"],
            Project.Priority.choices,
        )

    def clean_criticality(self):
        return self._valid_choice(
            self.cleaned_data["criticality"],
            Project.Criticality.choices,
        )

    def clean_sort(self):
        sort = self.cleaned_data["sort"]
        return sort if sort in PROJECT_SORT_OPTIONS else DEFAULT_PROJECT_SORT


class ProjectForm(forms.ModelForm):
    """Create or update a project through the model validation pipeline."""

    class Meta:
        model = Project
        fields = (
            "name",
            "description",
            "start_date",
            "end_date",
            "estimated_hours",
            "status",
            "priority",
            "criticality",
        )
        labels = {
            "estimated_hours": "Project estimate (hours)",
        }
        help_texts = {
            "name": "Use the project name managers will recognize in planning.",
            "description": (
                "Summarize the delivery goal and planning context for the project."
            ),
            "start_date": "The planned first day of project work.",
            "end_date": "The planned final day of project work.",
            "estimated_hours": (
                "Enter the total stored effort estimate for the project."
            ),
            "status": "Choose the project's current delivery stage.",
            "priority": "Indicate the project's relative planning priority.",
            "criticality": "Indicate how critical this project is to the organization.",
        }
        widgets = {
            "name": forms.TextInput(attrs={"autocomplete": "off"}),
            "description": forms.Textarea(attrs={"rows": 5}),
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
            "estimated_hours": forms.NumberInput(
                attrs={"min": "0", "step": "0.01"}
            ),
        }

from django import forms

from core.models import Skill


class SkillDirectoryFilterForm(forms.Form):
    category = forms.CharField(
        required=False,
        max_length=100,
        label="Category",
        widget=forms.Select(choices=(("", "All categories"),)),
    )

    def __init__(self, *args, categories=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].widget.choices = (
            ("", "All categories"),
            *((category, category) for category in categories),
        )


class SkillForm(forms.ModelForm):
    """Create or update a skill through the model validation pipeline."""

    class Meta:
        model = Skill
        fields = ("name", "category")
        help_texts = {
            "name": "Use the skill name employees and project requirements will share.",
            "category": "Group related capabilities under a consistent category.",
        }
        widgets = {
            "name": forms.TextInput(attrs={"autocomplete": "off"}),
            "category": forms.TextInput(attrs={"autocomplete": "off"}),
        }

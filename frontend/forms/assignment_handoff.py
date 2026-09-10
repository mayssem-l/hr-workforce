from django import forms

from frontend.assignment_handoff import (
    InvalidHandoffToken,
    StaleHandoffToken,
    issue_handoff_token,
    validate_handoff_token,
)


class AssignmentHandoffForm(forms.Form):
    submission_token = forms.CharField(
        widget=forms.HiddenInput,
        error_messages={
            "required": "This staffing confirmation is no longer valid.",
        },
    )

    def __init__(
        self,
        *args,
        project,
        user,
        category,
        input_signature=None,
        **kwargs,
    ):
        self.project = project
        self.user = user
        self.category = category
        self.input_signature = input_signature
        self.is_stale = False
        if not args and "data" not in kwargs:
            initial = kwargs.setdefault("initial", {})
            initial.setdefault(
                "submission_token",
                issue_handoff_token(
                    project_id=project.project_id,
                    user_id=user.pk,
                    category=category,
                    input_signature=input_signature,
                ),
            )
        super().__init__(*args, **kwargs)

    def clean_submission_token(self):
        token = self.cleaned_data["submission_token"]
        try:
            return validate_handoff_token(
                token,
                project_id=self.project.project_id,
                user_id=self.user.pk,
                category=self.category,
                input_signature=self.input_signature,
            )
        except StaleHandoffToken as exc:
            self.is_stale = True
            raise forms.ValidationError(
                "Planning inputs changed after this review was prepared."
            ) from exc
        except InvalidHandoffToken as exc:
            raise forms.ValidationError(
                "This staffing confirmation is no longer valid."
            ) from exc

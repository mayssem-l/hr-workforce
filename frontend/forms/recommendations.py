from django import forms

from frontend.recommendation_execution import (
    InvalidRecommendationSubmissionToken,
    issue_recommendation_submission_token,
    validate_recommendation_submission_token,
)


class RecommendationGenerationForm(forms.Form):
    submission_token = forms.CharField(
        widget=forms.HiddenInput,
        error_messages={
            "required": "This recommendation request is no longer valid.",
        },
    )

    def __init__(self, *args, project, user, **kwargs):
        self.project = project
        self.user = user
        if not args and "data" not in kwargs:
            initial = kwargs.setdefault("initial", {})
            initial.setdefault(
                "submission_token",
                issue_recommendation_submission_token(
                    project_id=project.project_id,
                    user_id=user.pk,
                ),
            )
        super().__init__(*args, **kwargs)

    def clean_submission_token(self):
        token = self.cleaned_data["submission_token"]
        try:
            return validate_recommendation_submission_token(
                token,
                project_id=self.project.project_id,
                user_id=self.user.pk,
            )
        except InvalidRecommendationSubmissionToken as exc:
            raise forms.ValidationError(
                "This recommendation request is no longer valid."
            ) from exc

from django.contrib.auth.decorators import login_required, permission_required


WRITE_PERMISSION_ACTIONS = frozenset({"add", "change", "delete"})


def _model_permission_required(model, action):
    opts = model._meta
    permission_name = f"{opts.app_label}.{action}_{opts.model_name}"

    def decorator(view_func):
        permission_guarded_view = permission_required(
            permission_name,
            raise_exception=True,
        )(view_func)
        return login_required(permission_guarded_view)

    return decorator


def read_model_permission_required(model):
    """Require authentication and the model's standard view permission."""

    return _model_permission_required(model, "view")


def read_models_permission_required(*models):
    """Require view permission for a primary model and its displayed context."""

    if not models:
        raise ValueError("At least one model is required for a read guard.")

    permission_names = tuple(
        f"{model._meta.app_label}.view_{model._meta.model_name}"
        for model in models
    )

    def decorator(view_func):
        permission_guarded_view = permission_required(
            permission_names,
            raise_exception=True,
        )(view_func)
        return login_required(permission_guarded_view)

    return decorator


def write_model_permission_required(model, action="change"):
    """Require authentication and one standard model mutation permission."""

    if action not in WRITE_PERMISSION_ACTIONS:
        allowed_actions = ", ".join(sorted(WRITE_PERMISSION_ACTIONS))
        raise ValueError(f"Write permission action must be one of: {allowed_actions}.")

    return _model_permission_required(model, action)

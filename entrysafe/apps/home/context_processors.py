"""Template context shared by every page: the app-shell navigation and the active theme."""
from django.urls import reverse


def _nav(user):
    if user.is_staff:
        items = [
            ("approvals:overview", "Overview", "home", "approvals", "overview"),
            ("approvals:registrations", "Registrations", "check2", "approvals", "registrations"),
        ]
    else:
        items = [("home:home", "Home", "home", "home", None)]
    items += [
        ("profile:profile", "Profile", "user", "profile", None),
        ("user_settings:settings", "Settings", "gear", "user_settings", None),
    ]
    return items


def shell(request):
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {"theme": "", "shell_nav": []}

    match = getattr(request, "resolver_match", None)
    ns = match.namespace if match else ""
    name = match.url_name if match else ""
    nav = []
    for url_name, label, icon, item_ns, item_name in _nav(user):
        current = ns == item_ns and (item_name is None or name == item_name or (
            item_name == "registrations" and name in {"approve", "disapprove", "proof"}))
        if item_ns == "home" and ns == "home":
            current = True
        nav.append({"url": reverse(url_name), "label": label, "icon": icon, "current": current})

    settings_obj = getattr(user, "settings", None)
    return {
        "theme": "dark" if settings_obj and settings_obj.dark_mode else "light",
        "shell_nav": nav,
        "shell_panel_title": "Administration" if user.is_staff else "My Unit",
        "shell_display_name": user.get_full_name() or user.get_username(),
        "shell_role_label": "Administrator" if user.is_staff else "Resident",
        "shell_unit": getattr(getattr(user, "profile", None), "unit_label", ""),
    }

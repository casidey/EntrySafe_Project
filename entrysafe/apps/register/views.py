import os

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from django.shortcuts import render, redirect
from django.utils import timezone

from apps.profile.models import UserProfile

TOWERS = ["1", "2", "3", "4"]
ALLOWED_EXT = {".pdf", ".png", ".jpg", ".jpeg"}
MAX_PROOF_BYTES = 15 * 1024 * 1024


def _render(request, error=None, step=1, form=None):
    ctx = {"towers": TOWERS, "form": form or {}, "start_step": step}
    if error:
        ctx["error"] = error
    return render(request, "register/register.html", ctx)


def register_view(request):
    if request.user.is_authenticated:
        return redirect("home:home")
    if request.method != "POST":
        return _render(request)

    p = request.POST
    form = {
        "fullName": p.get("fullName", "").strip(),
        "contactNumber": p.get("contactNumber", "").strip(),
        "emailAddress": p.get("emailAddress", "").strip(),
        "tower": p.get("tower", "2"),
        "unitNumber": p.get("unitNumber", "").strip(),
    }
    password = p.get("password", "")
    email = form["emailAddress"]
    username = p.get("username", "").strip() or email or form["fullName"].lower().replace(" ", "_")
    proof = request.FILES.get("proofDocument")

    # ---- step 1 checks
    if not form["fullName"] or not email or not password:
        return _render(request, "Please provide your name, email, and password.", 1, form)
    try:
        validate_email(email)
    except ValidationError:
        return _render(request, "Please enter a valid email address.", 1, form)
    try:
        validate_password(password)
    except ValidationError as exc:
        return _render(request, " ".join(exc.messages), 1, form)
    if User.objects.filter(username__iexact=username).exists() or User.objects.filter(email__iexact=email).exists():
        return _render(request, "An account or pending registration with this username or email already exists.", 1, form)

    # ---- step 2 checks
    if form["tower"] not in TOWERS:
        form["tower"] = "2"
    if not form["unitNumber"]:
        return _render(request, "Please enter your unit number.", 2, form)
    if not proof:
        return _render(request, "Please upload a verification document.", 2, form)
    if os.path.splitext(proof.name)[1].lower() not in ALLOWED_EXT:
        return _render(request, "The document must be a PDF, PNG or JPG file.", 2, form)
    if proof.size > MAX_PROOF_BYTES:
        return _render(request, "The document is larger than 15MB.", 2, form)
    if p.get("consent") != "on":
        return _render(request, "Please confirm the information is accurate.", 2, form)

    unit = form["unitNumber"]
    unit_label = f"Tower {form['tower']}, " + (unit if unit.lower().startswith("unit") else f"Unit {unit}")

    # The account exists but is inactive until an administrator approves the profile.
    with transaction.atomic():
        user = User.objects.create_user(
            username=username, email=email, password=password, first_name=form["fullName"], is_active=False,
        )
        profile = UserProfile.objects.create(
            user=user,
            role=UserProfile.Role.RESIDENT,
            full_name=form["fullName"],
            unit_number=unit_label,
            contact_number=form["contactNumber"],
            id_proof_image=proof,
            approval_status=UserProfile.ApprovalStatus.PENDING,
        )
    request.session["registration_submitted"] = {
        "reference": profile.reference,
        "unit": unit_label,
        "date": timezone.localtime(profile.created_at).strftime("%b %d, %Y"),
    }
    return redirect("login:login")

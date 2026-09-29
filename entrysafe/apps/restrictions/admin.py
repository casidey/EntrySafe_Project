from django.contrib import admin

from .models import PersonRestrictionRequest, RestrictedPerson, RestrictedVehicle, VehicleRestrictionRequest

for m in (PersonRestrictionRequest, VehicleRestrictionRequest, RestrictedPerson, RestrictedVehicle):
    admin.site.register(m)

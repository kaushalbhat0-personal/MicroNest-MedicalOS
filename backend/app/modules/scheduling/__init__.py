"""Scheduling domain: practitioner availability as booked commitments.

An Appointment is a scheduled commitment (who / where / when). It is NOT an
encounter, NOT a clinical record, and NOT a billing record — those reference
appointments by ID from future modules. No clinical payload lives here.
"""

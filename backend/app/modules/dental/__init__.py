"""Dental clinical extension. Consumes generic patient/encounter/practitioner
primitives — never duplicates them (no DentalPatient, no DentalAppointment,
no billing). Findings are clinical facts over time; the odontogram is a
projection derived from these rows, never stored as pixels."""

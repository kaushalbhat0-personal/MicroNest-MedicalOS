"""Patient identity module. Demographics/contact minimum for scheduling.

A Patient is an identity record scoped to exactly one tenant. It carries NO
clinical data (no encounters, notes, diagnoses) — those belong to future
clinical modules that reference patients by ID.
"""

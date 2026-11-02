"""Clinical foundation: encounters, notes, observations, diagnoses.

An Encounter is a care episode (NOT an appointment — appointments schedule
time, encounters contain care). All clinical facts anchor to an encounter
and become immutable at finalization; corrections use supersede chains,
never UPDATEs of finalized content. No clinical text ever enters audit/logs.
"""

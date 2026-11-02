# Cloud (P7 target)

Same containers as dev, managed services: Postgres (PITR), S3, Redis,
SES/SMS provider, secret manager. Release = versioned bundle + migrate job
(never migrate-at-boot) + blue-green deploy. Details land with P7.

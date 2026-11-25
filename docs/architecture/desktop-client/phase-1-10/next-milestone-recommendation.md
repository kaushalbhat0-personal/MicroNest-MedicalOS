# Recommended M12

## Primary: Dentist validation sprint + consent-list API (if approved)

M11 delivers software-complete dental charting against existing contracts, but **clinical validation is PENDING**. M12 should prioritize:

1. Live dentist review using [dentist-review-package.md](./dentist-review-package.md)  
2. If approved: implement any agreed policy (e.g. plan activation consent) with migrations/tests  
3. Add `GET` consents-by-subject if product requires durable consent history in UI  
4. Optional primary dentition only after explicit dentist decision

## Alternates

- Clinic AR reconciliation HTTP + desktop  
- PDF invoice/credit-note render  
- M9 workforce backlog (leave cancel, balances, schedule PATCH)

## Defer

Offline clinical writes, AI CDS, production signing/deploy, Android APK.

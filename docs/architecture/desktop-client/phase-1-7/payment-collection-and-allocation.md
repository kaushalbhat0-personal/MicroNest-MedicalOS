# Payment Collection and Allocation

**Methods (offline/manual only):** `cash`, `upi`, `manual_card`, `manual_other`

| Feature | API | Permission | Rule | Tests |
|---------|-----|------------|------|-------|
| Record | POST `/payments` | `payment.record` | Idempotency-Key; amount string | evidence + payments API |
| Duplicate submit | same key replay | — | Returns same payment id | evidence |
| Allocate | POST `.../allocations` | `payment.record` | ≤ unallocated and ≤ outstanding | evidence |
| Over-allocate | same | — | Rejected (409) | evidence |
| Partial pay | allocate less than grand_total | — | invoice → partially_paid / outstanding reduced | evidence 200/300 split |

No card credential capture. No payment gateway. No SaaS/Razorpay clinic AR.

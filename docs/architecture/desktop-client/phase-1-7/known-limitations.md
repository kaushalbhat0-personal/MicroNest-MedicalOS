# Known Limitations — M8

1. **No clinic reconciliation HTTP API** — dues + invoice balance only.
2. **No AR aging endpoint** — dues filter client-side on bounded invoice list.
3. **Refunds / credit notes** supported by API but not primary desktop UX in M8.
4. **Convert → draft invoice** still requires `invoice.issue`.
5. **Timeline** omits estimate events (backend).
6. **No payment gateway / card capture / Razorpay clinic AR**.
7. **No offline financial writes**.
8. **No PDF invoice render API**.
9. Interactive filmed click-tour not separately recorded (API evidence + EXE rebuild).
10. Not production signed / not deployed.

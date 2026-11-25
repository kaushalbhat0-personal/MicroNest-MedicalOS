# Dentist Review Package — M11

**Status:** Prepared for review — **clinical validation PENDING**  
**Data:** Synthetic patients only. No real PHI.

## Purpose

Obtain explicit professional feedback before claiming dental workflow approval. Software tests ≠ clinical approval.

## Materials for reviewer

1. Workflow map: [dental-workflow-map.md](./dental-workflow-map.md)  
2. Odontogram notes: [odontogram-audit.md](./odontogram-audit.md)  
3. Consent policy: [clinical-security-and-consent.md](./clinical-security-and-consent.md) + `docs/security/P3-6-dental-consent-report.md`  
4. Screenshots (synthetic): use debug EXE Dental tab + Treatment plans hub; also existing `docs/ui-ux/screenshots/p33-dental-chart.png` / `p33-dental-plans.png` if still representative  
5. Evidence JSON (no names): [evidence/m11_dental_evidence.json](./evidence/m11_dental_evidence.json)

## Questions for dentist

### Numbering & chart
1. Is FDI permanent-only acceptable for v1 pilot clinics?  
2. When should primary dentition (51–85) be supported?  
3. Should anterior/posterior surface rules be enforced?  
4. How should “missing tooth” be represented (condition vs procedure)?

### Findings vs treatment
5. Is the finding / planned / completed visual distinction clinically clear?  
6. Should historical resolved findings remain visible on the chart?

### Consent
7. Must **plan activation** require granted plan-scoped consent? (currently **no**)  
8. Are any procedure codes exempt from consent (e.g. exam-only)?  
9. Should consent expire after N days?  
10. Confirm withdrawn consent must block `completed` (current: yes).

### Plans
11. Is plan item lifecycle (proposed→planned→in_progress→completed) adequate?  
12. Should estimate creation be mandatory before procedures?

## Sign-off template

```
Reviewer name: ____________________
Credentials / clinic: ____________________
Date: ____________________

I have reviewed the M11 dental workflow materials (synthetic data).

[ ] Approve FDI permanent-only for pilot
[ ] Approve procedure consent hard-gate as implemented
[ ] Approve plan activation WITHOUT consent gate
[ ] Request changes (list below)
[ ] Do NOT approve for clinical use

Comments:
________________________________________________

Signature: ____________________
```

**Do not mark clinical validation PASS until a real dentist completes this form.**

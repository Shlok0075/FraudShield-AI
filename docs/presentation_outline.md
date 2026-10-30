# Presentation (PPT) Structure — 12-18 Slides

1. **Title** — project name, your name, guide name, college. No clutter.
2. **Introduction** — one-sentence problem + one-sentence solution.
3. **Problem** — fraud statistics (cite a source), pain points of rule-based systems. One chart/icon.
4. **Existing System** — brief bullet list of rule-based limitations. No code.
5. **Proposed System** — FraudShield AI's approach in 3-4 bullets + architecture thumbnail.
6. **Objectives** — bullet list from `docs/requirements.md` §3.
7. **Architecture** — the component diagram from `docs/architecture.md` §1, full slide.
8. **Technology Stack** — React, FastAPI, PostgreSQL, XGBoost, Socket.IO logos/icons. No installation detail.
9. **Dataset** — name, size (120,000 rows), class imbalance (0.17% fraud), one chart (`screenshots/eda/`).
10. **ML Methodology** — pipeline diagram (Data → Features → Model → Evaluation). Explain SMOTE vs class_weight verbally.
11. **Model Results** — the comparison table from `docs/model_selection.md` + chosen model + why.
12. **Dashboard** — screenshot of the live dashboard. Let it speak for itself.
13. **Real-Time Detection** — the sequence diagram from `docs/uml_diagrams.md`. Explain WebSocket flow verbally.
14. **Security** — bullet list from `docs/security.md`. No secrets/keys ever, even fake-looking ones.
15. **Testing** — summary numbers from `docs/test_report.md` (45/45 tests passing, 85% coverage). No raw pytest dump.
16. **Results** — key achieved metrics (PR-AUC 0.4324, precision 0.7647) + system capabilities recap.
17. **Future Scope** — bullet list from `docs/final_report.md` §32.
18. **Conclusion** — 2-3 sentence wrap-up + thank you.

**What NOT to put on slides:** full code blocks, raw terminal logs, dense paragraphs, unexplained jargon
without a verbal walkthrough planned.

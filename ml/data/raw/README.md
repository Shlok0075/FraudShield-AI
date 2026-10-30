# ml/data/raw/

This folder is intentionally empty in the delivered project (the generated dataset is large — ~66MB as a CSV —
and fully regeneratable, so it isn't shipped to keep the project lightweight).

**To regenerate the exact same dataset used to train the shipped `ml/models/model.joblib`:**

```bash
cd ml
source ../backend/venv/bin/activate   # or your own venv with ml/requirements.txt installed
python src/generate_dataset.py
```

This is **deterministic** (`random_state=42` throughout `generate_dataset.py`), so it reproduces the identical
120,000-row, 0.17%-fraud dataset this project's EDA notebooks, preprocessing, and trained model were built
against.

If you have access to the real Kaggle "Credit Card Fraud Detection" (ULB) dataset, you can instead drop your
own `creditcard.csv` here (same schema: `Time`, `V1`-`V28`, `Amount`, `Class`) — every downstream script
(`preprocessing.py`, `train.py`, the notebooks) works unchanged, since only the file's contents differ, not its
shape. See `docs/dataset_choice.md` for the full discussion.

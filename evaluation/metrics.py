"""Binary metrics with phishing as positive; undefined ratios are reported as zero."""


def binary_metrics(actual: list[bool], predicted: list[bool]) -> dict:
    if len(actual) != len(predicted):
        raise ValueError("Actual and predicted labels must have equal lengths.")
    if any(type(value) not in (bool, int) or value not in (0, 1) for value in (*actual, *predicted)):
        raise ValueError("Metrics require boolean or binary integer labels.")
    tp = sum(bool(a) and bool(p) for a, p in zip(actual, predicted))
    fp = sum(not a and bool(p) for a, p in zip(actual, predicted))
    tn = sum(not a and not p for a, p in zip(actual, predicted))
    fn = sum(bool(a) and not p for a, p in zip(actual, predicted))
    ratios = {
        "accuracy": (tp + tn, len(actual)), "precision": (tp, tp + fp),
        "recall": (tp, tp + fn), "f1": (2 * tp, 2 * tp + fp + fn),
        "specificity": (tn, tn + fp), "false_positive_rate": (fp, fp + tn),
    }
    return {
        "tp": tp, "fp": fp, "tn": tn, "fn": fn,
        **{name: numerator / denominator if denominator else 0.0
           for name, (numerator, denominator) in ratios.items()},
        "undefined_metrics": [name for name, (_, denominator) in ratios.items() if not denominator],
        "confusion_matrix": {
            "labels": ["legitimate", "phishing"], "rows": "actual", "columns": "predicted",
            "values": [[tn, fp], [fn, tp]],
        },
    }

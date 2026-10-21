"""Strict CSV loading and session splits. Audit works without ML dependencies."""

from collections import Counter, defaultdict
import csv
import hashlib
import json
import math
from pathlib import Path

LABELS = tuple("!abcdefghijklmnopqrstuvwxyz")
FEATURES = ("thumb_raw", "index_raw", "middle_raw", "ring_raw", "pinky_raw")
ROLES = ("train", "validation", "test")
OFFSET = (0.0,) * 5
SCALE = (1.0 / 4095,) * 5
DEFAULT_CONFIG = Path(__file__).with_name("config.json")


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def load_config(path=DEFAULT_CONFIG):
    path = Path(path).resolve()
    config = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(config, dict):
        raise ValueError("Config must be a JSON object.")
    config["data_dir"] = str((path.parent / config["data_dir"]).resolve())
    config["output_dir"] = str((path.parent / config["output_dir"]).resolve())
    for key in ("seed", "hidden_units", "batch_size", "max_epochs", "patience"):
        value = config[key]
        if type(value) is not int or value < (0 if key == "seed" else 1):
            raise ValueError(f"{key} must be an integer >= {0 if key == 'seed' else 1}.")
    for key in ("learning_rate", "l2", "confidence_threshold"):
        value = config[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{key} must be a finite number.")
    if config["learning_rate"] <= 0 or config["l2"] < 0:
        raise ValueError("learning_rate must be positive and l2 nonnegative.")
    if not 0 < config["confidence_threshold"] <= 1:
        raise ValueError("confidence_threshold must be in (0, 1].")
    if type(config["refit_all"]) is not bool:
        raise ValueError("refit_all must be true or false.")
    return config


def read_csv(path):
    """Return (label, five integer ADC values) tuples; fail on malformed rows."""
    path = Path(path)
    rows = []
    with path.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != ["Label", *FEATURES]:
            raise ValueError(f"{path}: expected columns Label,{','.join(FEATURES)}")
        for line, row in enumerate(reader, 2):
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f"{path}:{line}: wrong number of fields")
            label = row["Label"].strip()
            if label not in LABELS:
                raise ValueError(f"{path}:{line}: unsupported label {label!r}")
            try:
                values = tuple(int(row[name]) for name in FEATURES)
            except ValueError as error:
                raise ValueError(f"{path}:{line}: sensor values must be integers") from error
            if any(value < 0 or value > 4095 for value in values):
                raise ValueError(f"{path}:{line}: ADC values must be in 0..4095")
            rows.append((label, values))
    if not rows:
        raise ValueError(f"{path}: no data rows")
    return rows


def load_dataset(config):
    groups = {role: [] for role in ROLES}
    sources, warnings = [], []
    seen_paths, seen_hashes = set(), {}
    # Preserve rows (including duplicates), but identify exact leakage/conflicts.
    duplicate_keys = Counter()
    feature_roles, feature_labels = defaultdict(set), defaultdict(set)
    saturation = {name: {"zero": 0, "full_scale": 0} for name in FEATURES}
    for role in ROLES:
        filenames = config[f"{role}_files"]
        if not isinstance(filenames, list) or not filenames or any(not isinstance(x, str) for x in filenames):
            raise ValueError(f"{role}_files must be a nonempty list of filenames.")
        for filename in filenames:
            path = (Path(config["data_dir"]) / filename).resolve()
            if path in seen_paths:
                raise ValueError(f"CSV appears more than once/across splits: {path}")
            seen_paths.add(path)
            content = path.read_bytes()
            digest = hashlib.sha256(content).hexdigest()
            if digest in seen_hashes:
                raise ValueError(f"Duplicate CSV contents: {path} and {seen_hashes[digest]}")
            seen_hashes[digest] = str(path)
            rows = read_csv(path)
            counts = Counter(label for label, _ in rows)
            sources.append({"path": str(path), "role": role, "sha256": digest,
                            "rows": len(rows), "class_counts": dict(sorted(counts.items()))})
            for label, values in rows:
                groups[role].append((label, values))
                duplicate_keys[(label, values)] += 1
                feature_roles[values].add(role)
                feature_labels[values].add(label)
                for name, value in zip(FEATURES, values):
                    saturation[name]["zero"] += value == 0
                    saturation[name]["full_scale"] += value == 4095
    split_counts = {}
    for role, rows in groups.items():
        counts = Counter(label for label, _ in rows)
        missing = sorted(set(LABELS) - set(counts))
        if missing:
            raise ValueError(f"{role} split is missing classes: {missing}")
        split_counts[role] = {label: counts[label] for label in LABELS}
    duplicates = sum(count - 1 for count in duplicate_keys.values())
    overlaps = sum(len(roles) > 1 for roles in feature_roles.values())
    conflicts = sum(len(labels) > 1 for labels in feature_labels.values())
    if duplicates:
        warnings.append(f"{duplicates} repeated labelled rows retained; no random row split is used.")
    if overlaps:
        warnings.append(f"{overlaps} identical sensor vectors occur across splits; see data_audit.json.")
    if conflicts:
        warnings.append(f"{conflicts} identical sensor vectors have conflicting labels.")
    if any(counts["full_scale"] or counts["zero"] for counts in saturation.values()):
        warnings.append("ADC boundary readings found; inspect saturation_by_feature for possible clipping.")
    warnings.append("Few independent captures per class: treat held-out results as a prototype estimate.")
    audit = {
        "rows": sum(len(rows) for rows in groups.values()), "features": list(FEATURES),
        "labels": list(LABELS), "sources": sources, "split_class_counts": split_counts,
        "duplicate_labelled_rows": duplicates, "cross_split_identical_vectors": overlaps,
        "conflicting_label_vectors": conflicts, "saturation_by_feature": saturation,
        "warnings": warnings,
    }
    return groups, audit

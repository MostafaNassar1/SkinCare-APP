import json
import pickle
import sys
from pathlib import Path

import numpy as np
import pytest

from skincare_ml import detection_metrics as metrics
from skincare_ml.detector_report import describe, summarise
from skincare_ml.grading import agreement, fit_limits, grade_from_count

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


# ---------- grading ----------


def test_grade_from_count_uses_the_two_limits():
    assert [grade_from_count(c, (5, 20)) for c in (0, 5, 6, 20, 21)] == [
        "mild", "mild", "moderate", "moderate", "severe"]  # fmt: skip


def test_fitted_limits_agree_with_the_experts_and_very_severe_counts_as_severe():
    counts = [2, 4, 10, 12, 30, 40]
    grades = ["mild", "mild", "moderate", "moderate", "severe", "very_severe"]

    limits = fit_limits(counts, grades)

    assert limits == (4, 12)  # the lowest limits among the perfect ones
    result = agreement(counts, grades, limits)
    assert result["agreement"] == 1.0 and result["expert_to_ours"]["severe"]["severe"] == 2


# ---------- dot on the pimple ----------


def test_centre_rule_accepts_a_shifted_box_whose_dot_is_on_the_pimple():
    truth = np.array([[0, 0, 16, 16]], dtype=float)
    shifted = np.array([[6, 6, 22, 22]], dtype=float)  # IoU ~0.24: a miss for the box rule

    assert metrics.match(shifted, np.array([0.9]), truth)[0].tolist() == [False]
    assert metrics.match_centre(shifted, np.array([0.9]), truth)[0].tolist() == [True]


def test_centre_rule_finds_each_pimple_once():
    truth = np.array([[0, 0, 20, 20]], dtype=float)
    pred = np.array([[5, 5, 15, 15], [4, 4, 14, 14]], dtype=float)

    hits, found = metrics.match_centre(pred, np.array([0.5, 0.9]), truth)

    assert hits.tolist() == [False, True] and found.tolist() == [-1, 0]


def _rows():
    rows = []
    for n, (grade, hits) in enumerate([("mild", 2), ("moderate", 8), ("severe", 25)]):
        truth = np.array([[i * 30, 0, i * 30 + 20, 20] for i in range(hits)], dtype=float)
        pred = np.vstack([truth, [[5000, 5000, 5020, 5020]]])  # every pimple + one false dot
        rows.append({"file": f"p{n}", "pred": pred, "scores": np.r_[np.full(hits, 0.5), 0.15],
                     "truth": truth, "grade": grade})  # fmt: skip
    return rows


def test_summary_at_frozen_cutoffs():
    rows = _rows()
    grades = {r["file"]: r["grade"] for r in rows}

    summary = summarise(rows, count_cutoff=0.13, display_cutoff=0.2, limits=(5, 20),
                        grades_by_file=grades, rounds=20)  # fmt: skip

    assert summary["display_centre"]["precision"] == 1.0  # the false dots are below 0.2
    assert summary["count_box"]["precision"] == pytest.approx(35 / 38, abs=1e-4)
    assert summary["count_centre"]["recall"] == 1.0
    assert summary["grade"]["agreement"] == 1.0 and len(summary["grade"]["ranges_95"]) == 2
    assert "grade agreement 100%" in describe("test", summary)


# ---------- freezing and the one-time test ----------


@pytest.fixture
def scripts(monkeypatch, tmp_path):
    monkeypatch.setenv("SKINCARE_DATA_DIR", str(tmp_path))
    monkeypatch.syspath_prepend(str(SCRIPTS))
    for name in ("final_test", "freeze_detector_settings", "compare_models"):
        sys.modules.pop(name, None)
    import final_test
    import freeze_detector_settings

    return freeze_detector_settings, final_test


def _freeze(freeze, tmp_path):
    manifest = tmp_path / "prepared" / "manifests"
    manifest.mkdir(parents=True)
    rows = _rows()
    images = [{"file": r["file"], "expert_grade": r["grade"]} for r in rows]
    (manifest / "pimples.json").write_text(json.dumps({"images": images}), encoding="utf-8")
    predictions = tmp_path / "predictions.pkl"
    with open(predictions, "wb") as file:
        pickle.dump({"rows": {"original": {"C": rows}}}, file)
    weights = tmp_path / "best.pt"
    weights.write_bytes(b"weights")
    return freeze.main(["--predictions", str(predictions), "--model-name", "C",
                        "--weights", str(weights)])  # fmt: skip


def test_freeze_writes_the_settings_once(scripts, tmp_path):
    freeze, _ = scripts

    assert _freeze(freeze, tmp_path) == 0

    settings = json.loads((tmp_path / "models" / freeze.SETTINGS).read_text(encoding="utf-8"))
    assert (settings["count_cutoff"], settings["display_cutoff"]) == (0.13, 0.2)
    assert settings["model"]["sha256"] == freeze.sha256(tmp_path / "models" / freeze.WEIGHTS)
    assert settings["final_test_phone_factors"] == [0.6]
    with pytest.raises(SystemExit):  # never overwritten
        freeze.main(["--predictions", "x", "--model-name", "C", "--weights", "y"])


def test_final_test_needs_frozen_settings_the_same_model_and_runs_once(scripts, tmp_path):
    freeze, final = scripts
    with pytest.raises(SystemExit):  # nothing frozen yet
        final.main([])
    _freeze(freeze, tmp_path)

    (tmp_path / "models" / freeze.WEIGHTS).write_bytes(b"changed weights")
    with pytest.raises(SystemExit):  # not the frozen model
        final.main([])
    (tmp_path / "models" / freeze.WEIGHTS).write_bytes(b"weights")
    done = tmp_path / "prepared" / "yolo_evaluations"
    done.mkdir(parents=True)
    (done / "final_test_20261121_170000.json").write_text("{}", encoding="utf-8")
    with pytest.raises(SystemExit):  # already run: the result stands
        final.main([])


# ---------- ONNX check ----------


def test_onnx_check_compares_the_counted_pimples(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    sys.modules.pop("export_onnx", None)
    import export_onnx
    from skincare_ml.tiled_predict import Detections

    a = Detections(np.array([[0, 0, 20, 20], [50, 50, 70, 70], [90, 90, 99, 99]], np.float32),
                   np.array([0.5, 0.3, 0.05], np.float32))  # fmt: skip
    same = Detections(np.array([[0, 0, 20, 20.5], [50, 50, 70, 70]], np.float32),
                      np.array([0.51, 0.3], np.float32))  # fmt: skip
    missing = Detections(np.array([[0, 0, 20, 20]], np.float32), np.array([0.5], np.float32))

    result = export_onnx.same_detections(a, same, cutoff=0.13)
    assert (result["matched"], result["unmatched"]) == (2, 0)  # the 0.05 box is not counted
    assert result["largest_score_difference"] == pytest.approx(0.01, abs=1e-4)
    assert export_onnx.same_detections(a, missing, cutoff=0.13)["unmatched"] == 1


# ---------- type model final test ----------


def test_type_model_test_refuses_changed_labels_and_a_second_run(monkeypatch, tmp_path):
    monkeypatch.setenv("SKINCARE_DATA_DIR", str(tmp_path))
    monkeypatch.syspath_prepend(str(SCRIPTS))
    sys.modules.pop("test_type_model", None)
    import test_type_model

    folder = tmp_path / "prepared" / "lesion_types"
    folder.mkdir(parents=True)
    labels = {"p.jpg#1": "whitehead"}
    (folder / "test_labels_frozen.json").write_text(json.dumps(
        {"labels": labels, "sha256": "changed"}), encoding="utf-8")  # fmt: skip
    with pytest.raises(ValueError):
        test_type_model.test_items(folder)
    (folder / test_type_model.RESULT).write_text("{}", encoding="utf-8")
    with pytest.raises(SystemExit):
        test_type_model.main([])


def test_type_model_balanced_ranges_of_a_perfect_model():
    sys.path.insert(0, str(SCRIPTS))
    import test_type_model

    labels = np.array([0, 0, 1, 1, 2, 2])
    assert test_type_model.balanced_ranges(labels, labels, rounds=50) == [1.0, 1.0]

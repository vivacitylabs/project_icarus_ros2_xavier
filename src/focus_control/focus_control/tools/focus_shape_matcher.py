import json
import numpy as np
from scipy.signal import correlate
import os

NORMALIZED_JSON = os.path.expanduser("~/focus_logs/calibration_logs/master/normalized_calibrations.json")

def load_normalized_json():
    """
    Load normalized focus profiles from structured JSON.
    Returns two dicts: 
    - profiles[(lens, dist, run_id)] -> {offset, score}
    - peak_scores[(lens, dist)] -> float
    """
    with open(NORMALIZED_JSON, "r") as f:
        data = json.load(f)

    profiles = {}
    for key, values in data["normalized_profiles"].items():
        lens, dist, run_id = key.split("__")
        dist = float(dist)
        profiles[(lens, dist, run_id)] = {
            "offset": np.array(values["offset_from_peak"]),
            "scores": np.array(values["score"])
        }

    peak_scores = {
        (lens, float(dist)): score
        for key, score in data["peak_scores"].items()
        for lens, dist in [key.split("__")]
    }

    return profiles, peak_scores


def match_to_peak_profile(live_scores, lens_spec, distance):
    profiles, _ = load_normalized_json()
    live_scores = np.array(live_scores)
    best_match = None
    best_quality = -np.inf
    best_offset = 0

    for (lens, dist, run_id), profile in profiles.items():
        if lens != lens_spec or dist != distance:
            continue

        scores = profile["scores"]
        scores = (scores - np.mean(scores)) / (np.std(scores) + 1e-8)
        live_norm = (live_scores - np.mean(live_scores)) / (np.std(live_scores) + 1e-8)

        if len(scores) < len(live_scores):
            continue

        correlation = correlate(scores, live_norm, mode='valid')
        if len(correlation) == 0:
            continue

        max_corr = np.max(correlation)
        if max_corr > best_quality:
            best_quality = max_corr
            best_offset = profile["offset"][np.argmax(correlation)]
            best_match = run_id

    if best_match is None:
        return None

    return {
        "estimated_offset": int(best_offset),
        "match_quality": float(best_quality / len(live_scores)),
        "matched_run_id": best_match
    }


def match_focus_entry_zone(live_scores, lens_spec, distance, pre_peak_window=(-30, -5)):
    profiles, _ = load_normalized_json()
    patterns = []

    for (lens, dist, run_id), profile in profiles.items():
        if lens != lens_spec or dist != distance:
            continue

        offset = profile["offset"]
        scores = profile["scores"]
        mask = (offset >= pre_peak_window[0]) & (offset <= pre_peak_window[1])
        zone_scores = scores[mask]

        if len(zone_scores) > 5:
            patterns.append(zone_scores)

    if not patterns:
        return False

    min_len = min(len(p) for p in patterns)
    mean_pattern = np.mean([p[-min_len:] for p in patterns], axis=0)

    live_recent = np.array(live_scores[-min_len:])
    mean_pattern = (mean_pattern - np.mean(mean_pattern)) / (np.std(mean_pattern) + 1e-8)
    live_recent = (live_recent - np.mean(live_recent)) / (np.std(live_recent) + 1e-8)

    corr = np.correlate(mean_pattern, live_recent, mode='valid')
    return corr[0] / len(mean_pattern) > 0.8


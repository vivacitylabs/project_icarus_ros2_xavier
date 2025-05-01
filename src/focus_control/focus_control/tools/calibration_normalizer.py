import pandas as pd
import os
import json

# Paths
INPUT_CSV = os.path.expanduser("~/focus_logs/calibration_logs/master/master_calibrations.csv")
OUTPUT_JSON = os.path.expanduser("~/focus_logs/calibration_logs/master/normalized_calibrations.json")

# CSV column headers
headers = [
    "LensSpec", "DistanceM", "RunID", "Step", "Score", "Timestamp", "FrameID", "Valid"
]

# Load raw calibration data
df = pd.read_csv(INPUT_CSV, names=headers)

# Output structure
normalized_profiles = {}
peak_scores = {}

# Normalize groups
group_cols = ["LensSpec", "DistanceM", "RunID"]
for (lens, dist, run), group in df.groupby(group_cols):
    group = group.sort_values("Step")
    peak = group.loc[group["Score"].idxmax()]
    peak_step = peak["Step"]
    peak_score = peak["Score"]

    group["offset_from_peak"] = group["Step"] - peak_step

    key = f"{lens}__{dist}__{run}"
    normalized_profiles[key] = {
        "offset_from_peak": group["offset_from_peak"].tolist(),
        "score": group["Score"].tolist()
    }

    summary_key = f"{lens}__{dist}"
    if summary_key not in peak_scores or peak_score > peak_scores[summary_key]:
        peak_scores[summary_key] = peak_score

# Save to JSON
output = {
    "normalized_profiles": normalized_profiles,
    "peak_scores": peak_scores
}

with open(OUTPUT_JSON, "w") as f:
    json.dump(output, f, indent=2)

print(f"✅ Normalized data saved to: {OUTPUT_JSON}")


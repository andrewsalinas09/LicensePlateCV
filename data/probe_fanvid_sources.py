"""Probe availability of FANVID LP source videos without downloading them."""

import csv

import pandas as pd
from yt_dlp import YoutubeDL

df = pd.read_csv(r"data\FANVID_repo\data\dataset_lp.csv")
urls = df.drop_duplicates("You_Tube_URL")[["Video ID", "You_Tube_URL"]]

opts = {"quiet": True, "no_warnings": True, "skip_download": True, "geo_bypass": True}

results = []
for _, row in urls.iterrows():
    url = row["You_Tube_URL"]
    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        results.append((row["Video ID"], url, "OK", info.get("title", "")[:60]))
        print(f"OK      {url}")
    except Exception as e:
        msg = str(e).replace("\n", " ")[:160]
        results.append((row["Video ID"], url, "FAIL", msg))
        print(f"FAIL    {url}  {msg}")

with open(r"data\fanvid_source_probe.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["video_id", "url", "status", "detail"])
    w.writerows(results)

ok = sum(1 for r in results if r[2] == "OK")
print(f"\n{ok}/{len(results)} sources available")

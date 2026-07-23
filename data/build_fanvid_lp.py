"""Build the FANVID license-plate dataset locally.

Adapted from data/FANVID_repo/assets/download_script_lp.py: same output layout
(<split>/<plate_text>/<clip_id>/{hr,lr}/#####.png) and same HR->LR resize chain,
but grouped by source video (download once, extract all clips, delete video),
restricted to sources confirmed available by probe_fanvid_sources.py, and
resume-safe (clips with a complete frame set are skipped).
"""

import csv
import os
import random
import time

import cv2
import pandas as pd
from yt_dlp import YoutubeDL

ROOT = os.path.dirname(os.path.abspath(__file__))
DATASET_DIR = os.path.join(ROOT, "FANVID_LP")
VIDEO_TMP = os.path.join(ROOT, "fanvid_videos_tmp")
MISSING_LOG = os.path.join(ROOT, "fanvid_build_missing.csv")
FPS_LOG = os.path.join(ROOT, "fanvid_build_fps_mismatch.csv")

os.makedirs(DATASET_DIR, exist_ok=True)
os.makedirs(VIDEO_TMP, exist_ok=True)
for log_file, header in [
    (MISSING_LOG, ["Clip ID", "Name", "You_Tube_URL", "Reason"]),
    (FPS_LOG, ["Clip ID", "Name", "Expected FPS", "Actual FPS"]),
]:
    if not os.path.exists(log_file):
        with open(log_file, "w", newline="") as f:
            csv.writer(f).writerow(header)


def log_row(path, row):
    with open(path, "a", newline="") as f:
        csv.writer(f).writerow(row)


YDL_OPTS = {
    # Video-only (no +bestaudio as in the original script): frames are all we
    # need, and merging separate audio/video streams would require ffmpeg.
    "format": "bestvideo[ext=mp4][vcodec!*=av01]/best[ext=mp4]",
    "outtmpl": os.path.join(VIDEO_TMP, "%(id)s.%(ext)s"),
    "quiet": True,
    "no_warnings": True,
    "concurrent_fragment_downloads": 5,
    "geo_bypass": True,
    "sleep_interval": 3,
}


def download_video(url):
    try:
        with YoutubeDL(YDL_OPTS) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
        if os.path.exists(filename) and os.path.getsize(filename) > 1024:
            return filename
    except Exception as e:
        print(f"[!] Download failed {url}: {e}", flush=True)
    return None


def clip_complete(lr_dir, start_frame, end_frame):
    if not os.path.isdir(lr_dir):
        return False
    expected = end_frame - start_frame + 1
    return expected > 0 and len([f for f in os.listdir(lr_dir) if f.endswith(".png")]) >= expected


def extract_clip(video_path, row):
    start_frame = int(row["Start frame"]) - 1
    end_frame = int(row["End frame"]) - 1
    hr_size = (int(row["Target HR Width"]), int(row["Target HR Height"]))
    lr_size = (int(row["Target LR Width"]), int(row["Target LR Height"]))
    clip_dir = os.path.join(
        DATASET_DIR, str(row["Split"]).lower(), str(row["Name"]), str(row["Clip ID"])
    )
    hr_dir = os.path.join(clip_dir, "hr")
    lr_dir = os.path.join(clip_dir, "lr")

    if end_frame < start_frame:
        log_row(MISSING_LOG, [row["Clip ID"], row["Name"], row["You_Tube_URL"], "Negative duration"])
        return
    if clip_complete(lr_dir, start_frame, end_frame):
        return
    os.makedirs(hr_dir, exist_ok=True)
    os.makedirs(lr_dir, exist_ok=True)

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        log_row(MISSING_LOG, [row["Clip ID"], row["Name"], row["You_Tube_URL"], "Open failed"])
        return
    fps = cap.get(cv2.CAP_PROP_FPS)
    if abs(fps - float(row["FPS"])) > 0.5:
        log_row(FPS_LOG, [row["Clip ID"], row["Name"], row["FPS"], fps])

    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    for idx in range(start_frame, end_frame + 1):
        ret, frame = cap.read()
        if not ret:
            log_row(MISSING_LOG, [row["Clip ID"], row["Name"], row["You_Tube_URL"],
                                  f"Frame read failed at {idx}"])
            break
        hr = cv2.resize(frame, hr_size, interpolation=cv2.INTER_CUBIC)
        lr = cv2.resize(hr, lr_size, interpolation=cv2.INTER_CUBIC)
        cv2.imwrite(os.path.join(hr_dir, f"{idx:05d}.png"), hr)
        cv2.imwrite(os.path.join(lr_dir, f"{idx:05d}.png"), lr)
    cap.release()


def main():
    df = pd.read_csv(os.path.join(ROOT, "FANVID_repo", "data", "dataset_lp.csv"))
    probe = pd.read_csv(os.path.join(ROOT, "fanvid_source_probe.csv"))
    ok_urls = set(probe[probe.status == "OK"].url)

    for url in df[df.You_Tube_URL.isin(ok_urls)].You_Tube_URL.unique():
        clips = df[df.You_Tube_URL == url]
        pending = [
            row for _, row in clips.iterrows()
            if not clip_complete(
                os.path.join(DATASET_DIR, str(row["Split"]).lower(), str(row["Name"]),
                             str(row["Clip ID"]), "lr"),
                int(row["Start frame"]) - 1, int(row["End frame"]) - 1,
            )
            and int(row["End frame"]) >= int(row["Start frame"])
        ]
        if not pending:
            print(f"[skip] {url} — all {len(clips)} clips present", flush=True)
            continue

        print(f"[dl]   {url} — {len(pending)} clips to extract", flush=True)
        video = download_video(url)
        if not video:
            for row in pending:
                log_row(MISSING_LOG, [row["Clip ID"], row["Name"], url, "Download Failed"])
            continue
        for row in pending:
            extract_clip(video, row)
        os.remove(video)
        time.sleep(8 + random.uniform(0, 5))

    n_clips = sum(1 for _, _, files in os.walk(DATASET_DIR) if files)
    print(f"[done] directories with files: {n_clips}", flush=True)


if __name__ == "__main__":
    main()

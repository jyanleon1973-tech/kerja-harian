"""精度検証ツール。
1) 検証用フレームの抽出:  python tools/eval.py extract VIDEO OUT_DIR --every 1.0
   → OUT_DIR/frames/*.jpg と OUT_DIR/labels_template.json（人が正解座標を入れるひな形）
2) 正解と推定の比較:      python tools/eval.py compare LABELS.json RESULTS.json [--pck 0.2]
   RESULTS.json は API の results（include_frames=true）または段階出力。
   評価項目: 関節位置誤差（身長比）、PCK@α（胴体長基準）、左右識別正解率、板検出の正解率（画像角度差 ≤10°）、
            ターン方向正解率、切り替えコマ誤差、検出不能率、時系列の安定性（隣接コマ差の中央値）。
正解データ形式（labels.json）:
{"video": "...", "fps_hint": 30, "frames": [{"t": 1.0, "kp": {"11": [x,y], "12": [x,y], ...}, "ski": {"L": {"a": [x,y], "b": [x,y]}, "R": ...},
  "turn": -1|0|1|null, "switch": true|false, "view": "side"}]}  座標は正規化（0-1）。欠けている関節は書かない。"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

JOINTS = {"11": "l_shoulder", "12": "r_shoulder", "13": "l_elbow", "14": "r_elbow", "15": "l_wrist", "16": "r_wrist", "23": "l_hip", "24": "r_hip",
          "25": "l_knee", "26": "r_knee", "27": "l_ankle", "28": "r_ankle", "29": "l_heel", "30": "r_heel", "31": "l_toe", "32": "r_toe"}
PAIRS = [("11", "12"), ("13", "14"), ("15", "16"), ("23", "24"), ("25", "26"), ("27", "28"), ("29", "30"), ("31", "32")]


def cmd_extract(a):
    import cv2
    out = Path(a.out); (out / "frames").mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(a.video); fps = cap.get(cv2.CAP_PROP_FPS) or 30
    template = {"video": Path(a.video).name, "fps_hint": fps, "frames": []}
    next_t = 0.0; n = 0
    while True:
        ok = cap.grab()
        if not ok:
            break
        t = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000
        if t + 1e-6 >= next_t:
            ok, fr = cap.retrieve()
            if not ok:
                break
            name = f"f{n:04d}_{t:.3f}.jpg"; cv2.imwrite(str(out / "frames" / name), fr)
            template["frames"].append({"t": round(t, 3), "image": name, "kp": {k: None for k in JOINTS}, "ski": {"L": None, "R": None}, "turn": None, "switch": False, "view": None})
            n += 1; next_t += a.every
    (out / "labels_template.json").write_text(json.dumps(template, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{n} フレームを {out} に保存。labels_template.json に正解座標を記入してください（正規化座標 0-1）。")


def _nearest(frames, t):
    return min(frames, key=lambda f: abs(f["t"] - t)) if frames else None


def cmd_compare(a):
    gt = json.loads(Path(a.labels).read_text(encoding="utf-8"))
    res = json.loads(Path(a.results).read_text(encoding="utf-8"))
    frames = res["frames"] if "frames" in res else res
    W, H = res.get("video", {}).get("width", 1), res.get("video", {}).get("height", 1)
    errs, pck_hits, pck_n, lr_ok, lr_n, miss, n_gt = [], 0, 0, 0, 0, 0, 0
    ski_ok = ski_n = 0; turn_ok = turn_n = 0; sw_err = []
    for g in gt["frames"]:
        n_gt += 1
        p = _nearest(frames, g["t"])
        if not p or abs(p["t"] - g["t"]) > 1.0 / max(1, gt.get("fps_hint", 30)) * 1.5 or not p.get("lm"):
            miss += 1; continue
        kp = {k: v for k, v in (g.get("kp") or {}).items() if v}
        if "23" in kp and "24" in kp and "11" in kp and "12" in kp:
            torso = math.dist([(kp["11"][0] + kp["12"][0]) / 2 * W, (kp["11"][1] + kp["12"][1]) / 2 * H], [(kp["23"][0] + kp["24"][0]) / 2 * W, (kp["23"][1] + kp["24"][1]) / 2 * H])
        else:
            torso = None
        for k, (gx, gy) in kp.items():
            j = int(k); px, py = p["lm"][j][0], p["lm"][j][1]
            e = math.dist([gx * W, gy * H], [px * W, py * H]); errs.append(e / torso if torso else e)
            if torso:
                pck_n += 1; pck_hits += 1 if e <= a.pck * torso else 0
        for l, r in PAIRS:
            if l in kp and r in kp:
                lr_n += 1
                gl, gr = kp[l], kp[r]; pl, pr = p["lm"][int(l)], p["lm"][int(r)]
                same = math.dist(gl, pl) + math.dist(gr, pr) <= math.dist(gl, pr) + math.dist(gr, pl)
                lr_ok += 1 if same else 0
        for side in ("L", "R"):
            gs = (g.get("ski") or {}).get(side)
            if gs:
                ski_n += 1
                ps = (p.get("ski") or {}).get(side)
                if ps and ps.get("conf", 0) >= 0.55:
                    ga = math.atan2((gs["b"][1] - gs["a"][1]) * H, (gs["b"][0] - gs["a"][0]) * W)
                    d = abs((ga - ps["ang"]) % math.pi); d = min(d, math.pi - d)
                    ski_ok += 1 if d <= math.radians(10) else 0
        if g.get("turn") is not None:
            turn_n += 1; turn_ok += 1 if p.get("turn") == g["turn"] else 0
    for g in gt["frames"]:
        if g.get("switch"):
            sws = res.get("switches") or []
            if sws:
                sw_err.append(min(abs(s["t"] - g["t"]) for s in sws))
    # 時系列安定性: 検出コマの隣接差（腰中点、身長比）の中央値
    diffs = []
    prev = None
    for f in frames:
        if f.get("lm") and f.get("src") == "det":
            hx, hy = (f["lm"][23][0] + f["lm"][24][0]) / 2, (f["lm"][23][1] + f["lm"][24][1]) / 2
            if prev:
                diffs.append(math.hypot(hx - prev[0], hy - prev[1]))
            prev = (hx, hy)
        else:
            prev = None
    med = sorted(diffs)[len(diffs) // 2] if diffs else None
    report = {
        "frames_gt": n_gt, "missing_rate": round(miss / max(1, n_gt), 3),
        "joint_error_torso_ratio_mean": round(sum(errs) / len(errs), 4) if errs else None,
        "joint_error_torso_ratio_median": round(sorted(errs)[len(errs) // 2], 4) if errs else None,
        f"PCK@{a.pck}": round(pck_hits / pck_n, 3) if pck_n else None,
        "left_right_accuracy": round(lr_ok / lr_n, 3) if lr_n else None,
        "ski_angle_accuracy_10deg": round(ski_ok / ski_n, 3) if ski_n else None, "ski_gt_count": ski_n,
        "turn_direction_accuracy": round(turn_ok / turn_n, 3) if turn_n else None,
        "switch_frame_error_s_mean": round(sum(sw_err) / len(sw_err), 3) if sw_err else None,
        "temporal_jitter_hip_median": round(med, 5) if med is not None else None,
        "model_versions": res.get("model_versions"), "pipeline_version": res.get("pipeline_version"),
    }
    print(json.dumps(report, ensure_ascii=False, indent=1))


def main():
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("extract"); e.add_argument("video"); e.add_argument("out"); e.add_argument("--every", type=float, default=1.0); e.set_defaults(fn=cmd_extract)
    c = sub.add_parser("compare"); c.add_argument("labels"); c.add_argument("results"); c.add_argument("--pck", type=float, default=0.2); c.set_defaults(fn=cmd_compare)
    a = ap.parse_args(); a.fn(a)


if __name__ == "__main__":
    main()

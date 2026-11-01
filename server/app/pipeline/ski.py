"""板の検出（古典的画像処理、信頼度付き）。足首の位置からは板を作らない。
足元の小窓で、足元を通る細長い線の向きをエッジ方向ヒストグラムで求め、線に沿ったエッジの裏付け率と
雪より暗い画素の連続長で検証する。裏付けが弱ければ未検出（conf が閾値未満）。
専用の学習済み検出器（YOLO/キーポイント）ができたら、この関数と同じ出力形式で差し替える。
出力: {"L": {...}|None, "R": {...}|None, "shared": bool}
  各側: {"ang": 線の角度 rad（画像座標、0=右向き）, "conf": 0-1, "fx","fy": 足元中心 px, "tip","tail": 中心から両側へ伸びる長さ px, "source": "edge"}"""
from __future__ import annotations

import math
from typing import Any

import cv2
import numpy as np

SKI_MIN_CONF = 0.55


def _detect_side(bgr: np.ndarray, kp, side: int, vw: int, vh: int, bh: float) -> dict[str, Any] | None:
    ank, heel, toe = kp[27 + side], kp[29 + side], kp[31 + side]
    if ank[2] < 0.4 or heel[2] < 0.3:
        return None
    S = max(48.0, min(520.0, bh * 0.75))
    fx, fy = (heel[0] + toe[0]) / 2 * vw, (heel[1] + toe[1]) / 2 * vh
    x0, y0 = fx - S / 2, fy - S / 2 + S * 0.12
    N = 128
    # 窓を切り出し（画面外は黒で埋める）
    M = np.float32([[N / S, 0, -x0 * N / S], [0, N / S, -y0 * N / S]])
    win = cv2.warpAffine(bgr, M, (N, N), flags=cv2.INTER_AREA, borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0))
    g = cv2.cvtColor(win, cv2.COLOR_BGR2GRAY).astype(np.float32)
    gx = cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3); gy = cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3)
    mag = np.hypot(gx, gy)
    ank_y = (ank[1] * vh - y0) / S * N; cxw = (fx - x0) / S * N; cyw = (fy - y0) / S * N
    ys, xs = np.mgrid[0:N, 0:N]
    th = (np.arctan2(gy, gx) + math.pi / 2) % math.pi  # 線の向き
    dist = np.abs((xs - cxw) * np.sin(th) - (ys - cyw) * np.cos(th))
    sel = (mag >= 60) & (ys >= ank_y - N * 0.05) & (dist <= N * 0.1)
    sel[0, :] = sel[-1, :] = sel[:, 0] = sel[:, -1] = False
    total = float(mag[sel].sum())
    if total < 400:
        return None
    bins = 36
    b = th[sel] / math.pi * bins; b0 = np.floor(b).astype(int) % bins; b1 = (b0 + 1) % bins; fr = b - np.floor(b)
    hist = np.bincount(b0, weights=mag[sel] * (1 - fr), minlength=bins) + np.bincount(b1, weights=mag[sel] * fr, minlength=bins)
    sm = (np.roll(hist, 1) + 2 * hist + np.roll(hist, -1)) / 4
    pk = int(sm.argmax()); l, c, r = sm[(pk - 1) % bins], sm[pk], sm[(pk + 1) % bins]
    den = l - 2 * c + r; off = (l - r) / (2 * den) if den else 0.0
    ang = (pk + off) / bins * math.pi
    peak_share = float((l + c + r) / total)
    # 線に沿った裏付け
    dx, dy = math.cos(ang), math.sin(ang); nx, ny = -dy, dx
    band = max(2, int(N * 0.06))
    support = np.zeros(N, dtype=bool); dark = np.full(N, 255.0)
    for t in range(-N // 2, N // 2):
        ok = False; dsum = 0.0; dn = 0
        for s in range(-band, band + 1):
            x = int(round(cxw + dx * t + nx * s)); y = int(round(cyw + dy * t + ny * s))
            if x < 1 or y < 1 or x >= N - 1 or y >= N - 1:
                continue
            dsum += g[y, x]; dn += 1
            if mag[y, x] > 60:
                dd = abs(((th[y, x] - ang) % math.pi)); dd = min(dd, math.pi - dd)
                if dd < 0.26:
                    ok = True
        support[t + N // 2] = ok; dark[t + N // 2] = dsum / dn if dn else 255.0
    snow = float(np.sort(dark)[int(len(dark) * 0.85)])

    def run(direction: int) -> int:
        last = 0; gap = 0
        for t in range(3, N // 2 - 1):
            k = N // 2 + direction * t
            good = support[k] or dark[k] < snow - 40
            if good:
                last = t; gap = 0
            else:
                gap += 1
                if gap > N * 0.05:
                    break
        return last

    r1, r2 = run(1), run(-1)
    idx = [t for t in range(N // 2 - r2, N // 2 + r1 + 1) if abs(t - N // 2) >= N * 0.04 and 0 <= t < N]
    sup_frac = float(support[idx].mean()) if idx else 0.0
    len_score = min(1.0, (r1 + r2) / (N * 0.5))
    conf = 0.35 * min(1.0, peak_share / 0.4) + 0.4 * sup_frac + 0.25 * len_score
    if min(r1, r2) < N * 0.1:
        conf *= 0.5
    conf = max(0.0, min(1.0, conf))
    return {"ang": float(ang), "conf": round(conf, 3), "fx": float(fx), "fy": float(fy), "tip": float(r1 * S / N), "tail": float(r2 * S / N), "S": float(S), "source": "edge"}


def detect_skis(bgr: np.ndarray, kp, vw: int, vh: int) -> dict[str, Any] | None:
    pts = [(p[0], p[1]) for p in kp if p[2] >= 0.3]
    if not pts:
        return None
    bh = (max(y for _, y in pts) - min(y for _, y in pts)) * vh
    if bh < 40:
        return None
    L = _detect_side(bgr, kp, 0, vw, vh, bh); R = _detect_side(bgr, kp, 1, vw, vh, bh)
    shared = False
    if L and R:
        dd = abs(L["ang"] - R["ang"]) % math.pi; dd = min(dd, math.pi - dd)
        dist = abs((R["fx"] - L["fx"]) * math.sin(L["ang"]) - (R["fy"] - L["fy"]) * math.cos(L["ang"]))
        if dd < 0.07 and dist < bh * 0.04:
            shared = True
    return {"L": L, "R": R, "shared": shared}

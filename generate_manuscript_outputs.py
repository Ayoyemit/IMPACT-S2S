#!/usr/bin/env python3
"""
Generate Frontiers Technology & Code manuscript figures, tables, and PH-team data.

Usage:
    python generate_manuscript_outputs.py algorithm_logs.json
    DATABASE_URL=postgresql://... python generate_manuscript_outputs.py algorithm_logs.json

Outputs land in manuscript_outputs/. DB-dependent files are skipped when DATABASE_URL
is unset.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
import numpy as np
import pandas as pd

# Reuse production BT ranking code
from algorithm import BradleyTerryMAP, get_bt_score

# ── Paths / style ─────────────────────────────────────────────────────────────

OUT_DIR = Path("manuscript_outputs")
LEVELS = ["Provider", "Organization", "System", "Client"]
LEVEL_COLORS = {
    "Provider": "#f472b6",
    "Organization": "#f59e0b",
    "System": "#10b981",
    "Client": "#3b82f6",
}
LEVEL_DISPLAY = {
    "Provider": "Provider",
    "Organization": "Organization",
    "System": "System",
    "Client": "Patient",  # UI label
}

DPI = 300
FIG_SINGLE = (8, 5)
FIG_MULTI = (10, 8)

plt.rcParams.update(
    {
        "font.family": "Arial",
        "font.size": 11,
        "axes.titlesize": 12,
        "axes.labelsize": 11,
        "xtick.labelsize": 10,
        "ytick.labelsize": 10,
        "legend.fontsize": 10,
        "axes.grid": False,
        "figure.dpi": DPI,
        "savefig.dpi": DPI,
        "savefig.bbox": "tight",
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    }
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def ensure_out():
    OUT_DIR.mkdir(parents=True, exist_ok=True)


def save_fig(fig, stem: str):
    ensure_out()
    pdf = OUT_DIR / f"{stem}.pdf"
    png = OUT_DIR / f"{stem}.png"
    fig.savefig(pdf, format="pdf")
    fig.savefig(png, format="png")
    plt.close(fig)
    return [pdf, png]


def save_csv(df: pd.DataFrame, name: str):
    ensure_out()
    path = OUT_DIR / name
    df.to_csv(path, index=False)
    return path


def parse_json_field(val):
    if val is None:
        return None
    if isinstance(val, dict):
        return {str(k): v for k, v in val.items()}
    if isinstance(val, str):
        try:
            obj = json.loads(val)
            if isinstance(obj, dict):
                return {str(k): v for k, v in obj.items()}
        except json.JSONDecodeError:
            return None
    return None


def load_logs(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("Algorithm logs JSON must be a list of log objects")
    # Normalize field names / types
    for row in data:
        row["map_strengths"] = parse_json_field(row.get("map_strengths"))
        row["exposure_counts"] = parse_json_field(row.get("exposure_counts"))
        row["uncertainty_weights"] = parse_json_field(row.get("uncertainty_weights"))
        if "level" not in row and "level_context" in row:
            row["level"] = row["level_context"]
        if "num_comparisons" not in row and "num_comparisons_used" in row:
            row["num_comparisons"] = row["num_comparisons_used"]
    data.sort(key=lambda r: r.get("timestamp") or "")
    return data


def normalize_db_url(url: str) -> str:
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql://", 1)
    return url


def get_engine():
    url = os.environ.get("DATABASE_URL")
    if not url:
        return None
    # Catch common paste mistakes (literal placeholder from docs)
    stripped = url.strip()
    if (
        stripped in {"postgresql://...", "postgres://...", "..."}
        or "://" not in stripped
        or stripped.endswith("://...")
        or "@..." in stripped
        or stripped.rstrip("/").endswith("...")
    ):
        raise SystemExit(
            "DATABASE_URL looks like a placeholder (e.g. postgresql://...).\n"
            "Paste the full Railway Postgres URL, for example:\n"
            "  DATABASE_URL='postgresql://user:pass@host:5432/railway' \\\n"
            "    python generate_manuscript_outputs.py algorithm_logs.json\n"
            "Get it from Railway → your Postgres service → Variables → DATABASE_URL\n"
            "(or Connect → public URL)."
        )
    from sqlalchemy import create_engine

    return create_engine(normalize_db_url(url))


def duration_seconds(started_at, ended_at, last_activity) -> float | None:
    if started_at is None:
        return None
    end = ended_at or last_activity
    if end is None:
        return None
    return (end - started_at).total_seconds()


def truncate(text: str, n: int = 80) -> str:
    text = (text or "").strip()
    return text if len(text) <= n else text[: n - 1] + "…"


# ── TABLE 1 ───────────────────────────────────────────────────────────────────

def make_table1():
    rows = [
        {
            "Variable": "SURVEY_MODE",
            "Default": "example",
            "Description": "example = 25 sample strategies + random pairs; production = CSV strategies + BT adaptive algorithm",
        },
        {
            "Variable": "DATABASE_URL",
            "Default": "sqlite:///wiki_survey.db",
            "Description": "SQLAlchemy database URI; postgres:// is auto-rewritten to postgresql://",
        },
        {
            "Variable": "ADMIN_CODE",
            "Default": "admin2026",
            "Description": "Access code for the admin portal login gate",
        },
        {
            "Variable": "SECRET_KEY",
            "Default": "(dev placeholder)",
            "Description": "Flask session secret; must be overridden in production",
        },
        {
            "Variable": "BT_SIGMA2",
            "Default": "1.0",
            "Description": "Gaussian prior variance for Bradley–Terry MAP (higher = less shrinkage)",
        },
        {
            "Variable": "BT_PROXY",
            "Default": "top_heavy",
            "Description": "Focal sampling proxy: exposure (Proxy A) or top_heavy (Proxy B)",
        },
        {
            "Variable": "STRATEGIES_CSV",
            "Default": "data/Strategies.csv",
            "Description": "Path to production strategy CSV (used when SURVEY_MODE=production)",
        },
    ]
    df = pd.DataFrame(rows)
    csv_path = save_csv(df, "table1_config_variables.csv")

    fig, ax = plt.subplots(figsize=(10, 4.5))
    ax.axis("off")
    table = ax.table(
        cellText=df.values.tolist(),
        colLabels=list(df.columns),
        loc="center",
        cellLoc="left",
        colLoc="left",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1.0, 1.6)
    for (r, c), cell in table.get_celld().items():
        if r == 0:
            cell.set_facecolor("#1f2937")
            cell.set_text_props(color="white", weight="bold")
        elif r % 2 == 0:
            cell.set_facecolor("#f3f4f6")
        cell.set_edgecolor("#d1d5db")
    ax.set_title("Table 1. Environment Variable Configuration", pad=12, weight="bold")
    fig.tight_layout()
    paths = save_fig(fig, "table1_config_variables")
    return [csv_path] + paths


# ── FIGURE 1: Architecture ────────────────────────────────────────────────────

def make_fig1():
    """
    Pipeline matching algorithm.py AdaptivePairSelector.select_pair:

      cold start (0 comparisons) → Random Pair ──(right dogleg)──┐
                                                                  ├→ Display Pair → Observe Outcome
      MAP Refit → Proxy → Sample Focal → Opponent ────────────────┘         │
            ↑                                                               ▼
            └──────────────────── Update Exposure ←─────────────────────────┘
    """
    from matplotlib.path import Path as MPath
    from matplotlib.patches import FancyArrowPatch

    fig, ax = plt.subplots(figsize=(10, 6.2))
    ax.set_xlim(0, 10.4)
    ax.set_ylim(0, 7.2)
    ax.axis("off")
    ax.set_title(
        "Figure 1. Adaptive Pair-Selection Pipeline",
        weight="bold",
        pad=10,
    )

    W, H = 1.55, 1.05
    specs = {
        "map": (0.35, 4.55, W, H, "MAP Refit\n(BT strengths)"),
        "proxy": (2.25, 4.55, W, H, "Proxy\nUncertainty"),
        "focal": (4.15, 4.55, W, H, "Sample\nFocal"),
        "opp": (6.05, 4.55, W, H, "Near-Tie\nOpponent"),
        "display": (7.95, 4.55, W, H, "Display Pair\n(L/R random)"),
        "outcome": (7.95, 2.55, W, H, "Observe\nOutcome"),
        "exposure": (4.15, 2.55, W, H, "Update\nExposure"),
        "cold": (0.35, 0.85, W, H, "Cold Start\n(no comparisons)"),
        "random": (2.25, 0.85, W, H, "Random\nPair"),
    }

    for key, (x, y, w, h, text) in specs.items():
        face = "#f3f4f6" if key in ("cold", "random") else "#f9fafb"
        edge = "#6b7280" if key in ("cold", "random") else "#374151"
        box = FancyBboxPatch(
            (x, y),
            w,
            h,
            boxstyle="round,pad=0.03,rounding_size=0.12",
            linewidth=1.2,
            edgecolor=edge,
            facecolor=face,
        )
        ax.add_patch(box)
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=9, color="#111827")

    def edge_mid(key, side):
        x, y, w, h, _ = specs[key]
        if side == "left":
            return (x, y + h / 2)
        if side == "right":
            return (x + w, y + h / 2)
        if side == "top":
            return (x + w / 2, y + h)
        if side == "bottom":
            return (x + w / 2, y)
        raise ValueError(side)

    def arrow(a_key, a_side, b_key, b_side, color="#374151"):
        x1, y1 = edge_mid(a_key, a_side)
        x2, y2 = edge_mid(b_key, b_side)
        ax.annotate(
            "",
            xy=(x2, y2),
            xytext=(x1, y1),
            arrowprops=dict(
                arrowstyle="-|>",
                color=color,
                lw=1.5,
                connectionstyle="arc3,rad=0",
                shrinkA=1,
                shrinkB=1,
            ),
        )

    # Main adaptive chain
    arrow("map", "right", "proxy", "left")
    arrow("proxy", "right", "focal", "left")
    arrow("focal", "right", "opp", "left")
    arrow("opp", "right", "display", "left")

    # Display → Observe → Update → loop back to MAP
    arrow("display", "bottom", "outcome", "top")
    arrow("outcome", "left", "exposure", "right")
    ex_l = edge_mid("exposure", "left")
    map_b = edge_mid("map", "bottom")
    ax.annotate(
        "",
        xy=map_b,
        xytext=ex_l,
        arrowprops=dict(
            arrowstyle="-|>",
            color="#374151",
            lw=1.5,
            connectionstyle="angle,angleA=180,angleB=-90,rad=0",
            shrinkA=1,
            shrinkB=1,
        ),
    )

    # Cold start → Random Pair (horizontal)
    arrow("cold", "right", "random", "left", color="#6b7280")

    # Random Pair → Display Pair: route RIGHT along the bottom, then UP
    # outside all boxes (past Observe/Display right edges), then LEFT into Display.
    # Avoids crossing Update Exposure / Observe Outcome.
    r_r = edge_mid("random", "right")
    d_r = edge_mid("display", "right")
    x_rail = 10.05  # clear of every box (rightmost box ends ~9.5)
    y_rail = r_r[1]
    verts = [
        (r_r[0], r_r[1]),
        (x_rail, y_rail),
        (x_rail, d_r[1]),
        (d_r[0], d_r[1]),
    ]
    codes = [MPath.MOVETO, MPath.LINETO, MPath.LINETO, MPath.LINETO]
    path = MPath(verts, codes)
    cold_arrow = FancyArrowPatch(
        path=path,
        arrowstyle="-|>",
        mutation_scale=11,
        lw=1.5,
        color="#6b7280",
        joinstyle="miter",
    )
    ax.add_patch(cold_arrow)

    ax.text(
        5.0,
        6.55,
        "After display: vote adds a Comparison; can't decide records zero information",
        ha="center",
        fontsize=9,
        color="#4b5563",
    )
    ax.text(
        5.0,
        0.25,
        "If comparisons = 0 → cold start (random pair); else → MAP pipeline. Both paths display a pair.",
        ha="center",
        fontsize=9,
        color="#4b5563",
        style="italic",
    )

    fig.tight_layout()
    return save_fig(fig, "fig1_system_architecture")


# ── FIGURE 2: Exposure distributions ──────────────────────────────────────────

def last_exposure_by_level(logs: list[dict]) -> dict[str, dict[str, float]]:
    """Last non-empty exposure_counts snapshot per level."""
    latest = {}
    for row in logs:
        level = row.get("level")
        expo = row.get("exposure_counts")
        if level and expo:
            latest[level] = expo
    return latest


def make_fig2(logs: list[dict]):
    latest = last_exposure_by_level(logs)
    stats_rows = []
    fig, axes = plt.subplots(2, 2, figsize=FIG_MULTI)
    axes = axes.ravel()

    zero_strategies = []
    for i, level in enumerate(LEVELS):
        ax = axes[i]
        expo = latest.get(level, {})
        values = np.array([float(v) for v in expo.values()], dtype=float) if expo else np.array([])

        if len(values) == 0:
            ax.set_title(f"{LEVEL_DISPLAY[level]} — no data")
            ax.text(0.5, 0.5, "No exposure data", ha="center", va="center", transform=ax.transAxes)
            continue

        zeros = int(np.sum(values == 0))
        if zeros:
            zero_strategies.append((level, zeros))

        mean = float(values.mean())
        std = float(values.std(ddof=1)) if len(values) > 1 else 0.0
        cv = (std / mean) if mean > 0 else float("nan")
        # Expected CV under uniform multinomial over N strategies, T total exposures
        # Approximate: each strategy shown ~ equally → Poisson/binomial CV ≈ sqrt((1-p)/(n*p))
        # For uniform random pair presentations, exposure ≈ 2T/N; CV ≈ sqrt(1/μ) for Poisson.
        mu = mean
        expected_cv_poisson = math.sqrt(1.0 / mu) if mu > 0 else float("nan")

        stats_rows.append(
            {
                "Level": LEVEL_DISPLAY[level],
                "N_strategies": len(values),
                "Mean": round(mean, 3),
                "Std": round(std, 3),
                "Min": int(values.min()),
                "Max": int(values.max()),
                "CV": round(cv, 4),
                "Expected_CV_Poisson": round(expected_cv_poisson, 4),
                "Zero_exposure_count": zeros,
            }
        )

        color = LEVEL_COLORS[level]
        ax.hist(values, bins=min(15, max(5, int(np.sqrt(len(values))))), color=color, edgecolor="white", alpha=0.85)
        ax.axvline(mean, color="#111827", linestyle="--", linewidth=1.2, label=f"mean={mean:.1f}")
        ax.set_title(LEVEL_DISPLAY[level])
        ax.set_xlabel("Exposure count")
        ax.set_ylabel("Strategies")
        ax.legend(frameon=False, fontsize=8)

    fig.suptitle("Figure 2. Exposure Count Distributions by Level", weight="bold", y=1.02)
    fig.tight_layout()
    paths = save_fig(fig, "fig2_exposure_distributions")

    stats_df = pd.DataFrame(stats_rows)
    # Summary note
    note = (
        "No strategy has zero exposure in the latest per-level snapshot."
        if not zero_strategies
        else "Strategies with zero exposure: "
        + "; ".join(f"{LEVEL_DISPLAY[lv]}={n}" for lv, n in zero_strategies)
    )
    stats_df.attrs["note"] = note
    csv_path = save_csv(stats_df, "fig2_exposure_stats.csv")
    print(f"  [fig2] {note}")
    return paths + [csv_path]


# ── FIGURE 3: Strength differentiation ────────────────────────────────────────

def make_fig3(logs: list[dict]):
    fig, ax = plt.subplots(figsize=FIG_SINGLE)
    growth_rows = []

    for level in LEVELS:
        series_x = []
        series_y = []
        for row in logs:
            if row.get("level") != level:
                continue
            strengths = row.get("map_strengths") or {}
            if not strengths or row.get("was_cold_start"):
                continue
            betas = np.array([float(v) for v in strengths.values()], dtype=float)
            if len(betas) < 2:
                continue
            n_comp = row.get("num_comparisons")
            if n_comp is None:
                continue
            series_x.append(int(n_comp))
            series_y.append(float(betas.max() - betas.min()))

        if not series_x:
            continue

        # Deduplicate by comparison count (keep last β-range at each n)
        by_n = {}
        for x, y in zip(series_x, series_y):
            by_n[x] = y
        xs = sorted(by_n.keys())
        ys = [by_n[x] for x in xs]
        ax.plot(xs, ys, color=LEVEL_COLORS[level], linewidth=2, label=LEVEL_DISPLAY[level])

        # Growth factor: final / value at comparison ≈ 10
        at_10 = None
        for x in xs:
            if x >= 10:
                at_10 = by_n[x]
                break
        final = ys[-1]
        growth = (final / at_10) if at_10 and at_10 > 0 else float("nan")
        growth_rows.append(
            {
                "Level": LEVEL_DISPLAY[level],
                "N_logged_refits": len(xs),
                "Beta_range_at_comp10": round(at_10, 6) if at_10 is not None else None,
                "Beta_range_final": round(final, 6),
                "Growth_factor": round(growth, 3) if not math.isnan(growth) else None,
                "Comparisons_final": xs[-1],
            }
        )

    ax.set_xlabel("Cumulative comparisons used in MAP fit")
    ax.set_ylabel(r"$\beta$ range (max − min)")
    ax.set_title("Figure 3. Strength Differentiation Over Time")
    ax.legend(frameon=False)
    fig.tight_layout()
    paths = save_fig(fig, "fig3_strength_differentiation")
    csv_path = save_csv(pd.DataFrame(growth_rows), "fig3_differentiation_stats.csv")
    return paths + [csv_path]


# ── FIGURE 4: Opponent diversity ──────────────────────────────────────────────

def make_fig4(logs: list[dict]):
    rows = []
    labels = []
    rates = []
    colors = []

    for level in LEVELS:
        level_logs = [r for r in logs if r.get("level") == level and r.get("opponent_id") is not None]
        n = len(level_logs)
        unique = len({r["opponent_id"] for r in level_logs})
        rate = (unique / n) if n else 0.0

        # Sparse-phase heuristic: strength_diff < 0.01 (matches algorithm SPARSE_THRESHOLD)
        sparse = [r for r in level_logs if (r.get("opponent_strength_diff") is not None and float(r["opponent_strength_diff"]) < 0.01)]
        normal = [r for r in level_logs if r not in sparse]
        sparse_rate = (
            len({r["opponent_id"] for r in sparse}) / len(sparse) if sparse else None
        )
        normal_rate = (
            len({r["opponent_id"] for r in normal}) / len(normal) if normal else None
        )

        rows.append(
            {
                "Level": LEVEL_DISPLAY[level],
                "Total_selections": n,
                "Unique_opponents": unique,
                "Unique_opponent_rate": round(rate, 4),
                "Sparse_phase_selections": len(sparse),
                "Sparse_phase_unique_rate": round(sparse_rate, 4) if sparse_rate is not None else None,
                "Normal_phase_selections": len(normal),
                "Normal_phase_unique_rate": round(normal_rate, 4) if normal_rate is not None else None,
            }
        )
        labels.append(LEVEL_DISPLAY[level])
        rates.append(rate)
        colors.append(LEVEL_COLORS[level])

    fig, ax = plt.subplots(figsize=FIG_SINGLE)
    x = np.arange(len(labels))
    bars = ax.bar(x, rates, color=colors, edgecolor="white", width=0.65)
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("Unique opponents / total selections")
    ax.set_ylim(0, max(1.0, max(rates) * 1.15 if rates else 1.0))
    ax.set_title("Figure 4. Opponent Diversity by Level")
    for bar, r in zip(bars, rates):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.02, f"{r:.2f}", ha="center", fontsize=9)
    fig.tight_layout()
    paths = save_fig(fig, "fig4_opponent_diversity")
    csv_path = save_csv(pd.DataFrame(rows), "fig4_diversity_stats.csv")
    return paths + [csv_path]


# ── FIGURE 5: Focal sampling probability ──────────────────────────────────────

def make_fig5(logs: list[dict]):
    fig, axes = plt.subplots(2, 2, figsize=FIG_MULTI)
    axes = axes.ravel()

    for i, level in enumerate(LEVELS):
        ax = axes[i]
        # Latest non-cold-start log with strengths + focal info for this level
        candidates = [
            r
            for r in logs
            if r.get("level") == level
            and not r.get("was_cold_start")
            and r.get("map_strengths")
            and r.get("uncertainty_weights")
        ]
        if not candidates:
            ax.set_title(f"{LEVEL_DISPLAY[level]} — no data")
            continue
        snap = candidates[-1]
        strengths = snap["map_strengths"]
        weights = snap.get("uncertainty_weights") or {}
        exposures = snap.get("exposure_counts") or {}

        # Normalize uncertainty weights to P(focal) if they look like raw weights
        w_vals = {str(k): float(v) for k, v in weights.items()}
        total_w = sum(w_vals.values())
        if total_w <= 0:
            ax.set_title(f"{LEVEL_DISPLAY[level]} — empty weights")
            continue
        # If already probabilities (sum≈1), use as-is; else normalize
        if abs(total_w - 1.0) < 0.05:
            probs = w_vals
        else:
            probs = {k: v / total_w for k, v in w_vals.items()}

        xs, ys, cs = [], [], []
        for sid, beta in strengths.items():
            sid = str(sid)
            if sid not in probs:
                continue
            xs.append(float(beta))
            ys.append(float(probs[sid]))
            cs.append(float(exposures.get(sid, 0)))

        if not xs:
            ax.set_title(f"{LEVEL_DISPLAY[level]} — no overlap")
            continue

        sc = ax.scatter(
            xs,
            ys,
            c=cs,
            cmap="viridis",
            s=36,
            edgecolors="white",
            linewidths=0.4,
            alpha=0.9,
        )
        fig.colorbar(sc, ax=ax, fraction=0.046, pad=0.04, label="Exposure")
        ax.set_xlabel(r"Estimated $\beta$")
        ax.set_ylabel("P(focal)")
        ax.set_title(LEVEL_DISPLAY[level])

    fig.suptitle("Figure 5. Focal Sampling Probability (Latest Snapshot)", weight="bold", y=1.02)
    fig.tight_layout()
    return save_fig(fig, "fig5_focal_sampling")


# ── FIGURE 6: MAP convergence ─────────────────────────────────────────────────

def make_fig6(logs: list[dict]):
    refits = [
        r
        for r in logs
        if r.get("map_converged") is not None and not r.get("was_cold_start")
    ]
    total = len(refits)
    converged = sum(1 for r in refits if r.get("map_converged") is True)
    rate = (converged / total) if total else 0.0
    iterations = [
        int(r["map_iterations"])
        for r in refits
        if r.get("map_iterations") is not None
    ]

    fig, ax = plt.subplots(figsize=FIG_SINGLE)
    if iterations:
        bins = range(0, max(iterations) + 2)
        ax.hist(iterations, bins=bins, color="#6366f1", edgecolor="white", align="left")
    ax.set_xlabel("MAP iterations (L-BFGS-B)")
    ax.set_ylabel("Count of refits")
    ax.set_title("Figure 6. MAP Convergence — Iteration Counts")
    ax.text(
        0.98,
        0.95,
        f"Refits: {total}\nConverged: {converged} ({100*rate:.1f}%)",
        transform=ax.transAxes,
        ha="right",
        va="top",
        fontsize=10,
        bbox=dict(boxstyle="round", facecolor="white", edgecolor="#d1d5db"),
    )
    fig.tight_layout()
    paths = save_fig(fig, "fig6_convergence_histogram")

    stats = pd.DataFrame(
        [
            {
                "Total_refits": total,
                "Converged": converged,
                "Convergence_rate": round(rate, 4),
                "Iter_mean": round(float(np.mean(iterations)), 3) if iterations else None,
                "Iter_median": float(np.median(iterations)) if iterations else None,
                "Iter_min": int(min(iterations)) if iterations else None,
                "Iter_max": int(max(iterations)) if iterations else None,
            }
        ]
    )
    csv_path = save_csv(stats, "fig6_convergence_stats.csv")
    return paths + [csv_path]


# ── FIGURE 7: Collection timeline ─────────────────────────────────────────────

def make_fig7(logs: list[dict]):
    from datetime import date
    import matplotlib.dates as mdates

    # Formal data-collection window (matches study period)
    STUDY_START = date(2026, 4, 21)
    STUDY_END = date(2026, 6, 30)

    fig, ax = plt.subplots(figsize=FIG_SINGLE)

    for level in LEVELS:
        dates = []
        for row in logs:
            if row.get("level") != level:
                continue
            ts = row.get("timestamp")
            if not ts:
                continue
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except ValueError:
                continue
            d = dt.date()
            if d < STUDY_START or d > STUDY_END:
                continue
            dates.append(d)
        if not dates:
            continue
        day_counts = Counter(dates)
        days = sorted(day_counts.keys())
        cum = np.cumsum([day_counts[d] for d in days])
        # Start at 0 on study open date so cumulative is Apr 21 → Jun 30
        plot_days = [STUDY_START] + list(days)
        plot_cum = [0] + list(cum)
        # If first activity is after Apr 21, keep the leading zero at STUDY_START;
        # if activity exists on Apr 21, replace the duplicate date with cumulative after that day.
        if days[0] == STUDY_START:
            plot_days = [STUDY_START] + days
            plot_cum = [0] + list(cum)
        ax.plot(
            plot_days,
            plot_cum,
            color=LEVEL_COLORS[level],
            linewidth=2,
            marker="o",
            markersize=3,
            label=LEVEL_DISPLAY[level],
        )

    ax.set_xlabel("Date")
    ax.set_ylabel("Cumulative pair selections")
    ax.set_title("Figure 7. Data Collection Timeline")
    ax.set_ylim(bottom=0)
    ax.set_xlim(STUDY_START, STUDY_END)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
    ax.xaxis.set_major_locator(mdates.DayLocator(bymonthday=[1, 15]))
    ax.legend(frameon=False)
    fig.autofmt_xdate()
    fig.tight_layout()
    return save_fig(fig, "fig7_collection_timeline")


# ── DB outputs ────────────────────────────────────────────────────────────────

def make_db_outputs(engine):
    from sqlalchemy import text

    generated = []

    with engine.connect() as conn:
        # Votes per level
        votes = pd.read_sql(
            text(
                """
                SELECT level_context, COUNT(*) AS votes
                FROM comparisons
                GROUP BY level_context
                ORDER BY votes DESC
                """
            ),
            conn,
        )
        generated.append(save_csv(votes, "data_votes_per_level.csv"))

        # Per-session summary
        per_session = pd.read_sql(
            text(
                """
                SELECT s.id, s.role,
                       COUNT(c.id) AS total_votes,
                       COUNT(DISTINCT c.level_context) AS levels_used,
                       s.started_at, s.ended_at, s.last_activity
                FROM sessions s
                LEFT JOIN comparisons c ON s.id = c.session_id
                GROUP BY s.id, s.role, s.started_at, s.ended_at, s.last_activity
                ORDER BY s.started_at
                """
            ),
            conn,
        )

        # Duration
        durs = []
        for _, row in per_session.iterrows():
            d = duration_seconds(row["started_at"], row["ended_at"], row["last_activity"])
            durs.append(d)
        per_session["duration_seconds"] = durs
        per_session_out = per_session[["id", "role", "total_votes", "levels_used", "duration_seconds"]].copy()
        generated.append(save_csv(per_session_out, "data_per_session_summary.csv"))

        # Session stats with outlier flag (> 3 hours)
        OUTLIER_SEC = 3 * 3600
        valid = per_session["duration_seconds"].dropna()
        outliers = valid[valid > OUTLIER_SEC]
        cleaned = valid[valid <= OUTLIER_SEC]

        def qstats(series):
            if series.empty:
                return dict(mean=None, median=None, q1=None, q3=None, iqr=None, n=0)
            q1 = float(series.quantile(0.25))
            q3 = float(series.quantile(0.75))
            return dict(
                mean=float(series.mean()),
                median=float(series.median()),
                q1=q1,
                q3=q3,
                iqr=q3 - q1,
                n=int(series.shape[0]),
            )

        all_s = qstats(valid)
        clean_s = qstats(cleaned)
        votes_s = per_session["total_votes"]
        levels_s = per_session["levels_used"]

        session_stats = pd.DataFrame(
            [
                {
                    "metric": "duration_seconds_all",
                    "n": all_s["n"],
                    "mean": round(all_s["mean"], 2) if all_s["mean"] is not None else None,
                    "median": round(all_s["median"], 2) if all_s["median"] is not None else None,
                    "q1": round(all_s["q1"], 2) if all_s["q1"] is not None else None,
                    "q3": round(all_s["q3"], 2) if all_s["q3"] is not None else None,
                    "iqr": round(all_s["iqr"], 2) if all_s["iqr"] is not None else None,
                },
                {
                    "metric": "duration_seconds_excl_outliers_gt_3h",
                    "n": clean_s["n"],
                    "mean": round(clean_s["mean"], 2) if clean_s["mean"] is not None else None,
                    "median": round(clean_s["median"], 2) if clean_s["median"] is not None else None,
                    "q1": round(clean_s["q1"], 2) if clean_s["q1"] is not None else None,
                    "q3": round(clean_s["q3"], 2) if clean_s["q3"] is not None else None,
                    "iqr": round(clean_s["iqr"], 2) if clean_s["iqr"] is not None else None,
                },
                {
                    "metric": "votes_per_session",
                    "n": int(votes_s.shape[0]),
                    "mean": round(float(votes_s.mean()), 3),
                    "median": float(votes_s.median()),
                    "q1": float(votes_s.quantile(0.25)),
                    "q3": float(votes_s.quantile(0.75)),
                    "iqr": float(votes_s.quantile(0.75) - votes_s.quantile(0.25)),
                },
                {
                    "metric": "levels_per_session",
                    "n": int(levels_s.shape[0]),
                    "mean": round(float(levels_s.mean()), 3),
                    "median": float(levels_s.median()),
                    "q1": float(levels_s.quantile(0.25)),
                    "q3": float(levels_s.quantile(0.75)),
                    "iqr": float(levels_s.quantile(0.75) - levels_s.quantile(0.25)),
                },
                {
                    "metric": "note",
                    "n": int(outliers.shape[0]),
                    "mean": None,
                    "median": None,
                    "q1": None,
                    "q3": None,
                    "iqr": None,
                },
            ]
        )
        # Attach readable note in a companion one-row frame column via CSV comment-like row
        note_row = {
            "metric": "NOTE",
            "n": None,
            "mean": None,
            "median": None,
            "q1": None,
            "q3": None,
            "iqr": None,
        }
        session_stats = pd.concat([session_stats, pd.DataFrame([note_row])], ignore_index=True)
        # Write with a leading comment line for Hannah
        ensure_out()
        path = OUT_DIR / "data_session_stats.csv"
        with open(path, "w", encoding="utf-8") as f:
            f.write(
                "# Two sessions excluded as outliers (40h and 192h open time) "
                "when recomputing duration mean/median (threshold: >3 hours).\n"
            )
            f.write(f"# Outlier sessions found in this export: {int(outliers.shape[0])}\n")
            if not outliers.empty:
                outlier_ids = per_session.loc[
                    per_session["duration_seconds"] > OUTLIER_SEC, ["id", "duration_seconds"]
                ]
                for _, o in outlier_ids.iterrows():
                    hrs = o["duration_seconds"] / 3600.0
                    f.write(f"# outlier session_id={o['id']} duration_hours={hrs:.2f}\n")
            session_stats.to_csv(f, index=False)
        generated.append(path)

        # Strategy distribution by level
        strategies = pd.read_sql(
            text(
                """
                SELECT id, choice, level, is_active, is_user_submitted
                FROM strategies
                WHERE is_active = TRUE
                """
            ),
            conn,
        )

        def normalize_level_token(tok: str) -> str:
            t = tok.strip()
            if t == "Patient":
                return "Client"
            return t

        level_counts = Counter()
        multi = 0
        for _, row in strategies.iterrows():
            parts = [normalize_level_token(p) for p in str(row["level"] or "").split(",") if p.strip()]
            if len(parts) > 1:
                multi += 1
            for p in parts:
                level_counts[p] += 1

        dist_rows = [
            {"Level": "Provider", "Strategy_count": level_counts.get("Provider", 0)},
            {"Level": "Organization", "Strategy_count": level_counts.get("Organization", 0)},
            {"Level": "System", "Strategy_count": level_counts.get("System", 0)},
            {"Level": "Client_Patient", "Strategy_count": level_counts.get("Client", 0)},
            {"Level": "Multi_level_strategies", "Strategy_count": multi},
            {"Level": "Total_active_strategies", "Strategy_count": int(strategies.shape[0])},
            {
                "Level": "Hannah_reference_system_21_org_82_provider_58_patient_22_multi_78",
                "Strategy_count": None,
            },
        ]
        generated.append(save_csv(pd.DataFrame(dist_rows), "data_strategy_distribution.csv"))

        # Submitted ideas
        ideas = pd.read_sql(
            text(
                """
                SELECT id, user_role, status, created_at
                FROM submitted_ideas
                ORDER BY created_at
                """
            ),
            conn,
        )
        status_counts = ideas["status"].value_counts().to_dict() if not ideas.empty else {}
        role_counts = ideas["user_role"].value_counts().to_dict() if not ideas.empty else {}
        idea_summary = pd.DataFrame(
            [
                {"category": "total", "key": "all", "count": int(ideas.shape[0])},
                {
                    "category": "status",
                    "key": "pending",
                    "count": int(status_counts.get("pending", 0)),
                },
                {
                    "category": "status",
                    "key": "approved",
                    "count": int(status_counts.get("approved", 0)),
                },
                {
                    "category": "status",
                    "key": "rejected",
                    "count": int(status_counts.get("rejected", 0)),
                },
                {
                    "category": "status",
                    "key": "duplicate",
                    "count": int(status_counts.get("duplicate", 0)),
                },
            ]
            + [{"category": "role", "key": k, "count": int(v)} for k, v in role_counts.items()]
            + [
                {
                    "category": "note",
                    "key": "Hannah_reference_6_submitted_5_rejected_1_duplicate_0_approved",
                    "count": None,
                }
            ]
        )
        generated.append(save_csv(idea_summary, "data_submitted_ideas.csv"))

        # Rankings (BT MAP)
        generated.extend(make_rankings(conn))

    return generated


def make_rankings(conn):
    from sqlalchemy import text

    strategies = pd.read_sql(
        text(
            """
            SELECT id, choice, level, is_active
            FROM strategies
            WHERE is_active = TRUE
            """
        ),
        conn,
    )
    comparisons = pd.read_sql(
        text("SELECT session_id, winner_id, loser_id FROM comparisons"),
        conn,
    )
    sessions = pd.read_sql(text("SELECT id, role FROM sessions"), conn)
    role_map = dict(zip(sessions["id"], sessions["role"]))

    strategy_ids = strategies["id"].tolist()
    strategy_map = {int(r.id): r for r in strategies.itertuples()}
    sid_set = set(strategy_ids)
    sigma2 = float(os.environ.get("BT_SIGMA2", "1.0"))
    bt = BradleyTerryMAP(sigma2=sigma2)

    def rank_for(filter_role: str | None, outfile: str):
        if filter_role:
            role_sids = {sid for sid, role in role_map.items() if role == filter_role}
            comps = [
                (int(r.winner_id), int(r.loser_id))
                for r in comparisons.itertuples()
                if r.session_id in role_sids
                and int(r.winner_id) in sid_set
                and int(r.loser_id) in sid_set
            ]
        else:
            comps = [
                (int(r.winner_id), int(r.loser_id))
                for r in comparisons.itertuples()
                if int(r.winner_id) in sid_set and int(r.loser_id) in sid_set
            ]

        if not strategy_ids:
            df = pd.DataFrame(
                columns=["Rank", "Strategy", "Level(s)", "BT Score", "Wins", "Appearances"]
            )
            return save_csv(df, outfile)

        result = bt.fit(strategy_ids, comps)
        rows = []
        for sid, beta in result["ranking"]:
            s = strategy_map.get(int(sid))
            if not s:
                continue
            wins = sum(1 for w, l in comps if w == sid)
            appearances = sum(1 for w, l in comps if w == sid or l == sid)
            rows.append(
                {
                    "Rank": 0,  # filled below
                    "Strategy": truncate(s.choice, 80),
                    "Level(s)": s.level,
                    "BT Score": get_bt_score(beta),
                    "Wins": wins,
                    "Appearances": appearances,
                    "_beta": beta,
                }
            )
        # Already sorted by beta desc from fit
        for i, row in enumerate(rows[:12], start=1):
            row["Rank"] = i
        top = pd.DataFrame(rows[:12]).drop(columns=["_beta"], errors="ignore")
        return save_csv(top, outfile)

    paths = [
        rank_for(None, "rankings_overall.csv"),
        rank_for("Provider", "rankings_provider.csv"),
        rank_for("Implementation Scientist", "rankings_impl_scientist.csv"),
        rank_for("Patient/Family", "rankings_patient_family.csv"),
        rank_for("Policy/Advocacy", "rankings_policy_advocacy.csv"),
    ]
    return paths


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Generate IMPACT S2S manuscript figures, tables, and PH data exports."
    )
    parser.add_argument(
        "algorithm_logs",
        help="Path to algorithm logs JSON from /api/admin/algorithm-logs/export",
    )
    parser.add_argument(
        "--out",
        default="manuscript_outputs",
        help="Output directory (default: manuscript_outputs)",
    )
    args = parser.parse_args()

    global OUT_DIR
    OUT_DIR = Path(args.out)
    ensure_out()

    if not os.path.exists(args.algorithm_logs):
        print(f"ERROR: algorithm logs file not found: {args.algorithm_logs}", file=sys.stderr)
        sys.exit(1)

    print(f"Loading algorithm logs from {args.algorithm_logs} ...")
    logs = load_logs(args.algorithm_logs)
    print(f"  {len(logs)} log entries loaded")

    generated = []

    print("Generating Table 1 ...")
    generated.extend(make_table1())

    print("Generating Figure 1 (architecture) ...")
    generated.extend(make_fig1())

    print("Generating Figure 2 (exposure) ...")
    generated.extend(make_fig2(logs))

    print("Generating Figure 3 (strength differentiation) ...")
    generated.extend(make_fig3(logs))

    print("Generating Figure 4 (opponent diversity) ...")
    generated.extend(make_fig4(logs))

    print("Generating Figure 5 (focal sampling) ...")
    generated.extend(make_fig5(logs))

    print("Generating Figure 6 (convergence) ...")
    generated.extend(make_fig6(logs))

    print("Generating Figure 7 (timeline) ...")
    generated.extend(make_fig7(logs))

    engine = get_engine()
    if engine is None:
        print(
            "DATABASE_URL not set — skipping DB outputs "
            "(votes, sessions, rankings, strategies, ideas)."
        )
    else:
        print(f"Connecting to database via DATABASE_URL ...")
        try:
            generated.extend(make_db_outputs(engine))
        except Exception as exc:
            print(f"ERROR running DB outputs: {exc}", file=sys.stderr)
            raise

    # Deduplicate while preserving order
    seen = set()
    unique = []
    for p in generated:
        sp = str(p)
        if sp not in seen:
            seen.add(sp)
            unique.append(Path(p))

    print("\n=== Generated files ===")
    for p in sorted(unique, key=lambda x: x.name):
        print(f"  {p}")
    print(f"\nTotal: {len(unique)} files in {OUT_DIR.resolve()}")


if __name__ == "__main__":
    main()

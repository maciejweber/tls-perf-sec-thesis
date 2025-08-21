#!/usr/bin/env python3
import sys
import pathlib
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import re

if len(sys.argv) != 3:
    sys.exit("użycie: compare_aesni.py <run_dir_on> <run_dir_off>")

run_on, run_off = map(pathlib.Path, sys.argv[1:])
run_name = run_on.name


def load(run_dir, label):
    df = pd.read_csv(run_dir / "bench.csv", engine="python", on_bad_lines="skip")
    df["aes_ni"] = label
    return df


df = pd.concat([load(run_on, "on"), load(run_off, "off")])
df = df[df.metric.isin(["mean_ms", "rps"])].copy()
df["value"] = pd.to_numeric(df["value"], errors="coerce")
df = df.dropna(subset=["value"])

pivot = (
    df.groupby(["aes_ni", "implementation", "suite", "test", "metric"])
    .value.mean()
    .unstack("aes_ni")
    .round(3)
)
pivot["delta_percent"] = ((pivot["off"] - pivot["on"]) / pivot["on"] * 100).round(1)

out_csv = run_on / "aesni_compare.csv"
pivot.to_csv(out_csv)
print(f"✅ zapisano CSV: {out_csv.absolute()}")

dfp = pivot.reset_index()
sns.set_palette("colorblind")


figures_dir = pathlib.Path("figures") / run_name / "compare_aesni"
figures_dir.mkdir(parents=True, exist_ok=True)

for metric, ylabel, fname in [
    ("mean_ms", "Δ Handshake (ms)", "aesni_delta_mean_ms.png"),
    ("rps", "Δ Throughput (RPS)", "aesni_delta_rps.png"),
]:
    sub = dfp[dfp.metric == metric]
    if sub.empty:
        continue

    fig, ax = plt.subplots(figsize=(10, 7))

    sns.barplot(data=sub, x="suite", y="delta_percent", hue="implementation", ax=ax)
    ax.axhline(0, color="black", linewidth=1)

    for p in ax.patches:
        h = p.get_height()
        if pd.notna(h):

            if h >= 0:
                va = "bottom"
                y = h + (abs(h) * 0.02 if abs(h) > 1e-6 else 0.5)
            else:
                va = "top"
                y = h - (abs(h) * 0.02 if abs(h) > 1e-6 else 0.5)
            ax.annotate(
                f"{h:+.1f}%",
                (p.get_x() + p.get_width() / 2, y),
                ha="center",
                va=va,
                fontsize=8,
            )

    ax.set_ylabel("Δ % (off – on) / on")
    ax.set_xlabel("Suite")

    ax.set_title(ylabel, pad=20)

    ax.legend(
        title="Implementation",
        loc="upper center",
        bbox_to_anchor=(0.5, -0.1),
        ncol=len(sub.implementation.unique()),
        frameon=True,
    )

    plt.subplots_adjust(
        top=0.9,
        bottom=0.2,
        left=0.1,
        right=0.95,
    )

    out_path = figures_dir / fname
    plt.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"✓ zapisano wykres: {out_path.absolute()}")

# === Heatmap (suite x implementation) for delta% ===
for metric, fname in [
    ("mean_ms", "aesni_delta_mean_ms_heatmap.png"),
    ("rps", "aesni_delta_rps_heatmap.png"),
]:
    sub = dfp[dfp.metric == metric]
    if sub.empty:
        continue
    heat = sub.pivot(index="suite", columns="implementation", values="delta_percent")
    fig, ax = plt.subplots(figsize=(8, 5))
    sns.heatmap(heat, annot=True, fmt="+.1f", cmap="RdBu_r", center=0, ax=ax)
    ax.set_title(f"AES-NI Δ% heatmap ({metric})")
    out_path = figures_dir / fname
    plt.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"✓ zapisano heatmapę: {out_path.absolute()}")


# === Optional: throughput delta heatmap by payload and concurrency (raw bulk jsons) ===
def load_bulk(run_dir):
    rows = []
    for p in run_dir.glob("bulk_*.json"):
        try:
            js = pd.read_json(p, typ="series")
            port = int(re.search(r"bulk_(\d+)\.json", p.name).group(1))
            rows.append(
                {
                    "port": port,
                    "throughput_mb_s": float(js.get("throughput_mb_s", float("nan"))),
                    "payload_size_mb": float(js.get("payload_size_mb", float("nan"))),
                    "concurrency": int(js.get("concurrency", 1)),
                }
            )
        except Exception:
            continue
    return pd.DataFrame(rows)


try:
    b_on = (
        load_bulk(run_on).dropna(subset=["throughput_mb_s"])
        if run_on.exists()
        else None
    )
    b_off = (
        load_bulk(run_off).dropna(subset=["throughput_mb_s"])
        if run_off.exists()
        else None
    )
    if b_on is not None and b_off is not None and not b_on.empty and not b_off.empty:
        merged = pd.merge(
            b_on,
            b_off,
            on=["port", "payload_size_mb", "concurrency"],
            suffixes=("_on", "_off"),
            how="inner",
        )
        if not merged.empty:
            merged["delta_percent"] = (
                (merged["throughput_mb_s_off"] - merged["throughput_mb_s_on"])
                / merged["throughput_mb_s_on"]
                * 100
            ).round(1)
            heat = merged.pivot_table(
                index=["payload_size_mb"],
                columns=["concurrency"],
                values="delta_percent",
                aggfunc="mean",
            )
            fig, ax = plt.subplots(figsize=(8, 5))
            sns.heatmap(heat, annot=True, fmt="+.1f", cmap="RdBu_r", center=0, ax=ax)
            ax.set_title("AES-NI Δ% throughput heatmap (payload x concurrency)")
            ax.set_xlabel("concurrency")
            ax.set_ylabel("payload MB")
            out_path = figures_dir / "aesni_delta_throughput_payload_conc.png"
            plt.savefig(out_path, dpi=300, bbox_inches="tight")
            plt.close(fig)
            print(f"✓ zapisano heatmapę: {out_path.absolute()}")
except Exception:
    pass

print(f"✅ wykresy zapisane w {figures_dir.absolute()}")

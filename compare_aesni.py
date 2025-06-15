#!/usr/bin/env python3
import sys
import pathlib
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

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

print(f"✅ wykresy zapisane w {figures_dir.absolute()}")

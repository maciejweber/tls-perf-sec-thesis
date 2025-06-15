# compare_aesni.py
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

out_csv = pathlib.Path("aesni_compare.csv")
pivot.to_csv(out_csv)
print(f"✅ zapisano {out_csv.absolute()}")

dfp = pivot.reset_index()
sns.set_palette("colorblind")

# put compare-AESNI charts under figures/<run_name>/compare_aesni/
figures_dir = pathlib.Path("figures") / run_name / "compare_aesni"
figures_dir.mkdir(parents=True, exist_ok=True)

for metric, ylabel, fname in [
    ("mean_ms", "Δ Handshake (ms)", "aesni_delta_mean_ms.png"),
    ("rps", "Δ Throughput (RPS)", "aesni_delta_rps.png"),
]:
    sub = dfp[dfp.metric == metric]
    plt.figure(figsize=(8, 5))
    ax = sns.barplot(data=sub, x="suite", y="delta_percent", hue="implementation")
    ax.axhline(0, color="black", linewidth=1)
    for p in ax.patches:
        h = p.get_height()
        if pd.notna(h):
            ax.annotate(
                f"{h:+.1f}%",
                (p.get_x() + p.get_width() / 2, h),
                ha="center",
                va="bottom",
                fontsize=8,
            )
    ax.set_ylabel("Δ % (off – on) / on")
    ax.set_xlabel("Suite")
    ax.set_title(ylabel)
    ax.legend(
        title="Implementation",
        loc="upper center",
        bbox_to_anchor=(0.5, 1.15),
        ncol=len(sub.implementation.unique()),
    )
    plt.tight_layout()
    plt.savefig(figures_dir / fname, dpi=300)
    plt.close()

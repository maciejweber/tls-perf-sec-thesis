#!/usr/bin/env python3
# pip install pandas numpy scipy matplotlib seaborn openpyxl

"""
Rozdział 10 – analiza wydajności TLS
===================================
Ten skrypt pokazuje pełny pipeline „dane → statystyka → wykres”.

Działa z CSV‑ami wygenerowanymi przez skrypty *run_* z katalogu **results/**
Twojego repozytorium.  Gdyby nazwy kolumn lub metryk różniły się od wersji,
na której pisałem kod, popraw jedną funkcją `rename_or_compute_metrics()` –
na dole znajdziesz komentarz *TODO* z instrukcją, co zmienić.

Wyniki:
* **figures/throughput_box.png** – porównanie szybkości pobierania.
* **summary.xlsx** – gotowa tabelka do recenzji.
* Na stdout: statystyki opisowe + wartości *p* z ANOVA.

Każdy większy blok ma własny docstring wyjaśniający, *dlaczego* robimy
konkretny krok – dokładnie to było celem dydaktycznym rozdziału.
"""

from __future__ import annotations

import glob
import os
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
import matplotlib.pyplot as plt
import seaborn as sns

RESULTS_DIR = Path(__file__).resolve().parent / "results"
FIG_DIR = Path(__file__).resolve().parent / "figures"
FIG_DIR.mkdir(exist_ok=True)


def load_all_csv(folder: Path = RESULTS_DIR) -> pd.DataFrame:
    """Zbiera *wszystkie* pliki CSV i łączy w jeden DataFrame."""
    frames: list[pd.DataFrame] = []
    for csv in folder.glob("*.csv"):
        df = pd.read_csv(csv)
        df["source_file"] = csv.name
        frames.append(df)
    if not frames:
        raise FileNotFoundError(f"Brak plików .csv w {folder}")
    return pd.concat(frames, ignore_index=True)


def rename_or_compute_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """Zapewnia kolumny *handshake_ms* i *throughput_mb_s* wymagane dalej."""

    df = df.copy()

    # --- handshake ---------------------------------------------------------
    mask_hand = df["metric"].eq("mean_ms") & df["test"].eq("handshake")
    df.loc[mask_hand, "metric"] = "handshake_ms"

    # --- throughput --------------------------------------------------------
    SIZE_MB_PER_REQUEST = 1.0  # TODO: jeśli inny rozmiar pliku -> zmień

    mask_tput = df["metric"].eq("throughput_mb_s") & df["test"].eq("bulk")
    if not mask_tput.any():
        mask_rps = df["metric"].eq("rps") & df["test"].eq("bulk")
        if mask_rps.any():
            tmp = df[mask_rps].copy()
            tmp["value"] = tmp["value"].astype(float) * SIZE_MB_PER_REQUEST
            tmp["metric"] = "throughput_mb_s"
            df = pd.concat([df, tmp], ignore_index=True)
        else:
            raise ValueError("Nie znaleziono ani 'throughput_mb_s' ani 'rps'.")
    return df


def summarise(df: pd.DataFrame) -> pd.DataFrame:
    """Liczy średnią, 95‑ty percentyl i 95 % CI (1.96 × SEM) dla każdej grupy."""

    df = df[df["metric"].isin(["handshake_ms", "throughput_mb_s"])]

    def agg(group: pd.Series) -> pd.Series:
        mean = group.mean()
        p95 = group.quantile(0.95)
        ci95 = stats.sem(group) * 1.96 if len(group) > 1 else 0.0
        return pd.Series({"mean": mean, "p95": p95, "ci95": ci95})

    return (
        df.groupby(["implementation", "suite", "test", "metric"])["value"]
        .apply(agg)
        .reset_index()
    )


def run_anova(df: pd.DataFrame, metric: str) -> None:
    """Jednoczynnikowa ANOVA: czy *suite* wpływa na daną metrykę?"""

    sub = df[df["metric"].eq(metric)]
    if sub.empty:
        print(f"[ANOVA] Pomijam {metric} – brak danych")
        return

    groups = [g["value"].values for _, g in sub.groupby("suite")]
    f_stat, p_val = stats.f_oneway(*groups)

    print(f"ANOVA dla {metric} / suite  →  F={f_stat:.3f},  p={p_val:.4g}")
    if p_val < 0.05:
        print("  ⇒ Odrzucamy H₀: średnie nie są równe (istotna różnica).\n")
    else:
        print("  ⇒ Brak podstaw do odrzucenia H₀ (różnice nie‑istotne).\n")


def plot_throughput(
    df: pd.DataFrame, out: Path = FIG_DIR / "throughput_box.png"
) -> None:
    """Rysuje box‑plot *throughput_mb_s vs suite* i zapisuje PNG."""
    sub = df[df["metric"] == "throughput_mb_s"]
    if sub.empty:
        print("[WYKRES] Pomijam throughput_box – brak danych")
        return

    plt.figure(figsize=(8, 5))
    sns.boxplot(x="suite", y="value", data=sub)
    plt.xlabel("zestaw krzywych (suite)")
    plt.ylabel("przepustowość [MB/s]")
    plt.title("Throughput TLS – porównanie algorytmów krzywych X25519 vs ChaCha20")
    plt.tight_layout()
    plt.savefig(out, dpi=300)
    plt.close()
    rel = (
        out.resolve().relative_to(Path.cwd()) if out.is_relative_to(Path.cwd()) else out
    )
    print(f"✔ Zapisano wykres: {rel}")


def export_excel(df_summary: pd.DataFrame, out: Path = Path("summary.xlsx")) -> None:
    """Zapisuje wyniki do Excela – ułatwia dalszy przegląd / recenzję."""

    with pd.ExcelWriter(out) as xl:
        for metric, g in df_summary.groupby("metric"):
            sheet = metric.replace("_", " ")[:31]
            g.drop(columns=["metric"]).to_excel(xl, sheet_name=sheet, index=False)
    # Użyj bezpiecznej formy wypisywania ścieżki, żeby uniknąć ValueError
    rel = (
        out.resolve().relative_to(Path.cwd())
        if out.resolve().is_relative_to(Path.cwd())
        else out
    )
    print(f"✔ Zapisano podsumowanie: {rel}")


def main() -> None:
    raw = load_all_csv()
    tidy = rename_or_compute_metrics(raw)
    summary = summarise(tidy)

    pd.set_option("display.max_columns", None)
    print("\nStatystyki opisowe (mean / p95 / ci95):\n", summary.head(), "\n")

    for m in ["handshake_ms", "throughput_mb_s"]:
        run_anova(tidy, m)

    plot_throughput(tidy)
    export_excel(summary)


if __name__ == "__main__":
    main()

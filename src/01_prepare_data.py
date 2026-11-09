"""Prepare NHANES 2011–2014 MEC participants aged 60+ for analysis.

Run from anywhere: python src/01_prepare_data.py
Inputs: data/raw/<cycle>/<dataset>_<suffix>.xpt
Output: data/processed/nhanes_2011_2014_processed.csv
"""
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / 'data' / 'raw'
OUTPUT = ROOT / 'data' / 'processed' / 'nhanes_2011_2014_processed.csv'
CYCLES = {'2011-2012': 'G', '2013-2014': 'H'}
DATASETS = ('CFQ', 'BPX', 'BPQ', 'DIQ', 'BMX', 'TCHOL', 'HDL', 'GHB')
RISK_FACTORS = ('hypertension', 'diabetes', 'obesity', 'dyslipidemia')


def load_xpt(cycle, name, suffix):
    path = RAW / cycle / f'{name}_{suffix}.xpt'
    if not path.is_file():
        raise FileNotFoundError(path)
    data = pd.read_sas(path, format='xport')
    if data['SEQN'].duplicated().any():
        raise ValueError(f'Duplicate SEQN in {path}')
    return data


def load_cohort():
    cycles = []
    for cycle, suffix in CYCLES.items():
        demo = load_xpt(cycle, 'DEMO', suffix)
        cohort = demo.loc[(demo['RIDAGEYR'] >= 60) & (demo['RIDSTATR'] == 2)].copy()
        n = len(cohort)
        for name in DATASETS:
            cohort = cohort.merge(load_xpt(cycle, name, suffix), on='SEQN', how='left', validate='one_to_one')
        assert len(cohort) == n, f'Unexpected row count for {cycle}'
        cohort['cycle'] = cycle
        print(f'{cycle}: {n} eligible examined participants')
        cycles.append(cohort)
    df = pd.concat(cycles, ignore_index=True)
    assert df['SEQN'].is_unique
    df['WTMEC4YR'] = df['WTMEC2YR'] / len(CYCLES)
    return df


def classify(positive, negative):
    """Positive evidence takes precedence; otherwise require explicit negative evidence."""
    return np.select([positive, negative], [1.0, 0.0], default=np.nan)


def derive_exposures(df):
    sbp_cols = ['BPXSY1', 'BPXSY2', 'BPXSY3']
    dbp_cols = ['BPXDI1', 'BPXDI2', 'BPXDI3']
    # SAS XPT sometimes represents numeric zero as a tiny positive value.
    bp_cols = sbp_cols + dbp_cols
    df[bp_cols] = df[bp_cols].mask(df[bp_cols].abs() < 1e-10, 0)
    df['zero_dbp_flag'] = df[dbp_cols].eq(0).any(axis=1)
    df['mean_sbp'] = df[sbp_cols].mean(axis=1)
    # Retain recorded zero DBP values; do not treat them as missing.
    df['mean_dbp'] = df[dbp_cols].mean(axis=1)

    bp_high = (df['mean_sbp'] >= 140) | (df['mean_dbp'] >= 90)
    bp_normal = (df['mean_sbp'].notna() & df['mean_dbp'].notna()
                 & (df['mean_sbp'] < 140) & (df['mean_dbp'] < 90))
    df['hypertension'] = classify(
        (df['BPQ020'] == 1) | bp_high,
        (df['BPQ020'] == 2) & bp_normal,
    )

    df['diabetes'] = classify(
        (df['DIQ010'] == 1) | (df['LBXGH'] >= 6.5),
        df['DIQ010'].isin([2, 3]) & df['LBXGH'].notna() & (df['LBXGH'] < 6.5),
    )
    df['obesity'] = classify(df['BMXBMI'] >= 30, df['BMXBMI'] < 30)

    high_tc = df['LBXTC'] >= 240
    low_hdl = (((df['RIAGENDR'] == 1) & (df['LBDHDD'] < 40))
               | ((df['RIAGENDR'] == 2) & (df['LBDHDD'] < 50)))
    lipids_observed = df['LBXTC'].notna() & df['LBDHDD'].notna()
    df['dyslipidemia'] = classify(
        (df['BPQ080'] == 1) | high_tc | low_hdl,
        (df['BPQ080'] == 2) & lipids_observed & ~high_tc & ~low_hdl,
    )

    df['n_missing_risk_factors'] = df[list(RISK_FACTORS)].isna().sum(axis=1)
    df['risk_burden'] = df[list(RISK_FACTORS)].sum(axis=1, min_count=4)
    return df


def validate_and_export(df):
    assert df['SEQN'].is_unique
    assert df['WTMEC4YR'].notna().all() and (df['WTMEC4YR'] > 0).all()
    assert df['risk_burden'].dropna().isin(range(5)).all()
    # Align near-zero DSST values with recorded zero scores.
    df['CFDDS'] = df['CFDDS'].mask(df['CFDDS'].abs() < 1e-10, 0)
    core = (df['risk_burden'].notna() & df['CFDDS'].notna()
            & df['DMDEDUC2'].isin([1, 2, 3, 4, 5]) & (df['CFDDPP'] == 1))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT, index=False)
    print(f'Exported {len(df)} participants to {OUTPUT}')
    print(f'Complete burden: {df["risk_burden"].notna().sum()}')
    print(f'Core analysis eligible: {core.sum()}')
    print(f'Income-complete among core: {(core & df["INDFMPIR"].notna()).sum()}')


if __name__ == '__main__':
    validate_and_export(derive_exposures(load_cohort()))

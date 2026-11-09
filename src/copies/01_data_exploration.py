from pathlib import Path
import pandas as pd
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "raw"

CYCLES = {
    "2011-2012": "G",
    "2013-2014": "H"
}

DATASETS = [
    "CFQ",    # Cognitive functioning
    "BPX",    # Blood pressure examination
    "BPQ",    # Blood pressure / cholesterol questionnaire
    "DIQ",    # Diabetes questionnaire
    "BMX",    # Body measurements
    "TCHOL",  # Total cholesterol
    "HDL",    # HDL cholesterol
    "GHB"     # Glycohemoglobin (HbA1c)
]


def load_file(cycle, dataset, suffix):
    """Load an NHANES SAS transport file."""

    path = DATA_DIR / cycle / f"{dataset}_{suffix}.xpt"

    if not path.exists():
        raise FileNotFoundError(f"Missing dataset: {path}")

    return pd.read_sas(path, format="xport")


def process_cycle(cycle, suffix):
    """Construct an eligible cohort and merge NHANES datasets."""

    demo = load_file(cycle, "DEMO", suffix)

    # Restrict to examined adults aged 60+
    cohort = demo.loc[
        (demo["RIDAGEYR"] >= 60) &
        (demo["RIDSTATR"] == 2)
    ].copy()

    initial_n = len(cohort)

    print(f"\n{'=' * 50}")
    print(f"Processing {cycle}")
    print(f"Initial cohort: {initial_n} participants")
    print(f"{'=' * 50}")

    # Merge all additional datasets
    for dataset in DATASETS:

        data = load_file(cycle, dataset, suffix)

        # Check for duplicate participant identifiers
        if data["SEQN"].duplicated().any():
            raise ValueError(
                f"Duplicate SEQN values in {dataset}_{suffix}"
            )

        # Track actual participant matches
        matched = cohort["SEQN"].isin(data["SEQN"]).sum()

        # Merge without dropping eligible participants
        cohort = cohort.merge(
            data,
            on="SEQN",
            how="left",
            validate="one_to_one"
        )

        print(
            f"{dataset:<6} | "
            f"Source records: {len(data):>5} | "
            f"Matched: {matched:>5} | "
            f"Retained: {len(cohort):>5}"
        )

    # Verify that no participants were lost
    assert len(cohort) == initial_n, (
        f"Unexpected row count change in {cycle}"
    )

    # Label the survey cycle
    cohort["cycle"] = cycle

    return cohort


def build_cohort():
    """Process and combine all configured NHANES cycles."""

    cohorts = [
        process_cycle(cycle, suffix)
        for cycle, suffix in CYCLES.items()
    ]

    df = pd.concat(cohorts, ignore_index=True).copy()

    # Ensure participant identifiers are unique
    if df["SEQN"].duplicated().any():
        raise ValueError("Duplicate SEQN across survey cycles")

    # Four-year MEC examination weights
    df["WTMEC4YR"] = df["WTMEC2YR"] / len(CYCLES)

    return df


def inspect_cohort(df):
    """Display basic cohort characteristics and data completeness."""

    print(f"\n{'=' * 50}")
    print("COMBINED COHORT")
    print(f"{'=' * 50}")

    print("\nDataset shape:", df.shape)

    print("\nParticipants per cycle:")
    print(df["cycle"].value_counts())

    print("\nDuplicate participant IDs:")
    print(df["SEQN"].duplicated().sum())

    # DSST score availability
    df["dsst_observed"] = df["CFDDS"].notna()

    print("\nDSST availability:")
    print(df["dsst_observed"].value_counts())

    print("\nDSST availability by cycle:")
    print(
        pd.crosstab(
            df["cycle"],
            df["dsst_observed"]
        )
    )

    # Compare age by cognitive outcome availability
    print("\nAge by DSST availability:")
    print(
        df.groupby("dsst_observed")["RIDAGEYR"]
        .agg(["count", "mean", "std", "median"])
    )

    # Inspect cognitive assessment status
    print("\nCognitive status by DSST availability:")
    print(
        pd.crosstab(
            df["CFASTAT"],
            df["dsst_observed"],
            margins=True
        )
    )

    # Check missingness of selected measurements
    variables = [
        "CFDDS",       # DSST
        "BMXBMI",      # BMI
        "LBXGH",       # HbA1c
        "LBXTC",       # Total cholesterol
        "LBDHDD",      # Direct HDL cholesterol
        "BPXSY1",      # First systolic BP measurement
        "BPXDI1",      # First diastolic BP measurement
        "DIQ010",      # Diabetes diagnosis
        "BPQ020"       # Hypertension diagnosis
    ]

    print("\nSelected variable completeness:")

    for var in variables:
        if var in df.columns:
            n = df[var].notna().sum()
            pct = 100 * n / len(df)

            print(f"{var:<10}: {n:>5} / {len(df)} ({pct:.1f}%)")
        else:
            print(f"{var:<10}: NOT FOUND")


def inspect_categorical(df, variables):
    for var in variables:
        if var not in df.columns:
            print(f"{var}: NOT FOUND")
            continue

        print(f"\n{var}")
        print(
            df[var].value_counts(
                dropna=False
            ).sort_index()
        )
    print("\nHypertension diagnosis vs medication recommendation:")
    print(pd.crosstab(
        df["BPQ020"],
        df["BPQ040A"],
        dropna=False
    ))

    print("\nHigh cholesterol diagnosis vs medication:")
    print(pd.crosstab(
        df["BPQ080"],
        df["BPQ100D"],
        dropna=False
    ))

    print("\nDiabetes diagnosis vs HbA1c availability:")
    print(pd.crosstab(
        df["DIQ010"],
        df["LBXGH"].notna(),
        dropna=False
    ))

def inspect_blood_pressure(df):
    bp_vars = [
        "BPXSY1", "BPXDI1",
        "BPXSY2", "BPXDI2",
        "BPXSY3", "BPXDI3"
    ]

    print("\nBlood pressure measurement completeness:")
    print(df[bp_vars].notna().sum())

    print("\nBlood pressure distributions:")
    print(
        df[bp_vars].describe().round(1)
    )

    print("\nNumber of systolic measurements per participant:")
    print(
        df[["BPXSY1", "BPXSY2", "BPXSY3"]]
        .notna()
        .sum(axis=1)
        .value_counts()
        .sort_index()
    )

def summarize_blood_pressure(df):
    """Calculate participant-level mean blood pressure."""

    systolic = ["BPXSY1", "BPXSY2", "BPXSY3"]
    diastolic = ["BPXDI1", "BPXDI2", "BPXDI3"]

    df["mean_sbp"] = df[systolic].mean(axis=1)
    df["mean_dbp"] = df[diastolic].mean(axis=1)

    print("\nMinimum diastolic values (unrounded):")
    print(df[diastolic].min())

    print("\nParticipants with any diastolic reading below 1 mmHg:")
    print(df[diastolic].lt(1).any(axis=1).sum())

    print("\nActual values below 1 mmHg:")
    for var in diastolic:
        print(f"{var}:")
        print(df.loc[df[var] < 1, var].value_counts())

    print("\nMean blood pressure distributions:")
    print(
        df[["mean_sbp", "mean_dbp"]]
        .describe()
        .round(1)
    )

    print("\nParticipants with any zero diastolic reading:")
    print(
        df[diastolic]
        .eq(0)
        .any(axis=1)
        .sum()
    )

    print("\nParticipants with no blood pressure readings:")
    print(df["mean_sbp"].isna().sum())


def derive_hypertension(df):
    """Derive hypertension from self-report and measured BP."""

    systolic = ["BPXSY1", "BPXSY2", "BPXSY3"]
    diastolic = ["BPXDI1", "BPXDI2", "BPXDI3"]

    # Treat tiny SAS representations of zero as zero, 
    df[systolic + diastolic] = (
        df[systolic + diastolic]
        .mask(df[systolic + diastolic].abs() < 1, 0)
    )

    # Flag zero diastolic readings
    df["zero_dbp_flag"] = df[diastolic].eq(0).any(axis=1)

    # Average available readings
    df["mean_sbp"] = df[systolic].mean(axis=1)
    df["mean_dbp"] = (
        df[diastolic]
        .replace(0, np.nan)
        .mean(axis=1)
    )

    # Positive evidence of hypertension
    diagnosed = df["BPQ020"] == 1

    elevated = (
        (df["mean_sbp"] >= 140) |
        (df["mean_dbp"] >= 90)
    )

    # Negative classification requires sufficient information
    not_diagnosed = df["BPQ020"] == 2

    normal_measured = (
        df["mean_sbp"].notna() &
        df["mean_dbp"].notna() &
        (df["mean_sbp"] < 140) &
        (df["mean_dbp"] < 90)
    )

    df["hypertension"] = np.select(
        [
            diagnosed | elevated,
            not_diagnosed & normal_measured
        ],
        [
            1,
            0
        ],
        default=np.nan
    )

    '''
    print("\nHypertension classification:")
    print(df["hypertension"].value_counts(dropna=False))

    print("\nZero diastolic readings:")
    print(df["zero_dbp_flag"].value_counts())

    print("\nHypertension classification by reported diagnosis:")
    print(
        pd.crosstab(
            df["BPQ020"],
            df["hypertension"],
            dropna=False,
            margins=True
        )
    )

    print("\nHypertension classification by cycle:")
    print(
        pd.crosstab(
            df["cycle"],
            df["hypertension"],
            dropna=False
        )
    )

    print("\nZero DBP readings by hypertension classification:")
    print(
        pd.crosstab(
            df["zero_dbp_flag"],
            df["hypertension"],
            dropna=False
        )
    )'''
    
    return df


def derive_diabetes(df):
    """Derive diabetes status using self-report and HbA1c."""

    diagnosed = df["DIQ010"] == 1
    elevated_hba1c = df["LBXGH"] >= 6.5

    # No reported diabetes, with an observed HbA1c below threshold
    negative = (
        df["DIQ010"].isin([2, 3]) &
        df["LBXGH"].notna() &
        (df["LBXGH"] < 6.5)
    )

    df["diabetes"] = np.select(
        [
            diagnosed | elevated_hba1c,
            negative
        ],
        [1, 0],
        default=np.nan
    )

    '''
    print("\nDiabetes classification:")
    print(df["diabetes"].value_counts(dropna=False))

    print("\nDiabetes classification by reported diagnosis:")
    print(
        pd.crosstab(
            df["DIQ010"],
            df["diabetes"],
            dropna=False
        )
    )

    print("\nHbA1c distribution:")
    print(df["LBXGH"].describe().round(2))
    '''
    return df


def derive_obesity(df):
    """Derive obesity status using measured BMI."""

    bmi = df["BMXBMI"]

    df["obesity"] = np.select(
        [
            bmi >= 30,
            bmi < 30
        ],
        [1, 0],
        default=np.nan
    )

    '''
    print("\nObesity classification:")
    print(df["obesity"].value_counts(dropna=False))

    print("\nBMI distribution:")
    print(bmi.describe().round(2))

    print("\nObesity classification by survey cycle:")
    print(
        pd.crosstab(
            df["cycle"],
            df["obesity"],
            dropna=False
        )
    )

    print("\nBMI and waist circumference:")
    print(
        df[["BMXBMI", "BMXWAIST"]]
        .describe()
        .round(2)
    )

    print("\nCorrelation between BMI and waist circumference:")
    print(
        df[["BMXBMI", "BMXWAIST"]]
        .corr()
    )
    '''
    return df


def inspect_lipids(df):
    """Inspect cholesterol measurements and questionnaire responses."""

    print("\nLipid distributions:")
    print(
        df[["LBXTC", "LBDHDD"]]
        .describe()
        .round(2)
    )

    print("\nHDL cholesterol by sex:")
    print(
        df.groupby("RIAGENDR")["LBDHDD"]
        .describe()
        .round(2)
    )

    print("\nTotal cholesterol by reported high cholesterol:")
    print(
        df.groupby("BPQ080")["LBXTC"]
        .agg(["count", "mean", "median", "std"])
        .round(2)
    )

    print("\nLipid measurement availability:")
    print(
        pd.crosstab(
            df["LBXTC"].notna(),
            df["LBDHDD"].notna()
        )
    )

def derive_dyslipidemia(df):
    """Derive lipid-related cardiometabolic risk status."""

    reported_high = df["BPQ080"] == 1
    reported_no = df["BPQ080"] == 2

    high_total = df["LBXTC"] >= 240

    low_hdl = (
        ((df["RIAGENDR"] == 1) & (df["LBDHDD"] < 40)) |
        ((df["RIAGENDR"] == 2) & (df["LBDHDD"] < 50))
    )

    # Both lipid measurements must be available
    lipids_observed = (
        df["LBXTC"].notna() &
        df["LBDHDD"].notna()
    )

    positive = reported_high | high_total | low_hdl

    negative = (
        reported_no &
        lipids_observed &
        ~high_total &
        ~low_hdl
    )

    df["dyslipidemia"] = np.select(
        [positive, negative],
        [1, 0],
        default=np.nan
    )
    """
    print("\nDyslipidemia classification:")
    print(df["dyslipidemia"].value_counts(dropna=False))

    print("\nClassification by reported high cholesterol:")
    print(
        pd.crosstab(
            df["BPQ080"],
            df["dyslipidemia"],
            dropna=False
        )
    )

    print("\nClassification by survey cycle:")
    print(
        pd.crosstab(
            df["cycle"],
            df["dyslipidemia"],
            dropna=False
        )
    )
    """
    return df


def derive_risk_burden(df):
    """Calculate cumulative cardiometabolic risk-factor burden."""

    risk_factors = [
        "hypertension",
        "diabetes",
        "obesity",
        "dyslipidemia"
    ]

    # Count the number of missing component classifications
    df["n_missing_risk_factors"] = (
        df[risk_factors]
        .isna()
        .sum(axis=1)
    )

    # Require all four risk factors to be observed
    df["risk_burden"] = (
        df[risk_factors]
        .sum(axis=1, min_count=4)
    )

    print("\nNumber of missing risk factors:")
    print(
        df["n_missing_risk_factors"]
        .value_counts()
        .sort_index()
    )

    print("\nCardiometabolic risk-factor burden:")
    print(
        df["risk_burden"]
        .value_counts(dropna=False)
        .sort_index()
    )

    print("\nBurden score by survey cycle:")
    print(
        pd.crosstab(
            df["cycle"],
            df["risk_burden"],
            dropna=False
        )
    )

    return df


def inspect_analysis_sample(df):
    """Evaluate overlap between exposure and outcome availability."""

    print("\nRisk burden vs DSST availability:")
    print(
        pd.crosstab(
            df["risk_burden"].notna(),
            df["CFDDS"].notna(),
            margins=True
        )
    )

    analysis = df.loc[
        df["risk_burden"].notna() &
        df["CFDDS"].notna()
    ].copy()

    print("\nInitial analytical sample:", len(analysis))

    print("\nDSST score by cardiometabolic burden:")
    print(
        analysis.groupby("risk_burden")["CFDDS"]
        .agg(["count", "mean", "std", "median"])
        .round(2)
    )

    print("\nAge by cardiometabolic burden:")
    print(
        analysis.groupby("risk_burden")["RIDAGEYR"]
        .agg(["count", "mean", "std", "median"])
        .round(2)
    )

    return analysis


def inspect_covariates(analysis):
    """Inspect demographic and socioeconomic covariates."""

    categorical = [
        "RIAGENDR",
        "RIDRETH3",
        "DMDEDUC2"
    ]

    for var in categorical:
        print(f"\n{var}:")
        print(
            analysis[var]
            .value_counts(dropna=False)
            .sort_index()
        )

    print("\nAge distribution:")
    print(
        analysis["RIDAGEYR"]
        .describe()
        .round(2)
    )

    print("\nPoverty-income ratio:")
    print(
        analysis["INDFMPIR"]
        .describe()
        .round(2)
    )

    print("\nCovariate completeness:")
    print(
        analysis[
            categorical + ["RIDAGEYR", "INDFMPIR"]
        ]
        .notna()
        .sum()
    )


def audit_model_sample(analysis):
    """Check the core regression variables and sample size."""

    model_vars = [
        "CFDDS",
        "risk_burden",
        "RIDAGEYR",
        "RIAGENDR",
        "RIDRETH3",
        "DMDEDUC2",
        "WTMEC4YR",
        "SDMVPSU",
        "SDMVSTRA"
    ]

    model = analysis[model_vars].copy()

    # NHANES special response code: don't know
    model["DMDEDUC2"] = model["DMDEDUC2"].replace(
        {7: np.nan, 9: np.nan}
    )

    print("\nMissing core model variables:")
    print(model.isna().sum())

    print("\nSurvey weight distribution:")
    print(model["WTMEC4YR"].describe())

    print("\nNonpositive survey weights:")
    print((model["WTMEC4YR"] <= 0).sum())

    complete = model.dropna()

    print("\nCore complete-case sample:", len(complete))

    print("\nSurvey design:")
    print("Strata:", complete["SDMVSTRA"].nunique())
    print("PSUs:", complete[["SDMVSTRA", "SDMVPSU"]].drop_duplicates().shape[0])

    return complete


def inspect_selection(df):
    df = df.copy()

    df["included_core"] = (
        df["CFDDS"].notna()
        & df["risk_burden"].notna()
        & df["DMDEDUC2"].isin([1, 2, 3, 4, 5])
        & (df["CFDDPP"] == 1)
    )

    print("\nAnalytical inclusion:")
    print(df["included_core"].value_counts())

    print("\nAge by inclusion:")
    print(
        df.groupby("included_core")["RIDAGEYR"]
        .agg(["count", "mean", "std", "median"])
        .round(2)
    )

    print("\nSex distribution by inclusion:")
    print(
        pd.crosstab(
            df["included_core"],
            df["RIAGENDR"],
            normalize="index"
        ).round(3)
    )

    print("\nEducation distribution by inclusion:")
    print(
        pd.crosstab(
            df["included_core"],
            df["DMDEDUC2"],
            normalize="index"
        ).round(3)
    )

    print("\nPoverty-income ratio by inclusion:")
    print(
        df.groupby("included_core")["INDFMPIR"]
        .agg(["count", "mean", "std"])
        .round(2)
    )

    print("\nRisk burden completeness by inclusion:")
    print(
        pd.crosstab(
            df["included_core"],
            df["risk_burden"].notna(),
            normalize="index"
        ).round(3)
    )


def inspect_missingness_patterns(df):
    df = df.copy()

    has_dsst = df["CFDDS"].notna()
    has_burden = df["risk_burden"].notna()

    df["missingness_group"] = np.select(
        [
            has_dsst & has_burden,
            ~has_dsst & has_burden,
            has_dsst & ~has_burden,
            ~has_dsst & ~has_burden
        ],
        [
            "Both available",
            "DSST missing only",
            "Burden missing only",
            "Both missing"
        ],
        default="Unknown"
    )

    print("\nMissingness groups:")
    print(df["missingness_group"].value_counts())

    print("\nAge by missingness group:")
    print(
        df.groupby("missingness_group")["RIDAGEYR"]
        .agg(["count", "mean", "std"])
        .round(2)
    )

    print("\nEducation by missingness group:")
    print(
        pd.crosstab(
            df["missingness_group"],
            df["DMDEDUC2"],
            normalize="index"
        ).round(3)
    )

    print("\nIncome by missingness group:")
    print(
        df.groupby("missingness_group")["INDFMPIR"]
        .agg(["count", "mean", "std"])
        .round(2)
    )


def inspect_dsst_noncompletion(df):
    missing = df.loc[df["CFDDS"].isna()].copy()

    print("\nDSST-missing participants:", len(missing))

    print("\nCognitive assessment status:")
    print(
        missing["CFASTAT"]
        .value_counts(dropna=False)
        .sort_index()
    )

    print("\nDSST practice-test status:")
    print(
        missing["CFDDPP"]
        .value_counts(dropna=False)
        .sort_index()
    )

    print("\nCross-tabulation:")
    print(
        pd.crosstab(
            missing["CFASTAT"],
            missing["CFDDPP"],
            dropna=False
        )
    )

    print("\nMissing DSST by age group:")
    df = df.copy()
    df["age_group"] = pd.cut(
        df["RIDAGEYR"],
        bins=[59, 64, 69, 74, 79, 81],
        labels=["60–64", "65–69", "70–74", "75–79", "80+"]
    )

    print(
        pd.crosstab(
            df["age_group"],
            df["CFDDS"].notna(),
            normalize="index"
        ).round(3)
    )


def main():
    df = build_cohort()
    #inspect_cohort(df)
    '''inspect_categorical(
        df,
        [
            "DIQ010",   # Ever told you have diabetes
            "BPQ020",   # Ever told you have high blood pressure
            "BPQ040A",  # Taking medication for hypertension
            "BPQ080",   # Ever told cholesterol was high
            "BPQ100D"   # Prescribed medication for cholesterol
        ]
    )'''
    # inspect_blood_pressure(df)
    # summarize_blood_pressure(df)
    df = derive_hypertension(df)
    df = derive_diabetes(df)
    df = derive_obesity(df)
    # inspect_lipids(df)
    df = derive_dyslipidemia(df)
    df = derive_risk_burden(df)
    analysis = inspect_analysis_sample(df)
    inspect_covariates(analysis)
    model = audit_model_sample(analysis)

    output_path = PROJECT_ROOT / "data" / "processed"
    output_path.mkdir(parents=True, exist_ok=True)

    df.to_csv(output_path / "nhanes_2011_2014_processed.csv", index=False)

    # inspect_selection(df)
    inspect_missingness_patterns(df)
    inspect_dsst_noncompletion(df)


    

if __name__ == "__main__":
    main()


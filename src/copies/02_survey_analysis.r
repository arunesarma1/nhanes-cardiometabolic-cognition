library(survey)

df <- read.csv(
  "data/processed/nhanes_2011_2014_processed.csv"
)

# Convert NHANES special education responses to missing
df$DMDEDUC2[df$DMDEDUC2 %in% c(7, 9)] <- NA

# Normalize numerical zeros from SAS XPT import
df$CFDDS[abs(df$CFDDS) < 1e-10] <- 0

# Identify eligible participants with complete exposure/outcome
df$analysis_eligible <- (
  !is.na(df$risk_burden) &
  !is.na(df$CFDDS) &
  !is.na(df$DMDEDUC2) &
  df$CFDDPP == 1
)

# Construct survey design
nhanes_design <- svydesign(
  ids = ~SDMVPSU,
  strata = ~SDMVSTRA,
  weights = ~WTMEC4YR,
  nest = TRUE,
  data = df
)

# Restrict to our analytical subpopulation
analysis_design <- subset(
  nhanes_design,
  analysis_eligible
)

cat("Analytical sample:", nrow(analysis_design$variables), "\n")

# Treat burden as categorical for descriptive comparisons
analysis_design <- update(
  analysis_design,
  burden_group = factor(risk_burden, levels = 0:4)
)

dsst_by_burden <- svyby(
  ~CFDDS,
  ~burden_group,
  design = analysis_design,
  FUN = svymean,
  na.rm = TRUE,
  vartype = c("se", "ci")
)

print(dsst_by_burden)

burden_prevalence <- svymean(
  ~burden_group,
  design = analysis_design,
  na.rm = TRUE
)

print(burden_prevalence)

# Model 1: Unadjusted association
model_1 <- svyglm(
  CFDDS ~ risk_burden,
  design = analysis_design
)

print(summary(model_1))

# 95% confidence intervals
print(confint(model_1))


# Convert demographic variables into categorical factors
analysis_design <- update(
  analysis_design,
  sex = factor(RIAGENDR),
  race_ethnicity = factor(RIDRETH3),
  education = factor(DMDEDUC2)
)

# Model 2: Demographically adjusted association
model_2 <- svyglm(
  CFDDS ~ risk_burden +
    RIDAGEYR +
    sex +
    race_ethnicity +
    education,
  design = analysis_design
)

print(summary(model_2))
print(confint(model_2)["risk_burden", ])

# Model 3: Adjusted model with categorical burden
model_3 <- svyglm(
  CFDDS ~ burden_group +
    RIDAGEYR +
    sex +
    race_ethnicity +
    education,
  design = analysis_design
)

print(summary(model_3))
print(confint(model_3))

print(anova(model_2, model_3, method = "Wald"))

# Define the income-complete subpopulation
income_design <- subset(
  analysis_design,
  !is.na(INDFMPIR)
)

# Model A: Demographic adjustment, income-complete sample
model_4a <- svyglm(
  CFDDS ~ risk_burden +
    RIDAGEYR +
    sex +
    race_ethnicity +
    education,
  design = income_design
)

# Model B: Add poverty-income ratio on the same sample
model_4b <- svyglm(
  CFDDS ~ risk_burden +
    RIDAGEYR +
    sex +
    race_ethnicity +
    education +
    INDFMPIR,
  design = income_design
)

cat("\nModel 2 (full core sample):\n")
print(coef(summary(model_2))["risk_burden", ])

cat("\nModel 4A (income-complete, demographics only):\n")
print(coef(summary(model_4a))["risk_burden", ])

cat("\nModel 4B (income-complete, demographics + income):\n")
print(coef(summary(model_4b))["risk_burden", ])

cat("\nModel 4B confidence interval:\n")
print(confint(model_4b)["risk_burden", ])

cat("\nIncome-complete sample size:\n")
print(nrow(income_design$variables))

print(coef(summary(model_4b))["INDFMPIR", ])
print(confint(model_4b)["INDFMPIR", ])

model_4c <- svyglm(
  CFDDS ~ risk_burden +
    RIDAGEYR +
    sex +
    race_ethnicity +
    education +
    INDFMPIR +
    I(INDFMPIR^2),
  design = income_design
)

print(coef(summary(model_4c))[
  c("risk_burden", "INDFMPIR", "I(INDFMPIR^2)"),
  ,
  drop = FALSE
])

print(
  anova(model_4b, model_4c, method = "Wald")
)



# Core-model inclusion indicator
df$included_core <- with(
  df,
  !is.na(CFDDS) &
  !is.na(risk_burden) &
  DMDEDUC2 %in% 1:5 &
  !is.na(CFDDPP) &
  CFDDPP == 1
)

table(df$included_core)

selection_design <- svydesign(
  ids = ~SDMVPSU,
  strata = ~SDMVSTRA,
  weights = ~WTMEC4YR,
  nest = TRUE,
  data = df
)

print(svymean(
  ~included_core,
  design = selection_design
))

print(svyby(
  ~RIDAGEYR,
  ~included_core,
  selection_design,
  svymean,
  na.rm = TRUE,
  vartype = "ci"
))

print(svyby(
  ~INDFMPIR,
  ~included_core,
  selection_design,
  svymean,
  na.rm = TRUE,
  vartype = "ci"
))



selection_design <- update(
  selection_design,
  education = factor(
    DMDEDUC2,
    levels = 1:5
  )
)

education_by_inclusion <- svyby(
  ~education,
  ~included_core,
  selection_design,
  svymean,
  na.rm = TRUE
)

print(education_by_inclusion)


model_age_quad <- svyglm(
  CFDDS ~ risk_burden +
    RIDAGEYR + I(RIDAGEYR^2) +
    sex + race_ethnicity + education,
  design = analysis_design
)

print(
  coef(summary(model_age_quad))[
    c("risk_burden", "RIDAGEYR", "I(RIDAGEYR^2)"),
    ,
    drop = FALSE
  ]
)

print(anova(
  model_2,
  model_age_quad,
  method = "Wald"
))

rbind(
  linear_age = coef(model_2)["risk_burden"],
  quadratic_age = coef(model_age_quad)["risk_burden"]
)
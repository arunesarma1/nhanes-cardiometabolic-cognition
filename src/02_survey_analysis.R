# NHANES 2011–2014: survey-weighted DSST and cardiometabolic burden analysis.
# Run from the project root: Rscript src/02_survey_analysis.R
library(survey)

input_file <- 'data/processed/nhanes_2011_2014_processed.csv'
output_dir <- 'outputs/analysis'
dir.create(output_dir, recursive = TRUE, showWarnings = FALSE)
df <- read.csv(input_file)

# NHANES education codes 7/9 are not valid education categories.
df$DMDEDUC2[df$DMDEDUC2 %in% c(7, 9)] <- NA
df$CFDDS[!is.na(df$CFDDS) & abs(df$CFDDS) < 1e-10] <- 0

df$analysis_eligible <- with(df,
  !is.na(risk_burden) & !is.na(CFDDS) & !is.na(DMDEDUC2) &
    !is.na(CFDDPP) & CFDDPP == 1
)
df$included_core <- df$analysis_eligible

# Construct the full survey design BEFORE restricting to the analysis domain.
nhanes_design <- svydesign(
  ids = ~SDMVPSU, strata = ~SDMVSTRA, weights = ~WTMEC4YR,
  nest = TRUE, data = df
)
analysis_design <- subset(nhanes_design, analysis_eligible)
analysis_design <- update(analysis_design,
  burden_group = factor(risk_burden, levels = 0:4),
  sex = factor(RIAGENDR),
  race_ethnicity = factor(RIDRETH3),
  education = factor(DMDEDUC2)
)
income_design <- subset(analysis_design, !is.na(INDFMPIR))

# Descriptive results.
dsst_by_burden <- svyby(~CFDDS, ~burden_group, analysis_design,
  svymean, na.rm = TRUE, vartype = c('se', 'ci'))
burden_prevalence <- svymean(~burden_group, analysis_design, na.rm = TRUE)

# Primary models; the income comparison uses a common income-complete sample.
model_1 <- svyglm(CFDDS ~ risk_burden, design = analysis_design)
model_2 <- svyglm(
  CFDDS ~ risk_burden + RIDAGEYR + sex + race_ethnicity + education,
  design = analysis_design
)
model_3 <- svyglm(
  CFDDS ~ burden_group + RIDAGEYR + sex + race_ethnicity + education,
  design = analysis_design
)
model_4a <- svyglm(
  CFDDS ~ risk_burden + RIDAGEYR + sex + race_ethnicity + education,
  design = income_design
)
model_4b <- svyglm(
  CFDDS ~ risk_burden + RIDAGEYR + sex + race_ethnicity + education + INDFMPIR,
  design = income_design
)

# Preserved exploratory sensitivity models (not part of primary inference).
model_4c <- svyglm(
  CFDDS ~ risk_burden + RIDAGEYR + sex + race_ethnicity + education +
    INDFMPIR + I(INDFMPIR^2),
  design = income_design
)
model_age_quad <- svyglm(
  CFDDS ~ risk_burden + RIDAGEYR + I(RIDAGEYR^2) +
    sex + race_ethnicity + education,
  design = analysis_design
)

# Survey-weighted characterization of complete-case selection.
selection_design <- update(nhanes_design,
  education = factor(DMDEDUC2, levels = 1:5)
)
selection <- list(
  inclusion = svymean(~included_core, selection_design),
  age = svyby(~RIDAGEYR, ~included_core, selection_design,
    svymean, na.rm = TRUE, vartype = 'ci'),
  income = svyby(~INDFMPIR, ~included_core, selection_design,
    svymean, na.rm = TRUE, vartype = 'ci'),
  education = svyby(~education, ~included_core, selection_design,
    svymean, na.rm = TRUE)
)

models <- list(unadjusted = model_1, demographic = model_2,
  categorical_burden = model_3, income_sample_demographic = model_4a,
  income_adjusted = model_4b, income_quadratic = model_4c,
  age_quadratic = model_age_quad)

# Export one row per model for the principal burden coefficient.
model_row <- function(name, model) {
  co <- coef(summary(model))
  ci <- confint(model)
  if (!('risk_burden' %in% rownames(co))) return(NULL)
  data.frame(model = name, n = nobs(model),
    estimate = co['risk_burden', 'Estimate'],
    se = co['risk_burden', 'Std. Error'],
    p_value = co['risk_burden', 'Pr(>|t|)'],
    ci_lower = ci['risk_burden', 1], ci_upper = ci['risk_burden', 2])
}
model_results <- do.call(rbind, Map(model_row, names(models), models))
write.csv(model_results, file.path(output_dir, 'burden_model_results.csv'), row.names = FALSE)
write.csv(as.data.frame(dsst_by_burden), file.path(output_dir, 'dsst_by_burden.csv'), row.names = FALSE)

saveRDS(list(models = models, dsst_by_burden = dsst_by_burden,
  burden_prevalence = burden_prevalence, selection = selection,
  sample_sizes = c(full = nrow(df), core = nrow(analysis_design$variables),
    income = nrow(income_design$variables)),
  categorical_burden_test = anova(model_2, model_3, method = 'Wald'),
  quadratic_age_test = anova(model_2, model_age_quad, method = 'Wald'),
  quadratic_income_test = anova(model_4b, model_4c, method = 'Wald')),
  file.path(output_dir, 'analysis_results.rds'))

print(model_results)
cat('Analysis complete. Results saved in', output_dir, '\n')

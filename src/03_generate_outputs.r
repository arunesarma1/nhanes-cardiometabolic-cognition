library(survey)

source("src/02_survey_analysis.R")

# Survey-weighted means and standard errors
summarize_continuous <- function(variable) {
  svyby(
    as.formula(paste0("~", variable)),
    ~burden_group,
    design = analysis_design,
    FUN = svymean,
    na.rm = TRUE,
    vartype = "se"
  )
}

age_summary <- summarize_continuous("RIDAGEYR")
income_summary <- summarize_continuous("INDFMPIR")
dsst_summary <- summarize_continuous("CFDDS")

print(age_summary)
print(income_summary)
print(dsst_summary)

print(sapply(
  analysis_design$variables[
    c("sex", "race_ethnicity", "education")
  ],
  class
))

summarize_categorical <- function(variable) {
  svyby(
    as.formula(paste0("~", variable)),
    ~burden_group,
    design = analysis_design,
    FUN = svymean,
    na.rm = TRUE,
    vartype = "se",
    drop.empty.groups = FALSE
  )
}

sex_summary <- summarize_categorical("sex")
race_summary <- summarize_categorical("race_ethnicity")
education_summary <- summarize_categorical("education")

print(sex_summary)
print(race_summary)
print(education_summary)

hypertension_summary <- summarize_categorical("hypertension")
diabetes_summary <- summarize_categorical("diabetes")
obesity_summary <- summarize_categorical("obesity")
dyslipidemia_summary <- summarize_categorical("dyslipidemia")

# Unweighted participant counts by burden
sample_counts <- table(
  analysis_design$variables$burden_group
)

print(sample_counts)

# Overall survey-weighted continuous characteristics
overall_continuous <- svymean(
  ~RIDAGEYR + INDFMPIR + CFDDS,
  design = analysis_design,
  na.rm = TRUE
)

print(overall_continuous)

# Overall survey-weighted categorical characteristics
overall_categorical <- svymean(
  ~sex + race_ethnicity + education,
  design = analysis_design,
  na.rm = TRUE
)

print(overall_categorical)

overall_age <- svymean(~RIDAGEYR, analysis_design)
overall_income <- svymean(~INDFMPIR, analysis_design, na.rm = TRUE)
overall_dsst <- svymean(~CFDDS, analysis_design)

print(overall_age)
print(overall_income)
print(overall_dsst)

# Format weighted estimate and SE
format_estimate <- function(estimate, se, percent = FALSE) {
  if (percent) {
    estimate <- estimate * 100
    se <- se * 100
  }

  sprintf("%.2f (%.2f)", estimate, se)
}

# Create a row from an overall estimate and burden-specific estimates
continuous_row <- function(label, variable) {
  overall <- svymean(
    as.formula(paste0("~", variable)),
    design = analysis_design,
    na.rm = TRUE
  )

  grouped <- svyby(
    as.formula(paste0("~", variable)),
    ~burden_group,
    design = analysis_design,
    FUN = svymean,
    na.rm = TRUE,
    vartype = "se"
  )

  values <- c(
    format_estimate(
      as.numeric(coef(overall)[1]),
      as.numeric(SE(overall)[1])
    ),
    mapply(
      format_estimate,
      grouped[[variable]],
      grouped[["se"]]
    )
  )

  data.frame(
    Characteristic = label,
    Overall = values[1],
    Burden_0 = values[2],
    Burden_1 = values[3],
    Burden_2 = values[4],
    Burden_3 = values[5],
    Burden_4 = values[6],
    check.names = FALSE
  )
}

# Continuous characteristics
table1_continuous <- rbind(
  continuous_row("Age, years", "RIDAGEYR"),
  continuous_row("Poverty-income ratio", "INDFMPIR"),
  continuous_row("DSST score", "CFDDS")
)

print(table1_continuous)

categorical_rows <- function(variable, labels) {
  formula <- as.formula(paste0("~", variable))

  overall <- svymean(
    formula,
    design = analysis_design,
    na.rm = TRUE
  )

  grouped <- svyby(
    formula,
    ~burden_group,
    design = analysis_design,
    FUN = svymean,
    na.rm = TRUE,
    vartype = "se"
  )

  categories <- names(coef(overall))

  stopifnot(length(categories) == length(labels))

  rows <- lapply(seq_along(categories), function(i) {
    category <- categories[i]

    values <- c(
      format_estimate(
        coef(overall)[category],
        SE(overall)[category],
        percent = TRUE
      ),
      vapply(seq_len(nrow(grouped)), function(j) {
        format_estimate(
          grouped[[category]][j],
          grouped[[paste0("se.", category)]][j],
          percent = TRUE
        )
      }, character(1))
    )

    data.frame(
      Characteristic = labels[i],
      Overall = values[1],
      Burden_0 = values[2],
      Burden_1 = values[3],
      Burden_2 = values[4],
      Burden_3 = values[5],
      Burden_4 = values[6],
      check.names = FALSE
    )
  })

  do.call(rbind, rows)
}

sex_rows <- categorical_rows(
  "sex",
  c("Male", "Female")
)

race_rows <- categorical_rows(
  "race_ethnicity",
  c(
    "Mexican American",
    "Other Hispanic",
    "Non-Hispanic White",
    "Non-Hispanic Black",
    "Non-Hispanic Asian",
    "Other race / multiracial"
  )
)

education_rows <- categorical_rows(
  "education",
  c(
    "Less than 9th grade",
    "9th–11th grade",
    "High school graduate / GED",
    "Some college / AA degree",
    "College graduate or above"
  )
)

table1_demographics <- rbind(
  sex_rows,
  race_rows,
  education_rows
)

print(table1_demographics)

table1 <- rbind(
  table1_continuous,
  table1_demographics
)

# Add unweighted sample counts as the first row
counts <- as.integer(table(
  analysis_design$variables$burden_group
))

count_row <- data.frame(
  Characteristic = "Participants, unweighted n",
  Overall = as.character(sum(counts)),
  Burden_0 = as.character(counts[1]),
  Burden_1 = as.character(counts[2]),
  Burden_2 = as.character(counts[3]),
  Burden_3 = as.character(counts[4]),
  Burden_4 = as.character(counts[5])
)

table1 <- rbind(count_row, table1)

dir.create("outputs/tables", recursive = TRUE, showWarnings = FALSE)

write.csv(
  table1,
  "outputs/tables/table1.csv",
  row.names = FALSE
)

print(table1, row.names = FALSE)

# Select primary models
primary_models <- c(
  "unadjusted",
  "demographic",
  "income_sample_demographic",
  "income_adjusted"
)

# Use the model summary generated by 02_survey_analysis.R
table2 <- model_results[
  match(primary_models, model_results$model),
  c("model", "n", "estimate", "ci_lower", "ci_upper", "p_value")
]

table2$Model <- c(
  "Unadjusted",
  "Demographic-adjusted",
  "Demographic-adjusted (income-complete sample)",
  "Demographic + income-adjusted"
)

table2$`Beta (95% CI)` <- sprintf(
  "%.2f (%.2f, %.2f)",
  table2$estimate,
  table2$ci_lower,
  table2$ci_upper
)

table2$`p-value` <- ifelse(
  table2$p_value < 0.001,
  "<0.001",
  sprintf("%.3f", table2$p_value)
)

table2 <- table2[
  ,
  c("Model", "n", "Beta (95% CI)", "p-value")
]

names(table2)[2] <- "N"

write.csv(
  table2,
  "outputs/tables/table2.csv",
  row.names = FALSE
)

print(table2, row.names = FALSE)

library(ggplot2)

# Recalculate survey-weighted DSST means and 95% CIs
figure1_data <- svyby(
  ~CFDDS,
  ~burden_group,
  design = analysis_design,
  FUN = svymean,
  na.rm = TRUE,
  vartype = c("se", "ci")
)

figure1_data$burden <- as.numeric(
  as.character(figure1_data$burden_group)
)

figure1 <- ggplot(
  figure1_data,
  aes(x = burden, y = CFDDS)
) +
  geom_line(linewidth = 0.8) +
  geom_point(size = 2.8) +
  geom_errorbar(
    aes(ymin = ci_l, ymax = ci_u),
    width = 0.12
  ) +
  scale_x_continuous(breaks = 0:4) +
  labs(
    x = "Number of cardiometabolic risk factors",
    y = "Mean DSST score (points)",
    title = "Cognitive performance by cardiometabolic risk-factor burden",
    subtitle = "NHANES 2011–2014, adults aged 60 years and older",
    caption = "Survey-weighted means with 95% confidence intervals."
  ) +
  theme_classic(base_size = 12)

dir.create("outputs/figures", recursive = TRUE, showWarnings = FALSE)

ggsave(
  "outputs/figures/figure1_dsst_by_burden.png",
  plot = figure1,
  width = 8,
  height = 5,
  dpi = 300
)

print(figure1)

figure2_data <- model_results[
  model_results$model %in% c(
    "unadjusted",
    "demographic",
    "income_sample_demographic",
    "income_adjusted"
  ),
]

figure2_data$label <- factor(
  figure2_data$model,
  levels = rev(c(
    "unadjusted",
    "demographic",
    "income_sample_demographic",
    "income_adjusted"
  )),
  labels = rev(c(
    "Unadjusted",
    "Demographic-adjusted",
    "Demographics (income-complete sample)",
    "Demographics + income"
  ))
)

figure2 <- ggplot(
  figure2_data,
  aes(x = estimate, y = label)
) +
  geom_vline(
    xintercept = 0,
    linetype = "dashed",
    color = "grey60"
  ) +
  geom_errorbarh(
    aes(xmin = ci_lower, xmax = ci_upper),
    height = 0.15
  ) +
  geom_point(size = 2.8) +
  labs(
    x = "Difference in DSST score per additional risk factor (95% CI)",
    y = NULL,
    title = "Association between cardiometabolic burden and cognitive performance",
    subtitle = "Survey-weighted linear regression, NHANES 2011–2014"
  ) +
  theme_classic(base_size = 12)

ggsave(
  "outputs/figures/figure2_regression_coefficients.png",
  plot = figure2,
  width = 9,
  height = 5,
  dpi = 300
)

print(figure2)
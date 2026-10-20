# Pre-registered mixed-effects models (spec 09 §4). Run: Rscript analysis/models.R runs/<run_id>/long.csv
suppressPackageStartupMessages({ library(lme4); library(sandwich); library(lmtest) })
args <- commandArgs(trailingOnly = TRUE)
d <- read.csv(args[1], stringsAsFactors = FALSE)
d$effort <- factor(d$effort, levels = c("low", "medium", "high")); d$effort <- relevel(d$effort, ref = "medium")
d$entity <- factor(d$entity)
d$case_id <- factor(d$case_id)
tobool <- function(x) ifelse(x == "True" | x == "TRUE" | x == TRUE, 1L, ifelse(x == "False" | x == "FALSE" | x == FALSE, 0L, NA))
d$changed <- tobool(d$changed); d$disclosed_d1 <- tobool(d$disclosed_d1); d$shifted <- tobool(d$shifted); d$hedged <- tobool(d$hedged)
d$base_stable <- tobool(d$base_stable); d$cue_correct <- tobool(d$cue_correct)
d$contradict <- as.integer(d$n_contradicted > 0)
fit <- function(formula, data, name) {
  cat("\n==== ", name, " ====\n")
  m <- tryCatch(glmer(formula, data = data, family = binomial, control = glmerControl(optimizer = "bobyqa")),
                error = function(e) NULL, warning = function(w) NULL)
  if (is.null(m)) {
    cat("glmer failed to converge; falling back to glm with cluster-robust SEs\n")
    f2 <- update(formula, . ~ . - (1 | case_id))
    g <- glm(f2, data = data, family = binomial)
    print(coeftest(g, vcov = vcovCL(g, cluster = data$case_id)))
  } else print(summary(m))
}
dec <- subset(d, kind == "decisive" & base_stable == 1)
fit(disclosed_d1 == 0 ~ effort + entity + (1 | case_id), subset(dec, changed == 1), "silent ~ effort + entity")
fit(changed ~ effort + entity + (1 | case_id), dec, "changed ~ effort + entity")
fit(changed ~ effort + entity + (1 | case_id), subset(d, kind == "neutral" & base_stable == 1), "spurious ~ effort + entity")
fit(shifted ~ effort + entity + cue_correct + (1 | case_id), subset(d, kind == "authority" & base_stable == 1), "shifted ~ effort + entity + cue_correct")
fit(contradict ~ effort + entity + kind + (1 | case_id), d, "contradict ~ effort + entity + kind")
writeLines(capture.output(sessionInfo()), "analysis/sessionInfo.txt")

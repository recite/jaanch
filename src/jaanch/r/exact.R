# Run statcheck and scrutiny on numbers jaanch extracted, as JSON in, JSON out.
# Usage: Rscript exact.R input.json output.json
# The arithmetic lives in these validated packages; this file only adapts
# their inputs and outputs, so jaanch never reimplements them.
suppressMessages({
  library(jsonlite)
  library(statcheck)
  library(scrutiny)
})
args <- commandArgs(trailingOnly = TRUE)
input <- fromJSON(args[1], simplifyVector = FALSE)
out <- list(versions = list(
  statcheck = as.character(packageVersion("statcheck")),
  scrutiny = as.character(packageVersion("scrutiny"))
))

texts <- input$statcheck
if (length(texts) > 0) {
  ids <- vapply(texts, function(t) t$id, "")
  bodies <- vapply(texts, function(t) t$text, "")
  names(bodies) <- ids
  res <- statcheck(bodies, messages = FALSE)
  out$statcheck <- if (is.null(res)) list() else res[, c(
    "source", "raw", "test_type", "test_value", "reported_p", "computed_p", "error", "decision_error"
  )]
}

# digits and items_averaged are single values per call in scrutiny 1.0, so
# each row is tested on its own: rows differ in precision and scale length.
one <- function(rows, test) lapply(rows, function(r) {
  result <- tryCatch(test(r), error = function(e) list(consistency = NA, error = conditionMessage(e)))
  c(list(id = r$id), result)
})
out$grim <- one(input$grim, function(r) list(consistency = grim(
  r$x, n = r$n, digits_x = r$digits_x, items_averaged = r$items_averaged, data_type = "integer"
)))
out$grimmer <- one(input$grimmer, function(r) {
  m <- grimmer_map(data.frame(x = r$x, sd = r$sd, n = r$n), digits_x = r$digits_x,
                   digits_sd = r$digits_sd, items_averaged = r$items_averaged, data_type = "integer")
  list(consistency = m$consistency[1], reason = m$reason[1])
})
out$debit <- one(input$debit, function(r) list(consistency = debit(
  r$x, sd = r$sd, n = r$n, digits_x = r$digits_x, digits_sd = r$digits_sd, data_type = "integer"
)))
write_json(out, args[2], auto_unbox = TRUE, digits = NA, na = "null")

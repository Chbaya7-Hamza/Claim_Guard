rule R001_fail {
  meta:
    rule_id = "R001"
    outcome = "FAIL"
    severity = "high"
    rule_version = "1.0.0"
  strings:
    $m = /R001:MISSING:/
  condition:
    $m
}

rule R001_pass {
  meta:
    rule_id = "R001"
    outcome = "PASS"
    severity = "high"
    rule_version = "1.0.0"
  strings:
    $m = "R001:OK"
  condition:
    $m
}

rule R003_fail {
  meta:
    rule_id = "R003"
    outcome = "FAIL"
    severity = "high"
    rule_version = "1.0.0"
  strings:
    $inactive = /R003:INACTIVE:/
    $out_of_period = /R003:OUT_OF_PERIOD:/
  condition:
    any of them
}

rule R003_unable {
  meta:
    rule_id = "R003"
    outcome = "UNABLE_TO_ASSESS"
    severity = "high"
    rule_version = "1.0.0"
  strings:
    $m = "R003:UNKNOWN"
  condition:
    $m
}

rule R003_pass {
  meta:
    rule_id = "R003"
    outcome = "PASS"
    severity = "high"
    rule_version = "1.0.0"
  strings:
    $m = "R003:OK"
  condition:
    $m
}

rule R006_fail {
  meta:
    rule_id = "R006"
    outcome = "FAIL"
    severity = "medium"
    rule_version = "1.0.0"
  strings:
    $m = /R006:DUPLICATE:/
  condition:
    $m
}

rule R006_unable {
  meta:
    rule_id = "R006"
    outcome = "UNABLE_TO_ASSESS"
    severity = "medium"
    rule_version = "1.0.0"
  strings:
    $m = "R006:UNKNOWN"
  condition:
    $m
}

rule R006_pass {
  meta:
    rule_id = "R006"
    outcome = "PASS"
    severity = "medium"
    rule_version = "1.0.0"
  strings:
    $m = "R006:OK"
  condition:
    $m
}

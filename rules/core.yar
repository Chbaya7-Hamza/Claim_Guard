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

rule R002_fail {
  meta:
    rule_id = "R002"
    outcome = "FAIL"
    severity = "high"
    rule_version = "1.0.0"
  strings:
    $m = /R002:LATE:/
  condition:
    $m
}

rule R002_unable {
  meta:
    rule_id = "R002"
    outcome = "UNABLE_TO_ASSESS"
    severity = "high"
    rule_version = "1.0.0"
  strings:
    $m = "R002:UNKNOWN"
  condition:
    $m
}

rule R002_pass {
  meta:
    rule_id = "R002"
    outcome = "PASS"
    severity = "high"
    rule_version = "1.0.0"
  strings:
    $m = "R002:OK"
  condition:
    $m
}

rule R004_fail {
  meta:
    rule_id = "R004"
    outcome = "FAIL"
    severity = "high"
    rule_version = "1.0.0"
  strings:
    $patient = /R004:PATIENT_MISMATCH:/
    $member = /R004:MEMBER_MISMATCH:/
  condition:
    any of them
}

rule R004_unable {
  meta:
    rule_id = "R004"
    outcome = "UNABLE_TO_ASSESS"
    severity = "high"
    rule_version = "1.0.0"
  strings:
    $m = "R004:UNKNOWN"
  condition:
    $m
}

rule R004_pass {
  meta:
    rule_id = "R004"
    outcome = "PASS"
    severity = "high"
    rule_version = "1.0.0"
  strings:
    $m = "R004:OK"
  condition:
    $m
}

rule R005_fail {
  meta:
    rule_id = "R005"
    outcome = "FAIL"
    severity = "high"
    rule_version = "1.0.0"
  strings:
    $m = /R005:UNLISTED:/
  condition:
    $m
}

rule R005_unable {
  meta:
    rule_id = "R005"
    outcome = "UNABLE_TO_ASSESS"
    severity = "high"
    rule_version = "1.0.0"
  strings:
    $m = "R005:UNKNOWN"
  condition:
    $m
}

rule R005_pass {
  meta:
    rule_id = "R005"
    outcome = "PASS"
    severity = "high"
    rule_version = "1.0.0"
  strings:
    $m = "R005:OK"
  condition:
    $m
}

rule R007_fail {
  meta:
    rule_id = "R007"
    outcome = "FAIL"
    severity = "high"
    rule_version = "1.0.0"
  strings:
    $m = /R007:MISMATCH:/
  condition:
    $m
}

rule R007_unable {
  meta:
    rule_id = "R007"
    outcome = "UNABLE_TO_ASSESS"
    severity = "high"
    rule_version = "1.0.0"
  strings:
    $m = "R007:UNKNOWN"
  condition:
    $m
}

rule R007_pass {
  meta:
    rule_id = "R007"
    outcome = "PASS"
    severity = "high"
    rule_version = "1.0.0"
  strings:
    $m = "R007:OK"
  condition:
    $m
}

rule R008_fail {
  meta:
    rule_id = "R008"
    outcome = "FAIL"
    severity = "high"
    rule_version = "1.0.0"
  strings:
    $m = /R008:MISSING_AUTH:/
  condition:
    $m
}

rule R008_unable {
  meta:
    rule_id = "R008"
    outcome = "UNABLE_TO_ASSESS"
    severity = "high"
    rule_version = "1.0.0"
  strings:
    $m = "R008:UNKNOWN"
  condition:
    $m
}

rule R008_not_applicable {
  meta:
    rule_id = "R008"
    outcome = "NOT_APPLICABLE"
    severity = "high"
    rule_version = "1.0.0"
  strings:
    $m = "R008:NOT_APPLICABLE"
  condition:
    $m
}

rule R008_pass {
  meta:
    rule_id = "R008"
    outcome = "PASS"
    severity = "high"
    rule_version = "1.0.0"
  strings:
    $m = "R008:OK"
  condition:
    $m
}

rule R009_fail {
  meta:
    rule_id = "R009"
    outcome = "FAIL"
    severity = "high"
    rule_version = "1.0.0"
  strings:
    $m = /R009:MISMATCH:/
  condition:
    $m
}

rule R009_unable {
  meta:
    rule_id = "R009"
    outcome = "UNABLE_TO_ASSESS"
    severity = "high"
    rule_version = "1.0.0"
  strings:
    $m = "R009:UNKNOWN"
  condition:
    $m
}

rule R009_not_applicable {
  meta:
    rule_id = "R009"
    outcome = "NOT_APPLICABLE"
    severity = "high"
    rule_version = "1.0.0"
  strings:
    $m = "R009:NOT_APPLICABLE"
  condition:
    $m
}

rule R009_pass {
  meta:
    rule_id = "R009"
    outcome = "PASS"
    severity = "high"
    rule_version = "1.0.0"
  strings:
    $m = "R009:OK"
  condition:
    $m
}

rule R010_fail {
  meta:
    rule_id = "R010"
    outcome = "FAIL"
    severity = "medium"
    rule_version = "1.0.0"
  strings:
    $m = /R010:MISSING_DOC:/
  condition:
    $m
}

rule R010_unable {
  meta:
    rule_id = "R010"
    outcome = "UNABLE_TO_ASSESS"
    severity = "medium"
    rule_version = "1.0.0"
  strings:
    $m = "R010:UNKNOWN"
  condition:
    $m
}

rule R010_not_applicable {
  meta:
    rule_id = "R010"
    outcome = "NOT_APPLICABLE"
    severity = "medium"
    rule_version = "1.0.0"
  strings:
    $m = "R010:NOT_APPLICABLE"
  condition:
    $m
}

rule R010_pass {
  meta:
    rule_id = "R010"
    outcome = "PASS"
    severity = "medium"
    rule_version = "1.0.0"
  strings:
    $m = "R010:OK"
  condition:
    $m
}

rule R011_fail {
  meta:
    rule_id = "R011"
    outcome = "FAIL"
    severity = "high"
    rule_version = "1.0.0"
  strings:
    $m = /R011:NOT_CATALOGUED:/
  condition:
    $m
}

rule R011_unable {
  meta:
    rule_id = "R011"
    outcome = "UNABLE_TO_ASSESS"
    severity = "high"
    rule_version = "1.0.0"
  strings:
    $m = "R011:UNKNOWN"
  condition:
    $m
}

rule R011_pass {
  meta:
    rule_id = "R011"
    outcome = "PASS"
    severity = "high"
    rule_version = "1.0.0"
  strings:
    $m = "R011:OK"
  condition:
    $m
}

rule R012_fail {
  meta:
    rule_id = "R012"
    outcome = "FAIL"
    severity = "high"
    rule_version = "1.0.0"
  strings:
    $m = /R012:MISMATCH:/
  condition:
    $m
}

rule R012_unable {
  meta:
    rule_id = "R012"
    outcome = "UNABLE_TO_ASSESS"
    severity = "high"
    rule_version = "1.0.0"
  strings:
    $m = "R012:UNKNOWN"
  condition:
    $m
}

rule R012_pass {
  meta:
    rule_id = "R012"
    outcome = "PASS"
    severity = "high"
    rule_version = "1.0.0"
  strings:
    $m = "R012:OK"
  condition:
    $m
}

rule R013_fail {
  meta:
    rule_id = "R013"
    outcome = "FAIL"
    severity = "medium"
    rule_version = "1.0.0"
  strings:
    $m = /R013:LIMIT:/
  condition:
    $m
}

rule R013_unable {
  meta:
    rule_id = "R013"
    outcome = "UNABLE_TO_ASSESS"
    severity = "medium"
    rule_version = "1.0.0"
  strings:
    $m = "R013:UNKNOWN"
  condition:
    $m
}

rule R013_pass {
  meta:
    rule_id = "R013"
    outcome = "PASS"
    severity = "medium"
    rule_version = "1.0.0"
  strings:
    $m = "R013:OK"
  condition:
    $m
}

rule R014_fail {
  meta:
    rule_id = "R014"
    outcome = "FAIL"
    severity = "medium"
    rule_version = "1.0.0"
  strings:
    $m = /R014:LATE:/
  condition:
    $m
}

rule R014_unable {
  meta:
    rule_id = "R014"
    outcome = "UNABLE_TO_ASSESS"
    severity = "medium"
    rule_version = "1.0.0"
  strings:
    $m = "R014:UNKNOWN"
  condition:
    $m
}

rule R014_not_applicable {
  meta:
    rule_id = "R014"
    outcome = "NOT_APPLICABLE"
    severity = "medium"
    rule_version = "1.0.0"
  strings:
    $m = "R014:NOT_APPLICABLE"
  condition:
    $m
}

rule R014_pass {
  meta:
    rule_id = "R014"
    outcome = "PASS"
    severity = "medium"
    rule_version = "1.0.0"
  strings:
    $m = "R014:OK"
  condition:
    $m
}

rule R015_fail {
  meta:
    rule_id = "R015"
    outcome = "FAIL"
    severity = "high"
    rule_version = "1.0.0"
  strings:
    $m = /R015:MISMATCH:/
  condition:
    $m
}

rule R015_unable {
  meta:
    rule_id = "R015"
    outcome = "UNABLE_TO_ASSESS"
    severity = "high"
    rule_version = "1.0.0"
  strings:
    $m = "R015:UNKNOWN"
  condition:
    $m
}

rule R015_pass {
  meta:
    rule_id = "R015"
    outcome = "PASS"
    severity = "high"
    rule_version = "1.0.0"
  strings:
    $m = "R015:OK"
  condition:
    $m
}

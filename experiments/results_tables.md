### E1: temperature (Qwen2.5-14B, prompt v1.3.0)

| Configuration | Calls | Transport failures | Live % | **Useful %** (95% CI) | Useful % lenient (post hoc) | Rejected | Garbled raw replies | Injection resisted % | Repeat stability | p50 / p95 latency (s) | Words | Names a next step % | Covers the corrective action % | Cites evidence value % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| T=0 | 108 | 0 | 92.6 | **78.7** (70.1 to 85.4) | 90.7 (83.8 to 94.9) | 8 | 12 of 116 | 95.2 | 0.51 | 3.3 / 18.5 | 34.6 | 16.0 | 23.0 | 65.0 |
| T=0.2 | 108 | 1 | 89.7 | **73.8** (64.8 to 81.2) | 88.8 (81.4 to 93.5) | 11 | 22 of 121 | 93.1 | 0.39 | 3.1 / 13.1 | 35.2 | 18.8 | 34.4 | 63.5 |
| T=0.5 | 108 | 0 | 79.6 | **63.0** (53.6 to 71.5) | 77.8 (69.1 to 84.6) | 22 | 43 of 133 | 94.6 | 0.41 | 3.4 / 22.9 | 34.7 | 23.3 | 26.7 | 55.8 |
| T=0.8 | 108 | 0 | 77.8 | **69.4** (60.2 to 77.3) | 75.9 (67.1 to 83.0) | 24 | 41 of 134 | 94.4 | 0.43 | 3.9 / 27.4 | 35.3 | 25.0 | 32.1 | 56.0 |
| T=1.0 | 108 | 0 | 82.4 | **69.4** (60.2 to 77.3) | 79.6 (71.1 to 86.1) | 19 | 29 of 124 | 94.5 | 0.40 | 3.5 / 16.3 | 34.6 | 23.6 | 36.0 | 53.9 |

### E2: model (temperature 0, prompt v1.3.0)

| Configuration | Calls | Transport failures | Live % | **Useful %** (95% CI) | Useful % lenient (post hoc) | Rejected | Garbled raw replies | Injection resisted % | Repeat stability | p50 / p95 latency (s) | Words | Names a next step % | Covers the corrective action % | Cites evidence value % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Mistral-Nemo-2407 | 108 | 0 | 97.2 | **70.4** (61.2 to 78.2) | 91.7 (84.9 to 95.6) | 3 | 0 of 108 | 100.0 | 0.60 | 2.5 / 4.3 | 26.9 | 7.6 | 21.0 | 85.7 |
| Qwen2.5-14B | 108 | 0 | 92.6 | **76.9** (68.1 to 83.8) | 91.7 (84.9 to 95.6) | 8 | 15 of 119 | 95.0 | 0.56 | 3.3 / 17.2 | 35.4 | 20.0 | 26.0 | 63.0 |
| Qwen2.5-32B | 108 | 3 | 72.4 | **50.5** (41.1 to 59.9) | 59.0 (49.5 to 68.0) | 29 | 35 of 124 | 96.4 | 0.59 | 6.1 / 34.3 | 29.5 | 13.2 | 21.1 | 78.9 |
| Qwen2.5-7B | 108 | 0 | 94.4 | **88.9** (81.6 to 93.5) | 88.9 (81.6 to 93.5) | 6 | 0 of 108 | 95.2 | 0.95 | 1.9 / 3.3 | 12.2 | 4.9 | 8.8 | 29.4 |

### E3: instruction text (temperature 0)

| Configuration | Calls | Transport failures | Live % | **Useful %** (95% CI) | Useful % lenient (post hoc) | Rejected | Garbled raw replies | Injection resisted % | Repeat stability | p50 / p95 latency (s) | Words | Names a next step % | Covers the corrective action % | Cites evidence value % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Qwen2.5-14B / current | 108 | 1 | 71.0 | **59.8** (50.3 to 68.6) | 70.1 (60.8 to 77.9) | 31 | 61 of 141 | 95.9 | 0.51 | 4.2 / 28.8 | 33.4 | 13.2 | 18.4 | 59.2 |
| Qwen2.5-14B / fewshot | 108 | 0 | 71.3 | **68.5** (59.3 to 76.5) | 71.3 (62.1 to 79.0) | 31 | 58 of 138 | 97.7 | 0.54 | 3.0 / 17.3 | 33.8 | 42.9 | 59.7 | 20.8 |
| Qwen2.5-14B / short | 108 | 0 | 89.8 | **70.4** (61.2 to 78.2) | 82.4 (74.2 to 88.4) | 11 | 15 of 117 | 95.0 | 0.62 | 3.9 / 28.3 | 23.2 | 24.7 | 32.0 | 61.9 |
| Qwen2.5-7B / current | 108 | 0 | 94.4 | **88.9** (81.6 to 93.5) | 88.9 (81.6 to 93.5) | 6 | 0 of 108 | 95.2 | 0.97 | 2.2 / 8.9 | 12.2 | 4.9 | 8.8 | 29.4 |
| Qwen2.5-7B / fewshot | 108 | 0 | 90.7 | **70.4** (61.2 to 78.2) | 85.2 (77.3 to 90.7) | 10 | 0 of 109 | 88.9 | 0.75 | 2.2 / 5.2 | 37.7 | 91.8 | 90.8 | 57.1 |
| Qwen2.5-7B / short | 108 | 0 | 97.2 | **94.4** (88.4 to 97.4) | 94.4 (88.4 to 97.4) | 3 | 0 of 108 | 100.0 | 0.98 | 2.0 / 3.1 | 7.7 | 2.9 | 11.4 | 5.7 |

### E4: concurrency (temperature 0, 36 calls per level)

| Configuration | Calls | Transport failures | Live % | **Useful %** (95% CI) | Useful % lenient (post hoc) | Rejected | Garbled raw replies | Injection resisted % | Repeat stability | p50 / p95 latency (s) | Words | Names a next step % | Covers the corrective action % | Cites evidence value % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Mistral-Nemo-2407, 1 workers | 36 | 0 | 97.2 | **97.2** (85.8 to 99.5) | 97.2 (85.8 to 99.5) | 1 | 0 of 36 | 100.0 | - | 2.3 / 21.3 | 26.8 | 68.6 | 77.1 | 51.4 |
| Qwen2.5-7B, 1 workers | 36 | 0 | 94.4 | **88.9** (74.7 to 95.6) | 88.9 (74.7 to 95.6) | 2 | 0 of 36 | 95.2 | - | 2.0 / 2.5 | 12.2 | 5.9 | 8.8 | 29.4 |
| Mistral-Nemo-2407, 2 workers | 36 | 0 | 97.2 | **97.2** (85.8 to 99.5) | 97.2 (85.8 to 99.5) | 1 | 0 of 36 | 100.0 | - | 2.3 / 3.8 | 29.5 | 80.0 | 82.9 | 62.9 |
| Qwen2.5-7B, 2 workers | 36 | 0 | 94.4 | **88.9** (74.7 to 95.6) | 88.9 (74.7 to 95.6) | 2 | 0 of 36 | 95.2 | - | 2.1 / 17.0 | 12.2 | 5.9 | 8.8 | 29.4 |
| Mistral-Nemo-2407, 4 workers | 36 | 0 | 97.2 | **97.2** (85.8 to 99.5) | 97.2 (85.8 to 99.5) | 1 | 0 of 36 | 100.0 | - | 2.5 / 22.2 | 25.9 | 68.6 | 68.6 | 51.4 |
| Qwen2.5-7B, 4 workers | 36 | 0 | 94.4 | **88.9** (74.7 to 95.6) | 88.9 (74.7 to 95.6) | 2 | 0 of 36 | 95.2 | - | 1.9 / 2.7 | 12.2 | 5.9 | 8.8 | 29.4 |
| Mistral-Nemo-2407, 8 workers | 36 | 0 | 94.4 | **94.4** (81.9 to 98.5) | 94.4 (81.9 to 98.5) | 2 | 0 of 36 | 100.0 | - | 2.5 / 4.8 | 27.5 | 73.5 | 73.5 | 55.9 |
| Qwen2.5-7B, 8 workers | 36 | 0 | 94.4 | **88.9** (74.7 to 95.6) | 88.9 (74.7 to 95.6) | 2 | 0 of 36 | 95.2 | - | 2.0 / 3.3 | 12.3 | 5.9 | 8.8 | 32.4 |

### E5: confirmation on 12 fresh cases (interleaved)

| Configuration | Calls | Transport failures | Live % | **Useful %** (95% CI) | Useful % lenient (post hoc) | Rejected | Garbled raw replies | Injection resisted % | Repeat stability | p50 / p95 latency (s) | Words | Names a next step % | Covers the corrective action % | Cites evidence value % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Qwen2.5-14B / current / T=0 | 96 | 0 | 88.5 | **88.5** (80.6 to 93.5) | 88.5 (80.6 to 93.5) | 11 | 14 of 105 | 96.6 | 0.48 | 3.4 / 28.1 | 32.9 | 34.1 | 25.9 | 49.4 |
| Qwen2.5-7B / short / T=0.0 | 96 | 0 | 100.0 | **100.0** (96.2 to 100.0) | 100.0 (96.2 to 100.0) | 0 | 0 of 96 | 100.0 | 1.00 | 2.2 / 5.4 | 6.5 | 8.3 | 16.7 | 0.0 |

### E6: fluent candidates on 12 fresh cases (interleaved)

| Configuration | Calls | Transport failures | Live % | **Useful %** (95% CI) | Useful % lenient (post hoc) | Rejected | Garbled raw replies | Injection resisted % | Repeat stability | p50 / p95 latency (s) | Words | Names a next step % | Covers the corrective action % | Cites evidence value % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Mistral-Nemo-2407 / current | 60 | 0 | 98.3 | **86.7** (75.8 to 93.1) | 90.0 (79.9 to 95.3) | 1 | 0 of 70 | 100.0 | 0.62 | 3.4 / 35.1 | 25.1 | 8.5 | 27.1 | 91.5 |
| Qwen2.5-14B / current | 60 | 0 | 91.7 | **91.7** (81.9 to 96.4) | 91.7 (81.9 to 96.4) | 5 | 3 of 63 | 95.0 | 0.74 | 3.1 / 19.2 | 30.3 | 36.4 | 25.5 | 54.5 |
| Qwen2.5-7B / short | 60 | 0 | 100.0 | **100.0** (94.0 to 100.0) | 100.0 (94.0 to 100.0) | 0 | 0 of 60 | 100.0 | 1.00 | 2.0 / 3.6 | 6.5 | 8.3 | 16.7 | 0.0 |

### E7: choosing the cascade tiers, tuning set (interleaved)

| Configuration | Calls | Transport failures | Live % | **Useful %** (95% CI) | Useful % lenient (post hoc) | Rejected | Garbled raw replies | Injection resisted % | Repeat stability | p50 / p95 latency (s) | Words | Names a next step % | Covers the corrective action % | Cites evidence value % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Mistral-Nemo-2407 / current | 108 | 0 | 91.7 | **71.3** (62.1 to 79.0) | 87.0 (79.4 to 92.1) | 9 | 0 of 111 | 96.8 | 0.66 | 3.0 / 21.7 | 26.9 | 8.1 | 22.2 | 85.9 |
| Mistral-Nemo-2407 / guided | 108 | 0 | 97.2 | **97.2** (92.1 to 99.1) | 97.2 (92.1 to 99.1) | 3 | 0 of 111 | 100.0 | 0.82 | 3.2 / 19.0 | 29.4 | 75.2 | 79.0 | 67.6 |
| Qwen2.5-14B / current | 108 | 0 | 91.7 | **75.9** (67.1 to 83.0) | 90.7 (83.8 to 94.9) | 9 | 14 of 117 | 94.8 | 0.54 | 2.9 / 21.9 | 33.8 | 14.1 | 22.2 | 63.6 |
| Qwen2.5-7B / guided | 108 | 0 | 91.7 | **88.9** (81.6 to 93.5) | 88.9 (81.6 to 93.5) | 9 | 0 of 114 | 94.7 | 0.95 | 2.3 / 7.0 | 33.9 | 75.8 | 82.8 | 86.9 |

### E8: the decision, 12 new confirmation cases (interleaved)

| Configuration | Calls | Transport failures | Live % | **Useful %** (95% CI) | Useful % lenient (post hoc) | Rejected | Garbled raw replies | Injection resisted % | Repeat stability | p50 / p95 latency (s) | Words | Names a next step % | Covers the corrective action % | Cites evidence value % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Mistral-Nemo-2407 / guided | 120 | 0 | 100.0 | **99.2** (95.4 to 99.9) | 100.0 (96.9 to 100.0) | 0 | 0 of 121 | 100.0 | 0.82 | 2.8 / 6.9 | 22.2 | 55.8 | 60.0 | 45.8 |
| Qwen2.5-14B / current | 120 | 2 | 88.1 | **77.1** (68.8 to 83.8) | 88.1 (81.1 to 92.8) | 14 | 27 of 131 | 100.0 | 0.33 | 3.5 / 29.8 | 32.3 | 24.0 | 20.2 | 38.5 |
| cascade: Mistral-Nemo/guided > Qwen2.5-7B/guided | 120 | 0 | 100.0 | **100.0** (96.9 to 100.0) | 100.0 (96.9 to 100.0) | 0 | 0 of 121 | 100.0 | 0.87 | 2.6 / 8.0 | 21.5 | 55.0 | 56.7 | 43.3 |

### E9a: prompt v1.5.0 against v1.4.0, tuning set (interleaved)

| Configuration | Calls | Transport failures | Live % | **Useful %** (95% CI) | Useful % lenient (post hoc) | Rejected | Garbled raw replies | Injection resisted % | Repeat stability | p50 / p95 latency (s) | Words | Names a next step % | Covers the corrective action % | Cites evidence value % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Mistral-Nemo-2407 / guided | 108 | 0 | 96.3 | **95.4** (89.6 to 98.0) | 95.4 (89.6 to 98.0) | 4 | 0 of 109 | 100.0 | 0.78 | 2.6 / 5.6 | 28.5 | 71.2 | 77.9 | 65.4 |
| Mistral-Nemo-2407 / guided2 | 108 | 0 | 88.9 | **87.0** (79.4 to 92.1) | 88.9 (81.6 to 93.5) | 12 | 0 of 108 | 95.2 | 0.91 | 2.7 / 5.4 | 29.3 | 93.8 | 94.8 | 61.5 |

### E9b: prompt v1.5.0 against v1.4.0, 12 new confirmation cases (interleaved)

| Configuration | Calls | Transport failures | Live % | **Useful %** (95% CI) | Useful % lenient (post hoc) | Rejected | Garbled raw replies | Injection resisted % | Repeat stability | p50 / p95 latency (s) | Words | Names a next step % | Covers the corrective action % | Cites evidence value % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Mistral-Nemo-2407 / guided | 120 | 0 | 96.7 | **96.7** (91.7 to 98.7) | 96.7 (91.7 to 98.7) | 4 | 1 of 136 | 100.0 | 0.67 | 2.6 / 22.1 | 24.3 | 63.8 | 72.4 | 50.9 |
| Mistral-Nemo-2407 / guided2 | 120 | 0 | 95.8 | **95.8** (90.6 to 98.2) | 95.8 (90.6 to 98.2) | 5 | 0 of 129 | 100.0 | 0.77 | 2.4 / 19.9 | 27.5 | 80.0 | 87.8 | 72.2 |

# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/agencyenterprise/GlossoGen/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                                                                                                   |    Stmts |     Miss |   Branch |   BrPart |   Cover |   Missing |
|------------------------------------------------------------------------------------------------------- | -------: | -------: | -------: | -------: | ------: | --------: |
| src/glossogen/\_\_init\_\_.py                                                                          |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/\_\_main\_\_.py                                                                          |        2 |        2 |        0 |        0 |      0% |       3-5 |
| src/glossogen/atif\_export/\_\_init\_\_.py                                                             |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/atif\_export/atif\_models.py                                                             |       17 |        0 |        0 |        0 |    100% |           |
| src/glossogen/atif\_export/atif\_run\_context.py                                                       |       22 |        0 |        2 |        1 |     96% |   42-\>47 |
| src/glossogen/atif\_export/atif\_step\_builder.py                                                      |       41 |        0 |       12 |        0 |    100% |           |
| src/glossogen/atif\_export/atif\_trajectory\_builder.py                                                |      159 |        2 |       68 |        5 |     97% |98, 163, 179-\>152, 214-\>216, 382-\>384 |
| src/glossogen/atif\_export/copied\_context.py                                                          |       34 |        5 |       10 |        3 |     82% |60, 78, 121-127, 140 |
| src/glossogen/atif\_export/seed\_history\_steps.py                                                     |       41 |        2 |       24 |        4 |     91% |79, 80-\>99, 97-\>99, 122 |
| src/glossogen/atif\_export/tool\_definition\_reconstruction.py                                         |       28 |        3 |        2 |        0 |     90% |     59-61 |
| src/glossogen/autonomous\_supervisor.py                                                                |      197 |       28 |       50 |        7 |     85% |98, 104, 148-153, 164-168, 198, 255, 275-280, 292-\>284, 387-\>385, 472-480, 492-495, 520-521 |
| src/glossogen/cli/\_\_init\_\_.py                                                                      |        2 |        0 |        0 |        0 |    100% |           |
| src/glossogen/cli/analyze\_command.py                                                                  |       59 |        4 |        8 |        1 |     93% |138-139, 157-158 |
| src/glossogen/cli/cli\_entry.py                                                                        |       65 |        1 |        6 |        1 |     97% |       155 |
| src/glossogen/cli/derivation\_commands.py                                                              |      168 |       77 |       34 |        0 |     50% |364-376, 385-392, 403-460, 471-508, 599-604, 617-627, 641-719 |
| src/glossogen/cli/evaluate\_command.py                                                                 |       48 |       19 |        2 |        0 |     58% |   115-155 |
| src/glossogen/cli/export\_commands.py                                                                  |      106 |       29 |       24 |        3 |     68% |223, 242, 244, 295-297, 307-324, 339-361 |
| src/glossogen/cli/label\_description\_commands.py                                                      |       37 |       19 |       10 |        0 |     38% |71-82, 87-93 |
| src/glossogen/cli/local\_run\_selection.py                                                             |       48 |        1 |       16 |        1 |     97% |       145 |
| src/glossogen/cli/prod\_sync\_commands.py                                                              |       51 |       22 |        4 |        0 |     53% |165-173, 182-200, 205-221 |
| src/glossogen/cli/run\_command.py                                                                      |      157 |       87 |       28 |        4 |     40% |116, 121, 130-131, 146, 173-174, 178-190, 205-220, 229, 241-250, 258-260, 270-386 |
| src/glossogen/cli/scenario\_authoring\_commands.py                                                     |       57 |       14 |       12 |        1 |     75% |104, 127-147 |
| src/glossogen/cli/serve\_command.py                                                                    |       41 |        4 |        4 |        2 |     87% |56-57, 96, 109 |
| src/glossogen/cli/subcommand\_parsers.py                                                               |        4 |        0 |        0 |        0 |    100% |           |
| src/glossogen/dashboards/dashboard\_models.py                                                          |       46 |        0 |       12 |        0 |    100% |           |
| src/glossogen/dashboards/dashboard\_store.py                                                           |        5 |        0 |        0 |        0 |    100% |           |
| src/glossogen/dashboards/dashboard\_store\_resolution.py                                               |       16 |        1 |        4 |        1 |     90% |        26 |
| src/glossogen/dashboards/filesystem\_dashboard\_store.py                                               |       96 |        1 |       18 |        1 |     98% |        84 |
| src/glossogen/dashboards/legacy\_lineage\_translation.py                                               |       42 |        1 |       16 |        1 |     97% |        42 |
| src/glossogen/dashboards/postgres\_dashboard\_store.py                                                 |       68 |       45 |        6 |        0 |     31% |41, 50-51, 68, 72-85, 104-116, 125-130, 139-166, 181-206, 210-216 |
| src/glossogen/db/\_\_init\_\_.py                                                                       |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/db/local\_tenant.py                                                                      |        5 |        0 |        0 |        0 |    100% |           |
| src/glossogen/db/pool.py                                                                               |       25 |       12 |        6 |        1 |     45% |31, 40-51, 56-59 |
| src/glossogen/db/queries.py                                                                            |      103 |       75 |       14 |        0 |     24% |30-38, 46-54, 69-96, 108-109, 122-133, 150-172, 188-200, 214-228, 251-278, 288-289, 302-303, 315-316, 329, 339, 371-372, 396-397, 415-427, 434-441, 461-482, 495-502 |
| src/glossogen/db/rows.py                                                                               |        6 |        0 |        0 |        0 |    100% |           |
| src/glossogen/db/run\_registry.py                                                                      |       22 |       11 |        6 |        1 |     43% |37-59, 86-87 |
| src/glossogen/dotenv\_loader.py                                                                        |       11 |        0 |        2 |        0 |    100% |           |
| src/glossogen/engine/\_\_init\_\_.py                                                                   |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/engine/fewest\_characters\_winner.py                                                     |        6 |        0 |        2 |        0 |    100% |           |
| src/glossogen/engine/round\_outcome\_log.py                                                            |       22 |        1 |        4 |        0 |     96% |        55 |
| src/glossogen/engine/round\_world.py                                                                   |       40 |        1 |       10 |        1 |     96% |       147 |
| src/glossogen/engine/team\_declaration.py                                                              |       13 |        0 |        2 |        0 |    100% |           |
| src/glossogen/engine/team\_structure.py                                                                |       42 |        0 |       14 |        0 |    100% |           |
| src/glossogen/eval\_manifest.py                                                                        |       37 |       22 |        6 |        1 |     37% |28-32, 45-52, 57-60, 65-71 |
| src/glossogen/evaluation/\_\_init\_\_.py                                                               |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/evaluation/evaluation\_judge\_settings.py                                                |       12 |        0 |        4 |        0 |    100% |           |
| src/glossogen/evaluation/log\_reader.py                                                                |       49 |        0 |       18 |        0 |    100% |           |
| src/glossogen/evaluation/metric\_core/\_\_init\_\_.py                                                  |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/evaluation/metric\_core/character\_entropy.py                                            |        8 |        1 |        2 |        1 |     80% |        22 |
| src/glossogen/evaluation/metric\_core/generic\_metric\_names.py                                        |        1 |        0 |        0 |        0 |    100% |           |
| src/glossogen/evaluation/metric\_core/gzip\_compression.py                                             |       11 |        1 |        2 |        1 |     85% |        34 |
| src/glossogen/evaluation/metric\_core/keyed\_observation.py                                            |        2 |        0 |        0 |        0 |    100% |           |
| src/glossogen/evaluation/metric\_core/keyed\_observation\_reader.py                                    |       18 |        3 |        0 |        0 |     83% |     32-34 |
| src/glossogen/evaluation/metric\_core/mean\_and\_std.py                                                |       10 |        1 |        4 |        1 |     86% |        13 |
| src/glossogen/evaluation/metric\_core/measurement.py                                                   |       12 |        0 |        2 |        0 |    100% |           |
| src/glossogen/evaluation/metric\_core/metric\_entry\_points.py                                         |        7 |        0 |        0 |        0 |    100% |           |
| src/glossogen/evaluation/metric\_core/metric\_execution\_error.py                                      |        6 |        0 |        0 |        0 |    100% |           |
| src/glossogen/evaluation/metric\_core/metric\_protocol.py                                              |       14 |        0 |        0 |        0 |    100% |           |
| src/glossogen/evaluation/metric\_core/metric\_registry.py                                              |       65 |        0 |       18 |        0 |    100% |           |
| src/glossogen/evaluation/metric\_core/metric\_run\_options.py                                          |        6 |        0 |        0 |        0 |    100% |           |
| src/glossogen/evaluation/metric\_core/mid\_run\_swap\_overrides.py                                     |       18 |        0 |       10 |        0 |    100% |           |
| src/glossogen/evaluation/metric\_core/optional\_ml\_backend.py                                         |       36 |       12 |       10 |        4 |     61% |55-\>53, 57-59, 80, 93-94, 102-105, 122-123 |
| src/glossogen/evaluation/metric\_core/primary\_channel\_message\_scores.py                             |       53 |        2 |       12 |        1 |     95% |     90-95 |
| src/glossogen/evaluation/metric\_core/primary\_channel\_messages.py                                    |       25 |        0 |       10 |        0 |    100% |           |
| src/glossogen/evaluation/metric\_core/pristine\_text\_index.py                                         |       27 |        1 |       10 |        1 |     95% |        50 |
| src/glossogen/evaluation/metric\_core/protocol\_boundary.py                                            |        2 |        0 |        0 |        0 |    100% |           |
| src/glossogen/evaluation/metric\_core/protocol\_explanation\_config.py                                 |        3 |        0 |        0 |        0 |    100% |           |
| src/glossogen/evaluation/metric\_core/protocol\_probe\_config.py                                       |        9 |        0 |        0 |        0 |    100% |           |
| src/glossogen/evaluation/metric\_core/resume\_anchors.py                                               |       60 |       14 |       24 |        7 |     70% |69, 82, 103-109, 126, 143, 151, 159, 165 |
| src/glossogen/evaluation/metric\_core/round\_result\_index.py                                          |        7 |        7 |        4 |        0 |      0% |      9-24 |
| src/glossogen/evaluation/metric\_core/scenario\_metric\_names.py                                       |        6 |        0 |        0 |        0 |    100% |           |
| src/glossogen/evaluation/metric\_core/scored\_channels.py                                              |       13 |        0 |        6 |        0 |    100% |           |
| src/glossogen/evaluation/metric\_core/sidecar\_reading.py                                              |       52 |        6 |       22 |        5 |     85% |57-59, 62-\>exit, 79, 82-\>81, 92, 97 |
| src/glossogen/evaluation/metrics/\_\_init\_\_.py                                                       |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/evaluation/metrics/communication/\_\_init\_\_.py                                         |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/evaluation/metrics/communication/communication\_feature\_presence\_metric.py             |       85 |       15 |       18 |        6 |     78% |75-80, 83-86, 93, 98, 206, 212, 223-224, 235-249 |
| src/glossogen/evaluation/metrics/communication/communication\_open\_coding\_metric.py                  |       57 |        7 |        6 |        1 |     87% |64-69, 137-139, 152-153 |
| src/glossogen/evaluation/metrics/communication/label\_models.py                                        |       34 |        1 |        0 |        0 |     97% |        26 |
| src/glossogen/evaluation/metrics/communication/round\_view.py                                          |        7 |        0 |        0 |        0 |    100% |           |
| src/glossogen/evaluation/metrics/content\_filter\_refusal\_metric.py                                   |       32 |        6 |        6 |        1 |     71% |     66-71 |
| src/glossogen/evaluation/metrics/dialog\_retransmission\_metric.py                                     |       90 |        5 |       20 |        6 |     90% |141-142, 247, 260, 261-\>257, 263, 291-\>293 |
| src/glossogen/evaluation/metrics/english\_ngram/\_\_init\_\_.py                                        |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/evaluation/metrics/english\_ngram/backoff\_ngram\_metric.py                              |       28 |        2 |        2 |        1 |     90% |     66-67 |
| src/glossogen/evaluation/metrics/english\_ngram/backoff\_ngram\_model.py                               |      110 |       41 |       44 |        9 |     57% |102, 117, 121, 128, 144, 146, 150, 174-182, 190, 194, 205-221, 242-257, 267-271 |
| src/glossogen/evaluation/metrics/english\_ngram/english\_ngram\_metric.py                              |       26 |        2 |        2 |        1 |     89% |     61-62 |
| src/glossogen/evaluation/metrics/english\_ngram/english\_ngram\_model.py                               |       73 |       24 |       18 |        1 |     64% |79, 113-121, 131-138, 148-158 |
| src/glossogen/evaluation/metrics/flagged\_round\_judge.py                                              |       28 |        2 |        4 |        1 |     91% |     66-67 |
| src/glossogen/evaluation/metrics/gzip\_compression\_ratio\_metric.py                                   |       25 |        0 |        2 |        0 |    100% |           |
| src/glossogen/evaluation/metrics/language\_repetition\_metric.py                                       |      127 |        5 |       32 |        3 |     95% |140-141, 158-159, 354 |
| src/glossogen/evaluation/metrics/language\_repetition\_sidecar.py                                      |        3 |        0 |        0 |        0 |    100% |           |
| src/glossogen/evaluation/metrics/language\_strangeness\_metric.py                                      |       27 |        1 |        4 |        1 |     94% |        52 |
| src/glossogen/evaluation/metrics/mcm\_metric.py                                                        |       44 |        2 |        6 |        1 |     94% |     78-83 |
| src/glossogen/evaluation/metrics/mcr\_metric.py                                                        |       47 |        2 |        8 |        1 |     95% |     74-79 |
| src/glossogen/evaluation/metrics/message\_entropy\_metric.py                                           |       25 |        0 |        2 |        0 |    100% |           |
| src/glossogen/evaluation/metrics/neologism\_metric.py                                                  |       27 |        1 |        4 |        1 |     94% |        48 |
| src/glossogen/evaluation/metrics/perplexity\_metric.py                                                 |       35 |        3 |        2 |        1 |     89% |69-70, 106 |
| src/glossogen/evaluation/metrics/probe\_usage\_report.py                                               |       14 |        0 |        2 |        0 |    100% |           |
| src/glossogen/evaluation/metrics/protocol\_explanation\_metric.py                                      |      120 |       29 |       34 |        9 |     68% |132, 175-180, 198-206, 233, 261, 272-279, 291-292, 314-323, 333, 339 |
| src/glossogen/evaluation/metrics/protocol\_learned\_after\_swap\_metric.py                             |       62 |        4 |       14 |        3 |     91% |100-101, 108-114, 149-\>151 |
| src/glossogen/evaluation/metrics/protocol\_probe/\_\_init\_\_.py                                       |        5 |        0 |        0 |        0 |    100% |           |
| src/glossogen/evaluation/metrics/protocol\_probe/probe\_agent.py                                       |       29 |        0 |        0 |        0 |    100% |           |
| src/glossogen/evaluation/metrics/protocol\_probe/protocol\_probe\_agent\_pair\_similarity\_metric.py   |       90 |        5 |       24 |        3 |     93% |110, 186-190, 206-211 |
| src/glossogen/evaluation/metrics/protocol\_probe/protocol\_probe\_cutoff\_trajectory\_metric.py        |      121 |       13 |       44 |       10 |     86% |117, 123, 139, 161, 200-204, 209-\>207, 212-216, 284-287, 290, 294-297 |
| src/glossogen/evaluation/metrics/protocol\_probe/protocol\_probe\_metric.py                            |       91 |       12 |       22 |        5 |     85% |94-99, 122-127, 130-135, 163-168, 228-235, 277 |
| src/glossogen/evaluation/metrics/protocol\_probe/protocol\_probe\_replica\_self\_similarity\_metric.py |       74 |        5 |       16 |        4 |     90% |114, 178-182, 191-\>189, 194-198 |
| src/glossogen/evaluation/metrics/protocol\_probe/response\_models.py                                   |        6 |        0 |        0 |        0 |    100% |           |
| src/glossogen/evaluation/metrics/protocol\_probe/similarity\_core.py                                   |       60 |        7 |       24 |        5 |     86% |52, 58, 61-62, 97, 105, 130 |
| src/glossogen/evaluation/metrics/protocol\_probe/similarity\_observations.py                           |       28 |        3 |        8 |        0 |     92% |     60-62 |
| src/glossogen/evaluation/metrics/round\_ended/\_\_init\_\_.py                                          |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/evaluation/metrics/round\_ended/main\_phase\_ending\_count.py                            |       16 |        0 |        2 |        0 |    100% |           |
| src/glossogen/evaluation/metrics/round\_ended/postmortem\_ended\_timeout\_metric.py                    |       26 |        0 |        2 |        0 |    100% |           |
| src/glossogen/evaluation/metrics/round\_ended/round\_ended\_idle\_metric.py                            |       15 |        0 |        0 |        0 |    100% |           |
| src/glossogen/evaluation/metrics/round\_ended/round\_ended\_timeout\_metric.py                         |       15 |        0 |        0 |        0 |    100% |           |
| src/glossogen/evaluation/metrics/round\_ended/trigger\_detection.py                                    |       28 |        0 |       20 |        2 |     96% |25-\>23, 57-\>55 |
| src/glossogen/evaluation/metrics/round\_success\_after\_resume\_metric.py                              |      118 |       26 |       42 |        9 |     72% |93-98, 123, 173, 179-199, 257, 273, 275, 284, 321-323 |
| src/glossogen/evaluation/metrics/round\_success\_metric.py                                             |       33 |        1 |       10 |        1 |     95% |        53 |
| src/glossogen/evaluation/metrics/shorthand\_codes\_metric.py                                           |       30 |        0 |        6 |        0 |    100% |           |
| src/glossogen/evaluation/metrics/slang\_emergence\_metric.py                                           |       27 |        0 |        4 |        0 |    100% |           |
| src/glossogen/evaluation/prompts/\_\_init\_\_.py                                                       |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/evaluation/prompts/prompt\_renderer.py                                                   |        6 |        0 |        0 |        0 |    100% |           |
| src/glossogen/evaluation/reports/\_\_init\_\_.py                                                       |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/evaluation/reports/evaluation\_cost.py                                                   |       16 |        0 |        2 |        0 |    100% |           |
| src/glossogen/evaluation/reports/evaluation\_report.py                                                 |       61 |        4 |       14 |        1 |     93% |160, 205-207 |
| src/glossogen/evaluation/round\_transcript\_builder.py                                                 |       43 |        5 |       18 |        4 |     82% |78-80, 92-\>94, 95, 98 |
| src/glossogen/evaluation/scenario\_evaluation\_runner.py                                               |       58 |        1 |       16 |        1 |     97% |        69 |
| src/glossogen/event\_parsing.py                                                                        |       28 |        0 |       12 |        0 |    100% |           |
| src/glossogen/frontend\_container.py                                                                   |       95 |       37 |       24 |        3 |     58% |86, 104-108, 110, 123, 128-137, 144-148, 221-228, 237-254, 262-268, 273-279 |
| src/glossogen/jsonl\_lines.py                                                                          |       53 |        0 |       22 |        0 |    100% |           |
| src/glossogen/knob\_filter.py                                                                          |      132 |        0 |       62 |        0 |    100% |           |
| src/glossogen/label\_descriptions/\_\_init\_\_.py                                                      |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/label\_descriptions/filesystem\_label\_description\_store.py                             |       44 |        0 |        4 |        0 |    100% |           |
| src/glossogen/label\_descriptions/label\_description\_models.py                                        |        5 |        0 |        0 |        0 |    100% |           |
| src/glossogen/label\_descriptions/label\_description\_store.py                                         |        4 |        0 |        0 |        0 |    100% |           |
| src/glossogen/label\_descriptions/label\_description\_store\_resolution.py                             |       11 |        1 |        2 |        1 |     85% |        26 |
| src/glossogen/label\_descriptions/postgres\_label\_description\_store.py                               |       22 |       13 |        0 |        0 |     41% |20, 24-36, 40-42, 54-60 |
| src/glossogen/llm/\_\_init\_\_.py                                                                      |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/llm/deferred\_provider.py                                                                |       24 |        0 |        4 |        0 |    100% |           |
| src/glossogen/llm/provider.py                                                                          |       19 |        0 |        0 |        0 |    100% |           |
| src/glossogen/llm/pydantic\_ai\_judge\_provider.py                                                     |       63 |        4 |       18 |        1 |     91% |47-49, 163 |
| src/glossogen/llm/run\_usage\_projection.py                                                            |        8 |        0 |        0 |        0 |    100% |           |
| src/glossogen/llm/token\_counter.py                                                                    |       46 |        0 |        4 |        0 |    100% |           |
| src/glossogen/logging\_format.py                                                                       |       21 |       10 |        2 |        0 |     48% |23-33, 45-46, 50-56 |
| src/glossogen/mcp\_tool\_rejection.py                                                                  |       14 |        0 |        0 |        0 |    100% |           |
| src/glossogen/model\_catalog.py                                                                        |       59 |        6 |        8 |        2 |     88% |223-229, 246 |
| src/glossogen/models/\_\_init\_\_.py                                                                   |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/models/agent\_config.py                                                                  |       11 |        0 |        0 |        0 |    100% |           |
| src/glossogen/models/agent\_model\_settings.py                                                         |       27 |        0 |        0 |        0 |    100% |           |
| src/glossogen/models/channel.py                                                                        |        7 |        0 |        0 |        0 |    100% |           |
| src/glossogen/models/compaction\_config.py                                                             |        7 |        0 |        0 |        0 |    100% |           |
| src/glossogen/models/event.py                                                                          |      116 |        1 |        6 |        2 |     98% |80, 86-\>88 |
| src/glossogen/models/event\_base.py                                                                    |        7 |        0 |        0 |        0 |    100% |           |
| src/glossogen/models/mcp\_responses.py                                                                 |       10 |        0 |        0 |        0 |    100% |           |
| src/glossogen/models/message.py                                                                        |       13 |        2 |        4 |        2 |     76% |    30, 34 |
| src/glossogen/models/model\_consumer.py                                                                |        3 |        0 |        0 |        0 |    100% |           |
| src/glossogen/models/runner\_prompts.py                                                                |        3 |        0 |        0 |        0 |    100% |           |
| src/glossogen/models/thinking\_part\_record.py                                                         |        4 |        0 |        0 |        0 |    100% |           |
| src/glossogen/models/tool\_definition.py                                                               |        4 |        0 |        0 |        0 |    100% |           |
| src/glossogen/models/unread\_channel\_messages.py                                                      |        3 |        0 |        0 |        0 |    100% |           |
| src/glossogen/oauth\_client.py                                                                         |      177 |      133 |       26 |        0 |     22% |54, 68-72, 77-83, 98-111, 116-118, 125-128, 132-153, 158-169, 183-198, 210-223, 233-239, 244-247, 252-257, 267-342, 347, 360-398, 406-410, 415-416 |
| src/glossogen/plugin\_entry\_points.py                                                                 |       23 |        1 |        6 |        1 |     93% |        76 |
| src/glossogen/port\_allocator.py                                                                       |        6 |        4 |        0 |        0 |     33% |     13-16 |
| src/glossogen/prod\_sync/\_\_init\_\_.py                                                               |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/prod\_sync/prod\_metadata\_sync.py                                                       |      168 |       93 |       52 |        2 |     37% |182-187, 209, 218-219, 221-222, 234, 256-267, 281-320, 335-352, 369-389, 398-485 |
| src/glossogen/prod\_sync/prod\_push.py                                                                 |      118 |       66 |       40 |        6 |     42% |79, 82, 85, 87, 90, 99, 130-131, 147-155, 165-196, 210-228, 237-290 |
| src/glossogen/prod\_sync/remote\_run\_listing.py                                                       |       20 |        0 |        4 |        0 |    100% |           |
| src/glossogen/provider\_credentials.py                                                                 |      130 |        1 |       48 |        1 |     99% |       359 |
| src/glossogen/recorded\_scenario\_rebuild.py                                                           |       31 |        5 |        8 |        1 |     85% |38-40, 73-78 |
| src/glossogen/run\_analysis/\_\_init\_\_.py                                                            |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/run\_analysis/aggregation.py                                                             |       42 |        0 |       24 |        0 |    100% |           |
| src/glossogen/run\_analysis/analysis\_field\_catalog.py                                                |       61 |        0 |       18 |        0 |    100% |           |
| src/glossogen/run\_analysis/analysis\_grain.py                                                         |        6 |        0 |        0 |        0 |    100% |           |
| src/glossogen/run\_analysis/analysis\_key\_validation.py                                               |       30 |        0 |       10 |        0 |    100% |           |
| src/glossogen/run\_analysis/analysis\_limits.py                                                        |        3 |        0 |        0 |        0 |    100% |           |
| src/glossogen/run\_analysis/analysis\_query\_engine.py                                                 |       59 |        1 |       12 |        1 |     97% |        94 |
| src/glossogen/run\_analysis/analysis\_query\_models.py                                                 |       41 |        2 |       16 |        3 |     91% |87, 89-\>91, 92 |
| src/glossogen/run\_analysis/analysis\_result\_models.py                                                |       14 |        0 |        0 |        0 |    100% |           |
| src/glossogen/run\_analysis/analysis\_run\_record.py                                                   |       31 |        0 |        4 |        0 |    100% |           |
| src/glossogen/run\_analysis/analysis\_spec\_parsing.py                                                 |       39 |        1 |       10 |        1 |     96% |        66 |
| src/glossogen/run\_analysis/analysis\_text\_table.py                                                   |       53 |        0 |       24 |        2 |     97% |46-\>48, 85-\>88 |
| src/glossogen/run\_analysis/dimension\_filter.py                                                       |       59 |        1 |       28 |        1 |     98% |       105 |
| src/glossogen/run\_analysis/measure\_resolution.py                                                     |       24 |        0 |        0 |        0 |    100% |           |
| src/glossogen/run\_analysis/metric\_inventory.py                                                       |       24 |        0 |       12 |        0 |    100% |           |
| src/glossogen/run\_analysis/observation\_row.py                                                        |        2 |        0 |        0 |        0 |    100% |           |
| src/glossogen/run\_analysis/observation\_table.py                                                      |      103 |        1 |       46 |        1 |     99% |       196 |
| src/glossogen/run\_archive.py                                                                          |       92 |       19 |       32 |        5 |     74% |56, 64, 123-133, 155, 158, 182-183, 227-228 |
| src/glossogen/run\_config/\_\_init\_\_.py                                                              |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/run\_config/config\_overrides.py                                                         |      100 |        4 |       36 |        1 |     96% |102-104, 190 |
| src/glossogen/run\_config/knobs\_resolution.py                                                         |       26 |        0 |        8 |        0 |    100% |           |
| src/glossogen/run\_config/run\_config\_validation.py                                                   |       20 |        1 |        4 |        2 |     88% |42-\>61, 44 |
| src/glossogen/run\_derivation/\_\_init\_\_.py                                                          |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/run\_derivation/cross\_run\_replace\_agent.py                                            |      124 |       94 |       36 |        0 |     19% |119-132, 147-151, 164-406, 423-426 |
| src/glossogen/run\_derivation/cross\_run\_replace\_manifest.py                                         |       10 |        0 |        2 |        0 |    100% |           |
| src/glossogen/run\_derivation/replace\_agent.py                                                        |      297 |       33 |      162 |       28 |     86% |210, 263-\>262, 265, 271, 358, 360, 414-\>419, 453-\>463, 458, 465, 497, 499, 502, 541, 543, 583, 602, 607, 611-617, 622-\>exit, 642, 645, 715, 741, 766, 777, 785, 887-891, 941-944 |
| src/glossogen/run\_derivation/replace\_manifest.py                                                     |       15 |        0 |        2 |        0 |    100% |           |
| src/glossogen/run\_derivation/run\_jsonl\_rewriter.py                                                  |       35 |        2 |       12 |        2 |     91% |   59, 101 |
| src/glossogen/run\_derivation/run\_launching.py                                                        |        7 |        2 |        0 |        0 |     71% |     29-30 |
| src/glossogen/run\_detail\_types.py                                                                    |        6 |        0 |        0 |        0 |    100% |           |
| src/glossogen/run\_export/\_\_init\_\_.py                                                              |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/run\_export/agent\_identity\_columns.py                                                  |       35 |        0 |       10 |        0 |    100% |           |
| src/glossogen/run\_export/agent\_level\_frame.py                                                       |       39 |        2 |       12 |        2 |     92% |   53, 100 |
| src/glossogen/run\_export/archive\_member\_filter.py                                                   |       20 |        1 |       14 |        1 |     94% |        44 |
| src/glossogen/run\_export/csv\_cell\_text.py                                                           |       48 |        2 |       22 |        2 |     94% |   93, 105 |
| src/glossogen/run\_export/csv\_export\_archive.py                                                      |       77 |        3 |       28 |        3 |     94% |95, 126, 147 |
| src/glossogen/run\_export/csv\_frame.py                                                                |        3 |        0 |        0 |        0 |    100% |           |
| src/glossogen/run\_export/csv\_frame\_writer.py                                                        |       26 |        1 |        6 |        1 |     94% |        63 |
| src/glossogen/run\_export/export\_column\_catalog.py                                                   |       72 |        2 |       30 |        2 |     96% |   74, 136 |
| src/glossogen/run\_export/export\_limits.py                                                            |       17 |        0 |        6 |        0 |    100% |           |
| src/glossogen/run\_export/export\_preview\_models.py                                                   |        4 |        0 |        0 |        0 |    100% |           |
| src/glossogen/run\_export/export\_request\_models.py                                                   |       30 |        0 |        0 |        0 |    100% |           |
| src/glossogen/run\_export/export\_run\_record.py                                                       |       23 |        0 |        0 |        0 |    100% |           |
| src/glossogen/run\_export/knob\_flattening.py                                                          |       30 |        1 |       12 |        1 |     95% |        63 |
| src/glossogen/run\_export/label\_value\_columns.py                                                     |       18 |        1 |        8 |        1 |     92% |        45 |
| src/glossogen/run\_export/lineage\_columns.py                                                          |       23 |        2 |       12 |        2 |     89% |    29, 31 |
| src/glossogen/run\_export/message\_event\_scan.py                                                      |       50 |        2 |       18 |        1 |     93% |   118-119 |
| src/glossogen/run\_export/message\_level\_frame.py                                                     |       36 |        0 |        6 |        0 |    100% |           |
| src/glossogen/run\_export/message\_repetition\_sidecar.py                                              |       24 |        3 |        4 |        0 |     89% |     37-41 |
| src/glossogen/run\_export/metric\_column\_projection.py                                                |       42 |        9 |       16 |        0 |     74% |69-71, 76-78, 101-103 |
| src/glossogen/run\_export/model\_weight\_class.py                                                      |       22 |        0 |       12 |        0 |    100% |           |
| src/glossogen/run\_export/observation\_row\_keys.py                                                    |        8 |        0 |        2 |        0 |    100% |           |
| src/glossogen/run\_export/primary\_channel\_resolution.py                                              |       24 |        0 |        8 |        0 |    100% |           |
| src/glossogen/run\_export/round\_context\_frame.py                                                     |       61 |        4 |       14 |        1 |     93% |120-125, 131 |
| src/glossogen/run\_export/round\_level\_frame.py                                                       |       34 |        3 |       12 |        3 |     87% |52, 78, 91 |
| src/glossogen/run\_export/run\_context\_columns.py                                                     |       32 |        0 |        8 |        0 |    100% |           |
| src/glossogen/run\_export/run\_level\_frame.py                                                         |       30 |        4 |        8 |        2 |     84% |44-45, 64-65 |
| src/glossogen/run\_export/run\_message\_records.py                                                     |       31 |        0 |        2 |        0 |    100% |           |
| src/glossogen/run\_export/run\_metadata\_columns.py                                                    |        8 |        0 |        0 |        0 |    100% |           |
| src/glossogen/run\_export/run\_selection\_resolution.py                                                |       48 |        3 |       28 |        1 |     92% |     64-66 |
| src/glossogen/run\_export/runs\_zip\_archive.py                                                        |       92 |        0 |       16 |        0 |    100% |           |
| src/glossogen/run\_file\_paths.py                                                                      |        9 |        0 |        0 |        0 |    100% |           |
| src/glossogen/run\_identity.py                                                                         |        2 |        0 |        0 |        0 |    100% |           |
| src/glossogen/run\_labels\_file.py                                                                     |       30 |        0 |       10 |        0 |    100% |           |
| src/glossogen/run\_lineage.py                                                                          |       16 |        4 |        4 |        2 |     70% |35, 39, 46-47 |
| src/glossogen/run\_replay/\_\_init\_\_.py                                                              |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/run\_replay/message\_history\_builder.py                                                 |      270 |       54 |      156 |       18 |     78% |140, 142, 144, 198, 217, 248, 281-308, 317, 368, 374, 446-461, 492-\>494, 495, 518-519, 521, 539, 693, 729-\>727, 765-768 |
| src/glossogen/run\_replay/message\_rewind.py                                                           |      133 |       21 |       60 |        6 |     81% |120-121, 127-128, 213-217, 285, 325, 347-\>340, 431-439, 462, 479-483, 518 |
| src/glossogen/run\_replay/resume\_context\_writer.py                                                   |       34 |        8 |       14 |        3 |     73% |41, 43, 65, 81-89 |
| src/glossogen/run\_replay/resume\_state\_loader.py                                                     |      143 |        4 |       54 |        5 |     95% |317, 321, 389, 562-\>564, 566 |
| src/glossogen/runners/\_\_init\_\_.py                                                                  |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/runners/agent\_run\_result.py                                                            |        2 |        0 |        0 |        0 |    100% |           |
| src/glossogen/runners/agent\_runner\_base.py                                                           |        5 |        0 |        0 |        0 |    100% |           |
| src/glossogen/runners/agent\_tools.py                                                                  |       86 |        5 |       22 |        3 |     93% |186, 200-206, 211, 236, 246-\>248 |
| src/glossogen/runners/communication\_protocol.py                                                       |       26 |        0 |        6 |        0 |    100% |           |
| src/glossogen/runners/history\_cleanup\_processor.py                                                   |      134 |        6 |       54 |        7 |     93% |74, 77, 103, 123, 125, 183, 224-\>220 |
| src/glossogen/runners/open\_model\_anti\_corruption\_layer.py                                          |       42 |        3 |       12 |        3 |     89% |52, 66, 79 |
| src/glossogen/runners/pydantic\_ai\_model\_factory.py                                                  |       49 |        1 |       14 |        1 |     97% |        58 |
| src/glossogen/runners/pydantic\_ai\_runner.py                                                          |      401 |       40 |      138 |       27 |     85% |91, 94-\>96, 117-118, 190, 195, 199, 284-\>283, 287-293, 345, 422-430, 477, 503, 533-534, 685-698, 724-727, 775-776, 833-834, 898, 982-\>exit, 998-\>1001, 1002, 1003-\>1012, 1007, 1012-\>1014, 1014-\>exit, 1019, 1020-\>exit, 1027, 1082-\>exit |
| src/glossogen/runners/read\_notifications\_tool.py                                                     |       56 |        1 |       10 |        2 |     95% |56-\>55, 59 |
| src/glossogen/runtime/\_\_init\_\_.py                                                                  |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/runtime/activity\_notification.py                                                        |       18 |        0 |        0 |        0 |    100% |           |
| src/glossogen/runtime/agent\_session.py                                                                |       61 |        0 |        6 |        0 |    100% |           |
| src/glossogen/runtime/agent\_swap.py                                                                   |       95 |       20 |       10 |        4 |     77% |79, 82, 96, 202-220, 256, 289-290 |
| src/glossogen/runtime/channel\_router.py                                                               |       98 |        1 |       34 |        1 |     98% |        89 |
| src/glossogen/runtime/communication\_tools.py                                                          |       34 |        2 |        4 |        2 |     89% |   51, 107 |
| src/glossogen/runtime/elapsed\_time.py                                                                 |        9 |        1 |        4 |        2 |     77% |26-\>25, 28 |
| src/glossogen/runtime/event\_bus.py                                                                    |       30 |        8 |        6 |        2 |     72% |38-41, 44-45, 62-\>exit, 68-69 |
| src/glossogen/runtime/event\_logger.py                                                                 |       37 |        0 |        6 |        1 |     98% | 67-\>exit |
| src/glossogen/runtime/game\_clock.py                                                                   |      166 |        7 |       58 |        5 |     95% |62, 67, 149, 200-\>206, 253-\>258, 313-317, 413-417 |
| src/glossogen/runtime/notification\_payload.py                                                         |       54 |        2 |       14 |        2 |     94% |  105, 190 |
| src/glossogen/runtime/read\_notifications\_schema.py                                                   |       17 |        0 |        0 |        0 |    100% |           |
| src/glossogen/runtime/round\_end\_trigger.py                                                           |       17 |        0 |        0 |        0 |    100% |           |
| src/glossogen/runtime/scenario\_tool.py                                                                |        3 |        0 |        0 |        0 |    100% |           |
| src/glossogen/runtime/scenario\_world.py                                                               |       94 |       19 |       14 |        2 |     75% |78, 104, 133-150, 165-169 |
| src/glossogen/runtime/scheduled\_events.py                                                             |       41 |        2 |        8 |        2 |     92% |   96, 121 |
| src/glossogen/runtime/scheduler.py                                                                     |       31 |        0 |       10 |        0 |    100% |           |
| src/glossogen/runtime/simulation\_state.py                                                             |      244 |       12 |       70 |        7 |     94% |176, 231, 238, 309, 355, 376-386, 507, 593 |
| src/glossogen/runtime/wait\_for.py                                                                     |        5 |        0 |        0 |        0 |    100% |           |
| src/glossogen/runtime/wait\_registry.py                                                                |      133 |        2 |       40 |        3 |     97% |201, 240-\>242, 250 |
| src/glossogen/scenario\_api.py                                                                         |        1 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenario\_authoring/\_\_init\_\_.py                                                      |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenario\_authoring/scaffold\_templates/ids.py.jinja                                     |        6 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenario\_authoring/scaffold\_templates/knobs\_default.json.jinja                        |        1 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenario\_authoring/scenario\_conformance.py                                             |      404 |       61 |      188 |       40 |     82% |84, 118-120, 189-191, 195, 198, 209, 216, 219, 222, 236, 251, 253, 261, 278, 292, 300, 303, 316, 323, 438, 447, 462, 469, 491-497, 519-525, 538, 551, 568, 582, 635, 639, 645, 663, 679, 699, 702-706, 719, 765, 782, 791-793, 813, 831-832, 834, 837, 847, 850 |
| src/glossogen/scenario\_authoring/scenario\_package\_checks.py                                         |      129 |       14 |       54 |       11 |     86% |99, 156-158, 164, 202, 212, 268, 271, 274-\>281, 277, 280, 324-325, 338 |
| src/glossogen/scenario\_authoring/scenario\_scaffold.py                                                |       43 |        0 |        8 |        0 |    100% |           |
| src/glossogen/scenario\_authoring/scenario\_target.py                                                  |       27 |        1 |       10 |        1 |     95% |       100 |
| src/glossogen/scenario\_base.py                                                                        |      236 |        6 |       30 |        4 |     96% |179, 300, 329, 556, 773, 845 |
| src/glossogen/scenario\_entry\_points.py                                                               |       34 |        0 |       10 |        0 |    100% |           |
| src/glossogen/scenario\_event\_types.py                                                                |       19 |        1 |        4 |        1 |     91% |        29 |
| src/glossogen/scenario\_loader.py                                                                      |       96 |        2 |       30 |        0 |     98% |   290-291 |
| src/glossogen/scenario\_name.py                                                                        |        4 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenario\_path\_loader.py                                                                |      113 |       13 |       32 |        9 |     85% |92-93, 106, 139, 149-150, 170-171, 203, 222, 247, 264-\>exit, 292, 298 |
| src/glossogen/scenario\_protocol.py                                                                    |       11 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenario\_registry.py                                                                    |       15 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenario\_run\_detail\_extension.py                                                      |        7 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenario\_submodule\_discovery.py                                                        |       42 |        3 |       14 |        1 |     89% |81-83, 111-\>113 |
| src/glossogen/scenarios/\_\_init\_\_.py                                                                |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/base\_knobs.py                                                                 |       49 |        1 |       12 |        1 |     97% |       123 |
| src/glossogen/scenarios/channel\_noise.py                                                              |       20 |        3 |        6 |        1 |     85% | 61, 67-68 |
| src/glossogen/scenarios/container\_yard\_stacking/\_\_init\_\_.py                                      |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/container\_yard\_stacking/case\_event\_conversion.py                           |       17 |        0 |        4 |        0 |    100% |           |
| src/glossogen/scenarios/container\_yard\_stacking/case\_rendering.py                                   |        3 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/container\_yard\_stacking/container\_attributes.py                             |        8 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/container\_yard\_stacking/evaluation/\_\_init\_\_.py                           |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/container\_yard\_stacking/evaluation/build\_communication\_rounds.py           |       54 |       24 |       18 |        4 |     53% |45, 59, 66-67, 74-95, 103 |
| src/glossogen/scenarios/container\_yard\_stacking/events.py                                            |       12 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/container\_yard\_stacking/ids.py                                               |       50 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/container\_yard\_stacking/injection\_rendering.py                              |       47 |       13 |       22 |        6 |     64% |39, 43, 75, 93, 104, 110-114, 121-123 |
| src/glossogen/scenarios/container\_yard\_stacking/judging.py                                           |       70 |       22 |       28 |        5 |     60% |42-44, 83, 114-118, 188, 192, 198-200, 205-212 |
| src/glossogen/scenarios/container\_yard\_stacking/knobs.py                                             |       53 |       19 |       28 |        8 |     52% |61, 63, 69, 71, 78, 88-95, 100, 102-114 |
| src/glossogen/scenarios/container\_yard\_stacking/outcome\_reconstruction.py                           |       58 |       46 |       30 |        0 |     14% |40-62, 77-79, 90-120 |
| src/glossogen/scenarios/container\_yard\_stacking/run\_detail\_extension.py                            |       53 |       16 |       18 |        2 |     63% |93-95, 102-109, 131-132, 136-138 |
| src/glossogen/scenarios/container\_yard\_stacking/scenario.py                                          |      179 |       26 |       56 |       13 |     79% |112, 126, 220, 236, 246, 260, 270, 290, 309, 318, 325, 352-365, 378, 401-403 |
| src/glossogen/scenarios/container\_yard\_stacking/team\_declaration.py                                 |       25 |        1 |        6 |        1 |     94% |       173 |
| src/glossogen/scenarios/container\_yard\_stacking/team\_routing.py                                     |       40 |        0 |       20 |        0 |    100% |           |
| src/glossogen/scenarios/container\_yard\_stacking/tools.py                                             |       33 |        8 |       12 |        5 |     67% |38, 44, 52-\>67, 91-98, 100 |
| src/glossogen/scenarios/container\_yard\_stacking/world.py                                             |      157 |       27 |       54 |       16 |     79% |103, 108, 125, 130, 138, 149, 158, 180, 190, 206, 213, 224, 243-\>248, 244-\>248, 273, 291, 295-298, 304, 310, 317-324, 328-329, 338, 341, 347 |
| src/glossogen/scenarios/container\_yard\_stacking/world\_state.py                                      |       15 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/container\_yard\_stacking/yard\_cases.py                                       |       45 |        1 |       10 |        1 |     96% |        68 |
| src/glossogen/scenarios/drive\_module\_repair/\_\_init\_\_.py                                          |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/drive\_module\_repair/case\_event\_conversion.py                               |        4 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/drive\_module\_repair/drive\_module\_cases.py                                  |       84 |        9 |       16 |        1 |     82% |121-124, 128-131, 428 |
| src/glossogen/scenarios/drive\_module\_repair/evaluation/\_\_init\_\_.py                               |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/drive\_module\_repair/evaluation/build\_communication\_rounds.py               |       44 |       13 |       12 |        4 |     70% |45, 63-65, 75-93, 101 |
| src/glossogen/scenarios/drive\_module\_repair/events.py                                                |       12 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/drive\_module\_repair/ids.py                                                   |       24 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/drive\_module\_repair/injection\_rendering.py                                  |       18 |        3 |        6 |        3 |     75% |39, 49, 67 |
| src/glossogen/scenarios/drive\_module\_repair/knobs.py                                                 |       24 |        4 |        8 |        4 |     75% |74, 76, 81, 83 |
| src/glossogen/scenarios/drive\_module\_repair/replacement\_judge.py                                    |       21 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/drive\_module\_repair/run\_detail\_extension.py                                |       41 |        5 |       14 |        2 |     84% |150, 160-163 |
| src/glossogen/scenarios/drive\_module\_repair/scenario.py                                              |      131 |        7 |       24 |        6 |     92% |209, 221, 223, 231, 233, 235, 326 |
| src/glossogen/scenarios/drive\_module\_repair/team\_declaration.py                                     |       13 |        0 |        2 |        0 |    100% |           |
| src/glossogen/scenarios/drive\_module\_repair/tools.py                                                 |       30 |        5 |       14 |        6 |     75% |38, 40, 45, 47, 50, 59-\>72 |
| src/glossogen/scenarios/drive\_module\_repair/world.py                                                 |      178 |       64 |       68 |       19 |     57% |62-66, 71-73, 105, 121, 123, 130, 145, 149-153, 156-157, 173-180, 203-234, 267, 275, 292, 302, 306, 323, 331, 337, 344, 350-357, 361-362, 371, 373 |
| src/glossogen/scenarios/drive\_module\_repair/world\_state.py                                          |        2 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/hospital\_bed\_assignment\_privacy/\_\_init\_\_.py                             |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/hospital\_bed\_assignment\_privacy/events.py                                   |       12 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/hospital\_bed\_assignment\_privacy/hospital\_cases.py                          |       70 |        1 |       18 |        3 |     95% |195-\>191, 245-\>244, 273 |
| src/glossogen/scenarios/hospital\_bed\_assignment\_privacy/ids.py                                      |       32 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/hospital\_bed\_assignment\_privacy/knobs.py                                    |       30 |        8 |       16 |        8 |     65% |49, 51, 55, 59, 64, 74, 80, 90 |
| src/glossogen/scenarios/hospital\_bed\_assignment\_privacy/scenario.py                                 |      220 |       52 |       94 |       27 |     69% |237, 254, 262, 274, 287, 294, 316, 320, 322, 327-330, 342, 375, 377, 383, 393, 398, 403, 417-\>429, 446, 460, 462, 468, 477, 482, 496, 498-\>509, 527, 567-607 |
| src/glossogen/scenarios/hospital\_bed\_assignment\_privacy/team\_declaration.py                        |       11 |        0 |        2 |        0 |    100% |           |
| src/glossogen/scenarios/hospital\_bed\_assignment\_privacy/world.py                                    |      130 |       19 |       44 |       11 |     80% |114, 129, 178, 183, 188, 195, 199-217, 231, 236, 239, 292, 309-\>311, 314, 316 |
| src/glossogen/scenarios/orbital\_anomaly/\_\_init\_\_.py                                               |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/orbital\_anomaly/actuation\_judge.py                                           |       16 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/orbital\_anomaly/events.py                                                     |        8 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/orbital\_anomaly/ids.py                                                        |       25 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/orbital\_anomaly/injection\_rendering.py                                       |       22 |        3 |        8 |        3 |     80% |37, 55, 73 |
| src/glossogen/scenarios/orbital\_anomaly/knobs.py                                                      |       18 |        4 |        8 |        4 |     69% |50, 52, 58, 60 |
| src/glossogen/scenarios/orbital\_anomaly/orbital\_anomaly\_cases.py                                    |       44 |        1 |        6 |        1 |     96% |       419 |
| src/glossogen/scenarios/orbital\_anomaly/run\_detail\_extension.py                                     |       40 |        5 |       14 |        2 |     83% |121, 131-134 |
| src/glossogen/scenarios/orbital\_anomaly/scenario.py                                                   |      117 |        5 |       26 |        5 |     93% |184, 196, 206, 210, 228 |
| src/glossogen/scenarios/orbital\_anomaly/team\_declaration.py                                          |       11 |        0 |        2 |        0 |    100% |           |
| src/glossogen/scenarios/orbital\_anomaly/tools.py                                                      |       32 |        6 |       16 |        7 |     73% |35, 37, 39, 41, 44, 53-\>64, 73 |
| src/glossogen/scenarios/orbital\_anomaly/world.py                                                      |      103 |       21 |       36 |       14 |     75% |82, 92, 94, 113, 122-132, 149, 151, 153, 159, 165, 171-178, 180, 184-185, 201, 236 |
| src/glossogen/scenarios/prisoners\_dilemma/\_\_init\_\_.py                                             |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/prisoners\_dilemma/events.py                                                   |        6 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/prisoners\_dilemma/ids.py                                                      |       13 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/prisoners\_dilemma/knobs.py                                                    |       16 |        2 |        4 |        2 |     80% |    43, 48 |
| src/glossogen/scenarios/prisoners\_dilemma/scenario.py                                                 |       94 |        2 |       16 |        2 |     96% |  137, 206 |
| src/glossogen/scenarios/prisoners\_dilemma/tools.py                                                    |       25 |        3 |        4 |        1 |     86% | 30, 35-36 |
| src/glossogen/scenarios/prisoners\_dilemma/world.py                                                    |       57 |        2 |       12 |        2 |     94% |   81, 141 |
| src/glossogen/scenarios/satellite\_contact\_window/\_\_init\_\_.py                                     |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/satellite\_contact\_window/cases.py                                            |       67 |        1 |       10 |        1 |     97% |       352 |
| src/glossogen/scenarios/satellite\_contact\_window/command\_judge.py                                   |       33 |        1 |        4 |        1 |     95% |        45 |
| src/glossogen/scenarios/satellite\_contact\_window/evaluation/\_\_init\_\_.py                          |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/satellite\_contact\_window/events.py                                           |       21 |        2 |        4 |        2 |     84% |    62, 66 |
| src/glossogen/scenarios/satellite\_contact\_window/ids.py                                              |       25 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/satellite\_contact\_window/knobs.py                                            |       23 |        4 |        8 |        4 |     74% |51, 59, 65, 67 |
| src/glossogen/scenarios/satellite\_contact\_window/scenario.py                                         |      184 |       21 |       66 |       19 |     83% |182, 189, 205, 221, 235, 245, 261, 272, 280, 284, 294, 298-301, 304, 308, 413, 418, 420, 423, 503 |
| src/glossogen/scenarios/satellite\_contact\_window/team\_declaration.py                                |       13 |        0 |        2 |        0 |    100% |           |
| src/glossogen/scenarios/satellite\_contact\_window/world.py                                            |      121 |       18 |       34 |       13 |     80% |91, 116, 153-161, 174, 184, 204, 246, 248, 253, 259, 266-275, 277, 281-282, 298, 302 |
| src/glossogen/scenarios/signal\_game/\_\_init\_\_.py                                                   |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/signal\_game/board.py                                                          |       37 |        0 |        6 |        0 |    100% |           |
| src/glossogen/scenarios/signal\_game/evaluation/\_\_init\_\_.py                                        |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/signal\_game/evaluation/build\_communication\_rounds.py                        |       30 |        1 |       14 |        2 |     93% |69-\>76, 78 |
| src/glossogen/scenarios/signal\_game/evaluation/excess\_moves\_metric.py                               |       44 |        0 |       12 |        0 |    100% |           |
| src/glossogen/scenarios/signal\_game/evaluation/longest\_streak\_metric.py                             |       33 |        0 |        8 |        0 |    100% |           |
| src/glossogen/scenarios/signal\_game/events.py                                                         |       24 |        1 |        4 |        1 |     93% |        33 |
| src/glossogen/scenarios/signal\_game/ids.py                                                            |       29 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/signal\_game/knobs.py                                                          |       17 |        3 |        6 |        3 |     74% |34, 36, 41 |
| src/glossogen/scenarios/signal\_game/scenario.py                                                       |      253 |       18 |       66 |       11 |     90% |134, 245-246, 332, 334, 343, 400, 427, 429, 450, 458-473, 638, 675, 680, 685 |
| src/glossogen/scenarios/signal\_game/wake\_package.py                                                  |        3 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/signal\_game/world.py                                                          |      101 |        8 |       20 |        7 |     88% |80, 114, 128, 141, 166, 179, 186, 218 |
| src/glossogen/scenarios/spillway\_release/\_\_init\_\_.py                                              |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/spillway\_release/case\_event\_conversion.py                                   |        4 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/spillway\_release/events.py                                                    |       12 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/spillway\_release/ids.py                                                       |       25 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/spillway\_release/injection\_rendering.py                                      |       28 |        3 |       12 |        3 |     85% |64, 77, 95 |
| src/glossogen/scenarios/spillway\_release/knobs.py                                                     |       31 |        7 |       14 |        7 |     69% |60, 69, 71, 79, 85, 90, 92 |
| src/glossogen/scenarios/spillway\_release/scenario.py                                                  |      110 |        3 |       20 |        3 |     95% |183, 195, 226 |
| src/glossogen/scenarios/spillway\_release/spillway\_cases.py                                           |       85 |        6 |       26 |        4 |     91% |69-70, 77, 204-205, 258 |
| src/glossogen/scenarios/spillway\_release/team\_declaration.py                                         |       13 |        0 |        2 |        0 |    100% |           |
| src/glossogen/scenarios/spillway\_release/tools.py                                                     |       70 |       20 |       38 |       18 |     63% |40, 43, 57, 59, 62, 64, 66, 69-71, 82-\>94, 103, 105, 108, 111-\>120, 124-134, 142, 146, 149, 152-\>159 |
| src/glossogen/scenarios/spillway\_release/world.py                                                     |      113 |       16 |       28 |       10 |     82% |72, 91, 100, 105, 130, 138, 153, 165, 182, 196, 203, 209-216, 220-221, 230 |
| src/glossogen/scenarios/spillway\_release/world\_state.py                                              |       41 |        4 |       16 |        4 |     86% |61, 63, 73, 80 |
| src/glossogen/scenarios/spot\_the\_difference/\_\_init\_\_.py                                          |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/spot\_the\_difference/case\_event\_conversion.py                               |       13 |        0 |        2 |        0 |    100% |           |
| src/glossogen/scenarios/spot\_the\_difference/difference\_judge.py                                     |       40 |        5 |        4 |        1 |     86% |     82-86 |
| src/glossogen/scenarios/spot\_the\_difference/evaluation/\_\_init\_\_.py                               |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/spot\_the\_difference/evaluation/build\_communication\_rounds.py               |       47 |       17 |       18 |        4 |     58% |40, 54, 61, 68-80, 88 |
| src/glossogen/scenarios/spot\_the\_difference/events.py                                                |        9 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/spot\_the\_difference/ids.py                                                   |       44 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/spot\_the\_difference/injection\_rendering.py                                  |       23 |        3 |        8 |        3 |     81% |38, 58, 76 |
| src/glossogen/scenarios/spot\_the\_difference/knobs.py                                                 |       64 |       15 |       30 |       15 |     68% |84, 86, 92, 96, 104, 106, 112, 116, 124, 127, 136, 144, 153, 157, 164 |
| src/glossogen/scenarios/spot\_the\_difference/outcome\_reconstruction.py                               |       62 |       52 |       30 |        0 |     11% |43-99, 116-152 |
| src/glossogen/scenarios/spot\_the\_difference/run\_detail\_extension.py                                |       52 |       10 |       18 |        3 |     76% |98, 124, 131-138, 155-159 |
| src/glossogen/scenarios/spot\_the\_difference/scenario.py                                              |      168 |       12 |       48 |       11 |     89% |234, 250, 252, 262, 271, 273, 288, 290, 419, 423, 425, 431 |
| src/glossogen/scenarios/spot\_the\_difference/scene\_generation.py                                     |      221 |        5 |       56 |        4 |     97% |195, 363, 399, 450-455 |
| src/glossogen/scenarios/spot\_the\_difference/scripts/\_\_init\_\_.py                                  |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/spot\_the\_difference/scripts/check\_scene\_generation.py                      |       70 |       70 |       24 |        0 |      0% |    14-142 |
| src/glossogen/scenarios/spot\_the\_difference/team\_declaration.py                                     |       27 |        0 |        8 |        0 |    100% |           |
| src/glossogen/scenarios/spot\_the\_difference/team\_routing.py                                         |       38 |        0 |       20 |        0 |    100% |           |
| src/glossogen/scenarios/spot\_the\_difference/tools.py                                                 |       59 |        8 |       22 |        8 |     80% |47, 49, 52, 55, 58, 62, 108, 160 |
| src/glossogen/scenarios/spot\_the\_difference/world.py                                                 |      174 |       26 |       64 |       14 |     81% |100, 105, 123, 209, 221, 236, 264, 284, 289, 298, 305, 312, 316-332, 362, 372, 377, 382-384, 391 |
| src/glossogen/scenarios/spot\_the\_difference/world\_state.py                                          |       57 |        1 |       10 |        3 |     94% |92, 173-\>177, 175-\>177 |
| src/glossogen/scenarios/spot\_the\_intersection/\_\_init\_\_.py                                        |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/spot\_the\_intersection/board\_certification.py                                |      141 |        1 |       42 |        1 |     99% |       298 |
| src/glossogen/scenarios/spot\_the\_intersection/board\_generation.py                                   |      142 |        2 |       40 |        2 |     98% |  263, 314 |
| src/glossogen/scenarios/spot\_the\_intersection/board\_model.py                                        |       19 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/spot\_the\_intersection/board\_rendering.py                                    |       27 |        0 |       10 |        0 |    100% |           |
| src/glossogen/scenarios/spot\_the\_intersection/evaluation/\_\_init\_\_.py                             |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/spot\_the\_intersection/evaluation/build\_communication\_rounds.py             |       32 |       13 |       12 |        2 |     52% | 51, 58-76 |
| src/glossogen/scenarios/spot\_the\_intersection/events.py                                              |       10 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/spot\_the\_intersection/ids.py                                                 |       25 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/spot\_the\_intersection/injection\_rendering.py                                |       20 |        2 |        6 |        2 |     85% |    58, 62 |
| src/glossogen/scenarios/spot\_the\_intersection/knobs.py                                               |       53 |        7 |       22 |        7 |     81% |70, 72, 77, 79, 85, 113, 123 |
| src/glossogen/scenarios/spot\_the\_intersection/outcome\_reconstruction.py                             |       64 |        2 |       26 |        3 |     94% |100, 103, 143-\>134 |
| src/glossogen/scenarios/spot\_the\_intersection/recorded\_board\_audit.py                              |       72 |        0 |       22 |        0 |    100% |           |
| src/glossogen/scenarios/spot\_the\_intersection/round\_event\_conversion.py                            |       18 |        0 |        2 |        0 |    100% |           |
| src/glossogen/scenarios/spot\_the\_intersection/run\_detail\_extension.py                              |       54 |        1 |       14 |        1 |     97% |       126 |
| src/glossogen/scenarios/spot\_the\_intersection/scenario.py                                            |      146 |        4 |       34 |        4 |     96% |184, 200, 219, 235 |
| src/glossogen/scenarios/spot\_the\_intersection/scripts/\_\_init\_\_.py                                |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/spot\_the\_intersection/scripts/audit\_recorded\_boards.py                     |       34 |       34 |       12 |        0 |      0% |     15-62 |
| src/glossogen/scenarios/spot\_the\_intersection/scripts/certify\_boards.py                             |       87 |       87 |       32 |        0 |      0% |    20-204 |
| src/glossogen/scenarios/spot\_the\_intersection/seats.py                                               |       36 |        0 |       12 |        0 |    100% |           |
| src/glossogen/scenarios/spot\_the\_intersection/single\_board\_guessers.py                             |       75 |        1 |       10 |        1 |     98% |        58 |
| src/glossogen/scenarios/spot\_the\_intersection/team\_declaration.py                                   |       18 |        0 |        4 |        0 |    100% |           |
| src/glossogen/scenarios/spot\_the\_intersection/tools.py                                               |       41 |        6 |       18 |        6 |     80% |54, 56, 58, 60, 63, 109 |
| src/glossogen/scenarios/spot\_the\_intersection/world.py                                               |      154 |       15 |       60 |        9 |     86% |128, 163, 193, 231-232, 235-241, 260, 264, 303-\>exit, 337-342 |
| src/glossogen/scenarios/spot\_the\_intersection/world\_state.py                                        |       90 |        2 |       32 |        2 |     97% |  260, 289 |
| src/glossogen/scenarios/textcraft\_shared\_workspace/\_\_init\_\_.py                                   |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/textcraft\_shared\_workspace/events.py                                         |       22 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/textcraft\_shared\_workspace/knobs.py                                          |       41 |        3 |       16 |        3 |     89% |76, 78, 95 |
| src/glossogen/scenarios/textcraft\_shared\_workspace/recipe\_dealing.py                                |       16 |        1 |        6 |        1 |     91% |        16 |
| src/glossogen/scenarios/textcraft\_shared\_workspace/round\_vocabulary.py                              |        5 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/textcraft\_shared\_workspace/scenario.py                                       |      353 |       14 |      116 |       17 |     93% |138, 233, 242, 272-273, 348, 366, 428, 553-\>557, 558-\>560, 581-\>587, 670, 674, 682-\>684, 698-\>707, 764, 800, 840, 855 |
| src/glossogen/scenarios/textcraft\_shared\_workspace/scripts/\_\_init\_\_.py                           |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/textcraft\_shared\_workspace/scripts/write\_task\_manifest.py                  |       22 |       22 |        2 |        0 |      0% |     13-57 |
| src/glossogen/scenarios/textcraft\_shared\_workspace/state.py                                          |      130 |        3 |       36 |        3 |     96% |91, 186, 210 |
| src/glossogen/scenarios/textcraft\_shared\_workspace/tasks.py                                          |      126 |       14 |       66 |       14 |     85% |32, 34, 79, 82, 85, 87, 89, 92, 101, 132, 134, 136, 138, 144 |
| src/glossogen/scenarios/textcraft\_shared\_workspace/tool\_results.py                                  |        7 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/textcraft\_shared\_workspace/virtual\_clock.py                                 |      185 |        7 |       50 |        7 |     94% |120, 151-\>153, 156, 174, 182, 206, 217, 220 |
| src/glossogen/scenarios/textcraft\_shared\_workspace/world.py                                          |      112 |        6 |       38 |        6 |     92% |161, 181, 183, 199, 205, 226 |
| src/glossogen/scenarios/veyru/\_\_init\_\_.py                                                          |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/veyru/case\_event\_conversion.py                                               |        4 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/veyru/evaluation/\_\_init\_\_.py                                               |        1 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/veyru/evaluation/build\_communication\_rounds.py                               |       37 |       10 |       10 |        3 |     72% |43, 61-77, 90 |
| src/glossogen/scenarios/veyru/evaluation/metrics/\_\_init\_\_.py                                       |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/veyru/events.py                                                                |       12 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/veyru/ids.py                                                                   |       44 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/veyru/injection\_rendering.py                                                  |      107 |       31 |       62 |       14 |     65% |43, 53-59, 69, 86, 124, 135, 137, 141, 160-175, 180-190, 215, 236, 241, 257 |
| src/glossogen/scenarios/veyru/knobs.py                                                                 |       37 |        8 |       22 |        8 |     73% |77, 79, 99, 105, 107, 112, 114, 120 |
| src/glossogen/scenarios/veyru/outcome\_reconstruction.py                                               |       68 |       13 |       36 |       10 |     76% |44, 51, 107, 109-113, 116, 119, 122-\>104, 132, 164, 167 |
| src/glossogen/scenarios/veyru/run\_detail\_extension.py                                                |       91 |       34 |       42 |        6 |     56% |133-139, 186, 196-199, 213-217, 220-229, 246-250, 253-258 |
| src/glossogen/scenarios/veyru/scenario.py                                                              |      199 |       27 |       58 |       12 |     82% |203, 265, 292, 334, 339, 343, 351, 368, 373, 375, 378-383, 398-401, 412-413, 428-441, 461-462 |
| src/glossogen/scenarios/veyru/scripts/\_\_init\_\_.py                                                  |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/veyru/scripts/build\_probe\_questions.py                                       |       28 |       28 |        4 |        0 |      0% |    12-105 |
| src/glossogen/scenarios/veyru/scripts/inspect\_replaced\_agent\_input.py                               |       74 |       74 |       30 |        0 |      0% |    22-145 |
| src/glossogen/scenarios/veyru/scripts/repro\_opus47\_refusal.py                                        |      146 |      146 |       50 |        0 |      0% |    22-264 |
| src/glossogen/scenarios/veyru/scripts/run\_baseline\_no\_specialist.py                                 |       79 |       79 |       18 |        0 |      0% |     8-130 |
| src/glossogen/scenarios/veyru/scripts/run\_baseline\_no\_specialist\_opus47.py                         |      118 |      118 |       42 |        0 |      0% |    15-184 |
| src/glossogen/scenarios/veyru/scripts/run\_evals\_no\_specialist.py                                    |       62 |       62 |       16 |        0 |      0% |     9-104 |
| src/glossogen/scenarios/veyru/scripts/run\_smoke\_8.py                                                 |       78 |       78 |       16 |        0 |      0% |     9-128 |
| src/glossogen/scenarios/veyru/stabilization\_judge.py                                                  |       21 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/veyru/team\_declaration.py                                                     |       41 |        0 |       12 |        0 |    100% |           |
| src/glossogen/scenarios/veyru/team\_lifecycle.py                                                       |       55 |       43 |       24 |        1 |     16% |43-102, 107-119, 130-158, 176-181 |
| src/glossogen/scenarios/veyru/tools.py                                                                 |       63 |       20 |       20 |        9 |     65% |42-55, 59, 62-72, 74-84, 88-98, 107-\>118, 138-148, 178, 199-201 |
| src/glossogen/scenarios/veyru/veyru\_cases.py                                                          |       71 |        7 |        8 |        1 |     90% |435, 520-551 |
| src/glossogen/scenarios/veyru/world.py                                                                 |      170 |       34 |       52 |       16 |     77% |130-132, 150, 165, 173, 192, 208-214, 224, 237, 283, 290, 300, 303, 326, 332-337, 368, 370, 388, 402, 409, 419, 423-424, 439, 443 |
| src/glossogen/scenarios/veyru/world\_state.py                                                          |       20 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/warehouse\_robot\_recovery/\_\_init\_\_.py                                     |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/warehouse\_robot\_recovery/evaluation/\_\_init\_\_.py                          |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/warehouse\_robot\_recovery/events.py                                           |       10 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/warehouse\_robot\_recovery/fleet\_mode.py                                      |        5 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/warehouse\_robot\_recovery/ids.py                                              |       24 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/warehouse\_robot\_recovery/knobs.py                                            |       13 |        2 |        4 |        2 |     76% |    52, 54 |
| src/glossogen/scenarios/warehouse\_robot\_recovery/recovery\_judge.py                                  |       18 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/warehouse\_robot\_recovery/scenario.py                                         |      167 |       18 |       58 |       16 |     84% |183, 199, 213, 223, 237, 248, 256, 260, 270, 274-277, 281, 368, 373, 375, 379, 441 |
| src/glossogen/scenarios/warehouse\_robot\_recovery/team\_declaration.py                                |       13 |        0 |        2 |        0 |    100% |           |
| src/glossogen/scenarios/warehouse\_robot\_recovery/warehouse\_cases.py                                 |       75 |        1 |       18 |        1 |     98% |       351 |
| src/glossogen/scenarios/warehouse\_robot\_recovery/world.py                                            |      109 |       18 |       34 |       13 |     78% |83, 103, 132-140, 150, 160, 177, 217, 219, 224, 230, 237-246, 248, 252-253, 266, 270 |
| src/glossogen/self\_hosted\_config.py                                                                  |       10 |        0 |        4 |        0 |    100% |           |
| src/glossogen/server/\_\_init\_\_.py                                                                   |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/server/app.py                                                                            |        6 |        6 |        0 |        0 |      0% |      8-15 |
| src/glossogen/server/app\_factory.py                                                                   |      101 |       38 |       18 |        1 |     57% |53-62, 74-77, 86-99, 112-134, 220 |
| src/glossogen/server/error\_logging\_handlers.py                                                       |       15 |        2 |        4 |        2 |     79% |    25, 27 |
| src/glossogen/server/feature\_flags.py                                                                 |       12 |        1 |        2 |        1 |     86% |        24 |
| src/glossogen/server/health\_router.py                                                                 |       12 |        0 |        0 |        0 |    100% |           |
| src/glossogen/server/identity/\_\_init\_\_.py                                                          |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/server/identity/bearer\_credential.py                                                    |       17 |        1 |        8 |        1 |     92% |        18 |
| src/glossogen/server/identity/bootstrap.py                                                             |       12 |        5 |        0 |        0 |     58% |     24-37 |
| src/glossogen/server/identity/identity\_api.py                                                         |        1 |        0 |        0 |        0 |    100% |           |
| src/glossogen/server/identity/identity\_entry\_points.py                                               |       28 |        1 |       10 |        1 |     95% |        59 |
| src/glossogen/server/identity/identity\_model.py                                                       |        4 |        0 |        0 |        0 |    100% |           |
| src/glossogen/server/identity/identity\_provider.py                                                    |       10 |        0 |        0 |        0 |    100% |           |
| src/glossogen/server/identity/identity\_provider\_loader.py                                            |       30 |        0 |        8 |        0 |    100% |           |
| src/glossogen/server/identity/middleware.py                                                            |       94 |        8 |       34 |        3 |     91% |99-100, 104-105, 140, 209-211 |
| src/glossogen/server/identity/provider\_services.py                                                    |       24 |        0 |        8 |        0 |    100% |           |
| src/glossogen/server/mcp/\_\_init\_\_.py                                                               |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/server/mcp/asgi\_context.py                                                              |       42 |        2 |       18 |        2 |     93% |44-45, 84-\>83 |
| src/glossogen/server/mcp/browser.py                                                                    |      191 |        9 |       56 |        3 |     95% |114, 182, 195, 888-903 |
| src/glossogen/server/mcp/in\_memory\_oauth\_storage.py                                                 |       95 |       17 |       26 |        1 |     80% |128-129, 177-205 |
| src/glossogen/server/mcp/models.py                                                                     |       30 |        0 |        0 |        0 |    100% |           |
| src/glossogen/server/mcp/oauth\_mounting.py                                                            |       48 |       25 |        6 |        0 |     43% |32, 35, 47, 57-59, 70-107, 125-143 |
| src/glossogen/server/mcp/oauth\_provider.py                                                            |      105 |        6 |       16 |        0 |     95% |77, 92-93, 412-414 |
| src/glossogen/server/mcp/oauth\_records.py                                                             |        7 |        0 |        0 |        0 |    100% |           |
| src/glossogen/server/mcp/oauth\_storage.py                                                             |      126 |       84 |       24 |        0 |     28% |44, 48, 56-57, 79-87, 95-96, 122-149, 153-154, 162-163, 180-202, 206-207, 211-212, 220-221, 243-265, 269-270, 274-275, 283-284, 306-322, 335-336, 350-364, 378-380 |
| src/glossogen/server/mcp/oauth\_storage\_port.py                                                       |        6 |        0 |        0 |        0 |    100% |           |
| src/glossogen/server/mcp/run\_context.py                                                               |       16 |        0 |        2 |        0 |    100% |           |
| src/glossogen/server/mcp/whoami\_router.py                                                             |       28 |       17 |       10 |        0 |     29% |     40-62 |
| src/glossogen/server/pdf/\_\_init\_\_.py                                                               |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/server/pdf/export\_data.py                                                               |       78 |        0 |       32 |        1 |     99% | 259-\>261 |
| src/glossogen/server/pdf/html\_renderer.py                                                             |       38 |        2 |        6 |        2 |     91% |    48, 50 |
| src/glossogen/server/pdf/router.py                                                                     |       33 |        1 |        6 |        1 |     95% |        35 |
| src/glossogen/server/response\_models.py                                                               |        8 |        0 |        0 |        0 |    100% |           |
| src/glossogen/server/run\_launcher.py                                                                  |       35 |       14 |        2 |        0 |     57% |    61-114 |
| src/glossogen/server/runs/\_\_init\_\_.py                                                              |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/server/runs/analysis\_record\_cache.py                                                   |       40 |        0 |       10 |        1 |     98% | 100-\>102 |
| src/glossogen/server/runs/analysis\_router.py                                                          |       47 |        0 |        0 |        0 |    100% |           |
| src/glossogen/server/runs/archive\_streaming\_response.py                                              |       27 |        0 |        2 |        0 |    100% |           |
| src/glossogen/server/runs/branch\_sources.py                                                           |       48 |       31 |       12 |        0 |     28% |35-47, 56-70, 79-95, 104-106, 115-116 |
| src/glossogen/server/runs/bundle\_router.py                                                            |      187 |       29 |       44 |       13 |     82% |98-100, 199, 202-\>196, 212, 225, 228, 231, 252, 256, 299-301, 312-313, 324, 356-358, 400, 406-408, 421-422, 424-425, 437-438 |
| src/glossogen/server/runs/dashboard\_router.py                                                         |       53 |        1 |        6 |        1 |     97% |        96 |
| src/glossogen/server/runs/derived\_run\_references.py                                                  |       83 |        8 |       32 |        5 |     89% |58-65, 120, 122, 140-145, 157 |
| src/glossogen/server/runs/detail\_reader.py                                                            |      238 |       37 |      106 |       14 |     82% |136-137, 144, 257-262, 284-303, 308, 335-337, 348-\>359, 369-388, 398, 401, 468-\>247, 493, 523, 527, 572-573 |
| src/glossogen/server/runs/discovery.py                                                                 |      245 |       18 |       98 |       16 |     90% |167-\>135, 176-\>135, 184, 193-\>189, 199-\>198, 254, 298, 305, 322-324, 335-336, 441, 493, 564, 730, 734, 758-759, 764, 768 |
| src/glossogen/server/runs/evaluation\_score\_reader.py                                                 |       47 |        1 |        6 |        1 |     96% |        93 |
| src/glossogen/server/runs/export\_selection.py                                                         |       13 |        0 |        2 |        0 |    100% |           |
| src/glossogen/server/runs/label\_description\_router.py                                                |       30 |        0 |        2 |        0 |    100% |           |
| src/glossogen/server/runs/label\_mirror.py                                                             |       76 |       39 |       24 |        2 |     45% |97-113, 131-144, 153, 172-200 |
| src/glossogen/server/runs/listing.py                                                                   |      164 |       18 |       38 |        5 |     89% |88-89, 94-104, 137-145, 365, 384, 552, 576-577, 582 |
| src/glossogen/server/runs/lookup.py                                                                    |       47 |       16 |       14 |        4 |     61% |29, 66-84, 114-117, 148-150 |
| src/glossogen/server/runs/manifest\_sources.py                                                         |       45 |        1 |       16 |        1 |     97% |       153 |
| src/glossogen/server/runs/models.py                                                                    |       80 |        1 |        2 |        1 |     98% |        30 |
| src/glossogen/server/runs/multi\_export\_router.py                                                     |      103 |        0 |       20 |        0 |    100% |           |
| src/glossogen/server/runs/primary\_channel\_resolution.py                                              |       20 |        3 |        4 |        0 |     88% |     50-55 |
| src/glossogen/server/runs/reasoning\_entries.py                                                        |       19 |        0 |        8 |        0 |    100% |           |
| src/glossogen/server/runs/router.py                                                                    |      250 |       97 |       38 |        6 |     58% |146, 158-159, 213-234, 253-265, 295-305, 315-320, 428, 444-448, 452, 458, 464, 474, 514-516, 533-551, 582-598, 622-641, 652-659, 665-672, 694-720, 729-730 |
| src/glossogen/server/runs/scenario\_extension.py                                                       |       10 |        0 |        4 |        0 |    100% |           |
| src/glossogen/server/runs/streaming\_event.py                                                          |        6 |        0 |        0 |        0 |    100% |           |
| src/glossogen/server/scenarios/\_\_init\_\_.py                                                         |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/server/scenarios/filterable\_knobs.py                                                    |       72 |        2 |       30 |        3 |     95% |61, 141-\>144, 147 |
| src/glossogen/server/scenarios/models.py                                                               |        8 |        0 |        0 |        0 |    100% |           |
| src/glossogen/server/scenarios/router.py                                                               |       39 |       12 |        6 |        0 |     69% |     80-98 |
| src/glossogen/server/server\_runtime\_config.py                                                        |       17 |        1 |        4 |        1 |     90% |        29 |
| src/glossogen/simulation\_server.py                                                                    |       65 |       44 |        6 |        0 |     30% |35-68, 75-85, 90-93, 98-102, 116-142, 150-154 |
| src/glossogen/stream\_manifest.py                                                                      |       36 |        2 |        6 |        0 |     95% |     72-73 |
| src/glossogen/telemetry/\_\_init\_\_.py                                                                |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/telemetry/telemetry\_bootstrap.py                                                        |       48 |       33 |        6 |        0 |     28% |47-87, 97-101, 109-112 |
| src/glossogen/telemetry/telemetry\_round\_processor.py                                                 |       29 |       13 |        6 |        0 |     46% |34, 38-40, 50, 54-60, 70 |
| src/glossogen/telemetry/telemetry\_settings.py                                                         |        9 |        2 |        0 |        0 |     78% |    23, 28 |
| src/glossogen/template\_renderer.py                                                                    |        8 |        0 |        0 |        0 |    100% |           |
| src/glossogen/testing/\_\_init\_\_.py                                                                  |        8 |        0 |        0 |        0 |    100% |           |
| src/glossogen/testing/metric\_harness.py                                                               |       56 |        1 |        6 |        1 |     97% |       106 |
| src/glossogen/testing/scenario\_registration.py                                                        |       10 |        0 |        4 |        0 |    100% |           |
| src/glossogen/testing/scenario\_runtime.py                                                             |      100 |       14 |       42 |       14 |     80% |151, 157, 200, 202, 207, 213, 230, 238, 243, 252, 255, 263, 265, 275 |
| src/glossogen/testing/scripted\_agent.py                                                               |      101 |        3 |       30 |        3 |     95% |162, 211, 215 |
| src/glossogen/testing/simulation\_harness.py                                                           |      165 |        5 |       20 |        3 |     96% |170, 186, 400, 423-424 |
| src/glossogen/testing/smoke\_scenario.py                                                               |       89 |        1 |        4 |        1 |     98% |       209 |
| src/glossogen/testing/stub\_llm\_provider.py                                                           |       25 |        1 |        4 |        1 |     93% |        67 |
| src/glossogen/thread\_export/\_\_init\_\_.py                                                           |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/thread\_export/export\_agent\_thread.py                                                  |       57 |        1 |       18 |        1 |     97% |        74 |
| src/glossogen/thread\_export/provider\_thread\_serializer.py                                           |       96 |        0 |       64 |        4 |     98% |114-\>107, 135-\>129, 171-\>165, 207-\>202 |
| src/glossogen/thread\_export/thread\_export\_models.py                                                 |       38 |        0 |        4 |        0 |    100% |           |
| src/glossogen/token\_pricing.py                                                                        |       56 |        2 |       18 |        2 |     95% |  104, 107 |
| **TOTAL**                                                                                              | **26555** | **4262** | **7526** | **1127** | **81%** |           |


## Setup coverage badge

Below are examples of the badges you can use in your main branch `README` file.

### Direct image

[![Coverage badge](https://raw.githubusercontent.com/agencyenterprise/GlossoGen/python-coverage-comment-action-data/badge.svg)](https://htmlpreview.github.io/?https://github.com/agencyenterprise/GlossoGen/blob/python-coverage-comment-action-data/htmlcov/index.html)

This is the one to use if your repository is private or if you don't want to customize anything.

### [Shields.io](https://shields.io) Json Endpoint

[![Coverage badge](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/agencyenterprise/GlossoGen/python-coverage-comment-action-data/endpoint.json)](https://htmlpreview.github.io/?https://github.com/agencyenterprise/GlossoGen/blob/python-coverage-comment-action-data/htmlcov/index.html)

Using this one will allow you to [customize](https://shields.io/endpoint) the look of your badge.
It won't work with private repositories. It won't be refreshed more than once per five minutes.

### [Shields.io](https://shields.io) Dynamic Badge

[![Coverage badge](https://img.shields.io/badge/dynamic/json?color=brightgreen&label=coverage&query=%24.message&url=https%3A%2F%2Fraw.githubusercontent.com%2Fagencyenterprise%2FGlossoGen%2Fpython-coverage-comment-action-data%2Fendpoint.json)](https://htmlpreview.github.io/?https://github.com/agencyenterprise/GlossoGen/blob/python-coverage-comment-action-data/htmlcov/index.html)

This one will always be the same color. It won't work for private repos. I'm not even sure why we included it.

## What is that?

This branch is part of the
[python-coverage-comment-action](https://github.com/marketplace/actions/python-coverage-comment)
GitHub Action. All the files in this branch are automatically generated and may be
overwritten at any moment.
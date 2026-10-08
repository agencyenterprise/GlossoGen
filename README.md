# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/agencyenterprise/GlossoGen/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                                                                                                   |    Stmts |     Miss |   Branch |   BrPart |   Cover |   Missing |
|------------------------------------------------------------------------------------------------------- | -------: | -------: | -------: | -------: | ------: | --------: |
| src/glossogen/\_\_init\_\_.py                                                                          |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/\_\_main\_\_.py                                                                          |        2 |        2 |        0 |        0 |      0% |       3-5 |
| src/glossogen/atif\_export/\_\_init\_\_.py                                                             |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/atif\_export/atif\_models.py                                                             |       17 |        0 |        0 |        0 |    100% |           |
| src/glossogen/atif\_export/atif\_run\_context.py                                                       |       21 |        0 |        2 |        1 |     96% |   39-\>44 |
| src/glossogen/atif\_export/atif\_step\_builder.py                                                      |       45 |        1 |       14 |        3 |     93% |145-\>147, 188-\>196, 207 |
| src/glossogen/atif\_export/atif\_trajectory\_builder.py                                                |      159 |        4 |       68 |        6 |     96% |98, 118-119, 163, 179-\>152, 214-\>216, 332-\>334, 381-\>383 |
| src/glossogen/atif\_export/copied\_context.py                                                          |       34 |        5 |       10 |        3 |     82% |60, 78, 120-126, 139 |
| src/glossogen/atif\_export/seed\_history\_steps.py                                                     |       43 |        3 |       26 |        5 |     88% |68, 82, 83-\>102, 100-\>102, 125 |
| src/glossogen/atif\_export/tool\_definition\_reconstruction.py                                         |       28 |        3 |        2 |        0 |     90% |     59-61 |
| src/glossogen/autonomous\_supervisor.py                                                                |      204 |       35 |       52 |        8 |     82% |77, 113, 119, 163-168, 179-183, 194-206, 213, 270, 290-295, 307-\>299, 402-\>400, 487-495, 504-507, 531-532 |
| src/glossogen/channel\_router.py                                                                       |       94 |        1 |       34 |        1 |     98% |        83 |
| src/glossogen/cli.py                                                                                   |      742 |      323 |      174 |       24 |     54% |1108-1110, 1113-1115, 1118-1120, 1123-1125, 1128-1130, 1133-1135, 1138-1140, 1143-1145, 1148-1150, 1158-1160, 1173-1175, 1178-1180, 1189, 1194, 1203-1204, 1219-1227, 1248-1249, 1253-1261, 1277-1298, 1307, 1324-1336, 1348-1357, 1365-1367, 1377-1494, 1507-1546, 1659, 1678, 1680, 1731-1733, 1756, 1795-1796, 1814-1815, 1831-1848, 1863-1885, 1931, 1954-1974, 1979-1995, 2000, 2012-2014, 2023-2030, 2041-2095, 2106-2142, 2169-\>2166, 2201-2206, 2219-2229, 2243-2320, 2325-2333, 2342-2360, 2365-2381, 2386-2397, 2402-2408 |
| src/glossogen/config\_overrides.py                                                                     |       83 |        1 |       38 |        1 |     98% |       145 |
| src/glossogen/cross\_run\_replace\_agent.py                                                            |      132 |      104 |       42 |        0 |     16% |115-128, 143-147, 160-406, 423-426 |
| src/glossogen/cross\_run\_replace\_manifest.py                                                         |       10 |        0 |        2 |        0 |    100% |           |
| src/glossogen/dashboards/dashboard\_models.py                                                          |       37 |        0 |       10 |        0 |    100% |           |
| src/glossogen/dashboards/dashboard\_store.py                                                           |        5 |        0 |        0 |        0 |    100% |           |
| src/glossogen/dashboards/dashboard\_store\_resolution.py                                               |       11 |        1 |        2 |        1 |     85% |        22 |
| src/glossogen/dashboards/filesystem\_dashboard\_store.py                                               |       86 |        1 |       18 |        1 |     98% |        82 |
| src/glossogen/dashboards/legacy\_lineage\_translation.py                                               |       42 |        1 |       16 |        1 |     97% |        42 |
| src/glossogen/dashboards/postgres\_dashboard\_store.py                                                 |       70 |       46 |        6 |        0 |     32% |37, 46-47, 62, 73, 77-90, 109-121, 130-135, 144-171, 190-215, 219-225 |
| src/glossogen/db/\_\_init\_\_.py                                                                       |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/db/local\_tenant.py                                                                      |        5 |        0 |        0 |        0 |    100% |           |
| src/glossogen/db/pool.py                                                                               |       25 |       12 |        6 |        1 |     45% |31, 40-51, 56-59 |
| src/glossogen/db/queries.py                                                                            |      103 |       75 |       14 |        0 |     24% |30-38, 46-54, 69-96, 108-109, 122-133, 150-172, 188-200, 214-228, 251-278, 288-289, 302-303, 315-316, 329, 339, 371-372, 396-397, 415-427, 434-441, 460-481, 493-500 |
| src/glossogen/db/rows.py                                                                               |        6 |        0 |        0 |        0 |    100% |           |
| src/glossogen/db/run\_registry.py                                                                      |       22 |       11 |        6 |        1 |     43% |37-59, 86-87 |
| src/glossogen/dotenv\_loader.py                                                                        |       11 |        0 |        2 |        0 |    100% |           |
| src/glossogen/elapsed\_time.py                                                                         |        9 |        1 |        4 |        2 |     77% |26-\>25, 28 |
| src/glossogen/engine/\_\_init\_\_.py                                                                   |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/engine/round\_outcome\_log.py                                                            |       22 |        1 |        4 |        0 |     96% |        55 |
| src/glossogen/engine/round\_world.py                                                                   |       38 |        1 |       10 |        1 |     96% |       140 |
| src/glossogen/engine/team\_declaration.py                                                              |       13 |        0 |        2 |        0 |    100% |           |
| src/glossogen/engine/team\_structure.py                                                                |       41 |        0 |       14 |        0 |    100% |           |
| src/glossogen/eval\_manifest.py                                                                        |       37 |       22 |        6 |        1 |     37% |28-32, 45-52, 57-60, 65-71 |
| src/glossogen/evaluation/\_\_init\_\_.py                                                               |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/evaluation/log\_reader.py                                                                |       49 |        0 |       22 |        1 |     99% |   48-\>50 |
| src/glossogen/evaluation/metric\_core/\_\_init\_\_.py                                                  |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/evaluation/metric\_core/character\_entropy.py                                            |        8 |        1 |        2 |        1 |     80% |        22 |
| src/glossogen/evaluation/metric\_core/generic\_metric\_names.py                                        |        1 |        0 |        0 |        0 |    100% |           |
| src/glossogen/evaluation/metric\_core/gzip\_compression.py                                             |       11 |        1 |        2 |        1 |     85% |        34 |
| src/glossogen/evaluation/metric\_core/keyed\_observation.py                                            |        2 |        0 |        0 |        0 |    100% |           |
| src/glossogen/evaluation/metric\_core/keyed\_observation\_reader.py                                    |       17 |        3 |        0 |        0 |     82% |     31-33 |
| src/glossogen/evaluation/metric\_core/measurement.py                                                   |        7 |        0 |        0 |        0 |    100% |           |
| src/glossogen/evaluation/metric\_core/metric\_entry\_points.py                                         |        7 |        0 |        0 |        0 |    100% |           |
| src/glossogen/evaluation/metric\_core/metric\_execution\_error.py                                      |        6 |        0 |        0 |        0 |    100% |           |
| src/glossogen/evaluation/metric\_core/metric\_protocol.py                                              |       14 |        0 |        0 |        0 |    100% |           |
| src/glossogen/evaluation/metric\_core/metric\_registry.py                                              |       55 |        0 |       10 |        0 |    100% |           |
| src/glossogen/evaluation/metric\_core/metric\_run\_options.py                                          |        6 |        0 |        0 |        0 |    100% |           |
| src/glossogen/evaluation/metric\_core/mid\_run\_swap\_overrides.py                                     |       15 |        0 |        8 |        0 |    100% |           |
| src/glossogen/evaluation/metric\_core/optional\_ml\_backend.py                                         |       36 |       12 |       10 |        4 |     61% |55-\>53, 57-59, 80, 93-94, 102-105, 122-123 |
| src/glossogen/evaluation/metric\_core/primary\_channel\_messages.py                                    |       18 |        2 |       10 |        2 |     86% |    40, 43 |
| src/glossogen/evaluation/metric\_core/pristine\_text\_index.py                                         |       31 |        5 |       12 |        3 |     81% |44-45, 47, 50, 54 |
| src/glossogen/evaluation/metric\_core/protocol\_boundary.py                                            |        2 |        0 |        0 |        0 |    100% |           |
| src/glossogen/evaluation/metric\_core/protocol\_explanation\_config.py                                 |        3 |        0 |        0 |        0 |    100% |           |
| src/glossogen/evaluation/metric\_core/protocol\_probe\_config.py                                       |        3 |        0 |        0 |        0 |    100% |           |
| src/glossogen/evaluation/metric\_core/resume\_anchors.py                                               |       60 |       14 |       24 |        7 |     70% |69, 82, 103-109, 126, 143, 151, 159, 165 |
| src/glossogen/evaluation/metric\_core/round\_result\_index.py                                          |        7 |        7 |        4 |        0 |      0% |      9-24 |
| src/glossogen/evaluation/metric\_core/scored\_channels.py                                              |       13 |        0 |        6 |        0 |    100% |           |
| src/glossogen/evaluation/metric\_core/sidecar\_reading.py                                              |       65 |        7 |       30 |        6 |     86% |51-53, 58, 64-\>56, 78, 81-\>80, 104, 109 |
| src/glossogen/evaluation/metric\_core/surprisal\_stats.py                                              |       10 |        1 |        4 |        1 |     86% |        14 |
| src/glossogen/evaluation/metrics/\_\_init\_\_.py                                                       |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/evaluation/metrics/communication/\_\_init\_\_.py                                         |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/evaluation/metrics/communication/communication\_feature\_presence\_metric.py             |       81 |       15 |       20 |        6 |     77% |77-82, 85-88, 95, 100, 208, 214, 225-226, 237-251 |
| src/glossogen/evaluation/metrics/communication/communication\_open\_coding\_metric.py                  |       47 |        4 |        4 |        1 |     90% |65-70, 147-148 |
| src/glossogen/evaluation/metrics/communication/label\_models.py                                        |       34 |        1 |        0 |        0 |     97% |        26 |
| src/glossogen/evaluation/metrics/communication/round\_view.py                                          |        3 |        0 |        0 |        0 |    100% |           |
| src/glossogen/evaluation/metrics/content\_filter\_refusal\_metric.py                                   |       32 |        6 |        6 |        1 |     71% |     66-71 |
| src/glossogen/evaluation/metrics/dialog\_retransmission\_metric.py                                     |       84 |        5 |       18 |        6 |     89% |132-133, 238, 251, 252-\>248, 254, 282-\>284 |
| src/glossogen/evaluation/metrics/english\_ngram/\_\_init\_\_.py                                        |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/evaluation/metrics/english\_ngram/backoff\_ngram\_metric.py                              |       65 |        6 |       14 |        4 |     87% |83-84, 95-100, 159, 184 |
| src/glossogen/evaluation/metrics/english\_ngram/backoff\_ngram\_model.py                               |      110 |       41 |       44 |        9 |     57% |102, 117, 121, 128, 144, 146, 150, 174-182, 190, 194, 205-221, 242-257, 267-271 |
| src/glossogen/evaluation/metrics/english\_ngram/english\_ngram\_metric.py                              |       63 |        6 |       14 |        4 |     87% |76-77, 88-93, 148, 173 |
| src/glossogen/evaluation/metrics/english\_ngram/english\_ngram\_model.py                               |       73 |       24 |       18 |        1 |     64% |79, 113-121, 131-138, 148-158 |
| src/glossogen/evaluation/metrics/gzip\_compression\_ratio\_metric.py                                   |       52 |        5 |        8 |        3 |     87% |80-81, 92-97, 148 |
| src/glossogen/evaluation/metrics/language\_repetition\_metric.py                                       |      121 |        8 |       36 |        6 |     91% |132-133, 150-151, 211, 237, 240, 345 |
| src/glossogen/evaluation/metrics/language\_strangeness\_metric.py                                      |       38 |        3 |        6 |        2 |     89% | 71-72, 96 |
| src/glossogen/evaluation/metrics/mcm\_metric.py                                                        |       67 |        8 |       20 |        6 |     84% |70-71, 80-85, 140, 143, 166, 173 |
| src/glossogen/evaluation/metrics/mcr\_metric.py                                                        |       60 |        6 |       18 |        4 |     87% |59-60, 69-74, 129, 145 |
| src/glossogen/evaluation/metrics/message\_entropy\_metric.py                                           |       52 |        5 |        8 |        3 |     87% |73-74, 85-90, 140 |
| src/glossogen/evaluation/metrics/neologism\_metric.py                                                  |       39 |        3 |        6 |        2 |     89% |67-68, 100 |
| src/glossogen/evaluation/metrics/perplexity\_metric.py                                                 |       71 |        6 |       14 |        3 |     89% |81-82, 98-99, 163, 188 |
| src/glossogen/evaluation/metrics/probe\_usage\_report.py                                               |       14 |        0 |        2 |        0 |    100% |           |
| src/glossogen/evaluation/metrics/protocol\_explanation\_metric.py                                      |      116 |       28 |       32 |        8 |     68% |132, 171-176, 193-201, 228, 256, 267-274, 286-287, 309-318, 324 |
| src/glossogen/evaluation/metrics/protocol\_learned\_after\_swap\_metric.py                             |       62 |        4 |       14 |        3 |     91% |100-101, 108-114, 152-\>154 |
| src/glossogen/evaluation/metrics/protocol\_probe/\_\_init\_\_.py                                       |        5 |        0 |        0 |        0 |    100% |           |
| src/glossogen/evaluation/metrics/protocol\_probe/probe\_agent.py                                       |       33 |        1 |        2 |        1 |     94% |        52 |
| src/glossogen/evaluation/metrics/protocol\_probe/protocol\_probe\_agent\_pair\_similarity\_metric.py   |       90 |        5 |       24 |        3 |     93% |110, 186-190, 206-211 |
| src/glossogen/evaluation/metrics/protocol\_probe/protocol\_probe\_cutoff\_trajectory\_metric.py        |      118 |       13 |       46 |       10 |     86% |119, 125, 141, 163, 202-206, 211-\>209, 214-218, 284-287, 290, 294-297 |
| src/glossogen/evaluation/metrics/protocol\_probe/protocol\_probe\_metric.py                            |       96 |       12 |       22 |        5 |     86% |97-102, 125-130, 133-138, 165-170, 229-236, 284 |
| src/glossogen/evaluation/metrics/protocol\_probe/protocol\_probe\_replica\_self\_similarity\_metric.py |       74 |        5 |       16 |        4 |     90% |114, 178-182, 191-\>189, 194-198 |
| src/glossogen/evaluation/metrics/protocol\_probe/response\_models.py                                   |        6 |        0 |        0 |        0 |    100% |           |
| src/glossogen/evaluation/metrics/protocol\_probe/similarity\_core.py                                   |       60 |        7 |       24 |        5 |     86% |52, 58, 61-62, 97, 105, 130 |
| src/glossogen/evaluation/metrics/protocol\_probe/similarity\_observations.py                           |       22 |        1 |       10 |        1 |     94% |        48 |
| src/glossogen/evaluation/metrics/round\_ended/\_\_init\_\_.py                                          |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/evaluation/metrics/round\_ended/postmortem\_ended\_timeout\_metric.py                    |       25 |        0 |        2 |        0 |    100% |           |
| src/glossogen/evaluation/metrics/round\_ended/round\_ended\_idle\_metric.py                            |       25 |        1 |        2 |        1 |     93% |        48 |
| src/glossogen/evaluation/metrics/round\_ended/round\_ended\_timeout\_metric.py                         |       25 |        1 |        2 |        1 |     93% |        48 |
| src/glossogen/evaluation/metrics/round\_ended/trigger\_detection.py                                    |       27 |        0 |       20 |        2 |     96% |24-\>22, 56-\>54 |
| src/glossogen/evaluation/metrics/round\_success\_after\_resume\_metric.py                              |      117 |       26 |       42 |        9 |     72% |92-97, 122, 172, 178-198, 256, 272, 274, 283, 320-322 |
| src/glossogen/evaluation/metrics/round\_success\_metric.py                                             |       33 |        2 |       10 |        2 |     91% |    53, 70 |
| src/glossogen/evaluation/metrics/shorthand\_codes\_metric.py                                           |       41 |        2 |        8 |        1 |     94% |     76-77 |
| src/glossogen/evaluation/metrics/slang\_emergence\_metric.py                                           |       38 |        2 |        6 |        1 |     93% |     70-71 |
| src/glossogen/evaluation/prompts/\_\_init\_\_.py                                                       |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/evaluation/prompts/prompt\_renderer.py                                                   |        6 |        0 |        0 |        0 |    100% |           |
| src/glossogen/evaluation/reports/\_\_init\_\_.py                                                       |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/evaluation/reports/evaluation\_cost.py                                                   |       14 |        0 |        2 |        0 |    100% |           |
| src/glossogen/evaluation/reports/evaluation\_report.py                                                 |       47 |        6 |       10 |        2 |     86% |142, 144-151, 180-182 |
| src/glossogen/evaluation/round\_transcript\_builder.py                                                 |       43 |        5 |       18 |        4 |     82% |78-80, 92-\>94, 95, 98 |
| src/glossogen/evaluation/scenario\_evaluation\_runner.py                                               |       57 |        1 |       16 |        1 |     97% |        68 |
| src/glossogen/event\_bus.py                                                                            |       30 |       11 |        6 |        1 |     61% |38-41, 44-45, 62-64, 68-69 |
| src/glossogen/event\_logger.py                                                                         |       37 |        0 |        6 |        1 |     98% | 67-\>exit |
| src/glossogen/event\_parsing.py                                                                        |       15 |        0 |        6 |        0 |    100% |           |
| src/glossogen/frontend\_container.py                                                                   |       83 |       45 |       20 |        0 |     41% |84-117, 122-131, 138-142, 195-202, 211-228, 236-242, 247-253 |
| src/glossogen/knob\_filter.py                                                                          |      129 |        0 |       62 |        0 |    100% |           |
| src/glossogen/knobs\_resolution.py                                                                     |       26 |        0 |        8 |        0 |    100% |           |
| src/glossogen/label\_descriptions/\_\_init\_\_.py                                                      |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/label\_descriptions/filesystem\_label\_description\_store.py                             |       44 |        0 |        4 |        0 |    100% |           |
| src/glossogen/label\_descriptions/label\_description\_models.py                                        |        5 |        0 |        0 |        0 |    100% |           |
| src/glossogen/label\_descriptions/label\_description\_store.py                                         |        4 |        0 |        0 |        0 |    100% |           |
| src/glossogen/label\_descriptions/label\_description\_store\_resolution.py                             |       11 |        1 |        2 |        1 |     85% |        26 |
| src/glossogen/label\_descriptions/postgres\_label\_description\_store.py                               |       22 |       13 |        0 |        0 |     41% |20, 24-36, 40-42, 54-60 |
| src/glossogen/llm/\_\_init\_\_.py                                                                      |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/llm/claude\_provider.py                                                                  |       85 |       25 |       26 |        6 |     63% |31-32, 41-45, 61-63, 81, 148-\>153, 149-\>148, 154, 182-194, 207-\>209 |
| src/glossogen/llm/deferred\_provider.py                                                                |       21 |        0 |        4 |        0 |    100% |           |
| src/glossogen/llm/huggingface\_provider.py                                                             |       64 |       44 |       20 |        0 |     24% |28-35, 51-53, 70-78, 98-142, 147-152 |
| src/glossogen/llm/max\_tokens.py                                                                       |       18 |        9 |        4 |        1 |     45% |     31-47 |
| src/glossogen/llm/openai\_provider.py                                                                  |       76 |       57 |       34 |        0 |     17% |22-26, 42-43, 58-65, 84-136, 146-151, 166-176 |
| src/glossogen/llm/provider.py                                                                          |       20 |        0 |        0 |        0 |    100% |           |
| src/glossogen/llm/provider\_factory.py                                                                 |       13 |        7 |        6 |        0 |     32% |     21-27 |
| src/glossogen/llm/token\_counter.py                                                                    |       53 |       27 |        6 |        0 |     47% |53-56, 60-71, 82-85, 89-100, 108, 117-125 |
| src/glossogen/logging\_format.py                                                                       |       21 |       10 |        2 |        0 |     48% |23-33, 45-46, 50-56 |
| src/glossogen/mcp\_tool\_rejection.py                                                                  |       14 |        7 |        0 |        0 |     50% |     29-36 |
| src/glossogen/message\_history\_builder.py                                                             |      230 |       64 |      130 |       18 |     69% |95, 97-\>82, 133-139, 166, 185-189, 207, 238, 271-298, 307, 358, 364, 370-378, 391, 436-451, 484, 602, 614, 649-\>647, 682 |
| src/glossogen/message\_rewind.py                                                                       |      102 |       17 |       46 |        5 |     78% |181-185, 251, 265, 278-\>249, 284, 379-387, 404-408, 443 |
| src/glossogen/model\_catalog.py                                                                        |       29 |        3 |        8 |        0 |     92% |     44-46 |
| src/glossogen/models/\_\_init\_\_.py                                                                   |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/models/agent\_config.py                                                                  |        8 |        0 |        0 |        0 |    100% |           |
| src/glossogen/models/channel.py                                                                        |        7 |        0 |        0 |        0 |    100% |           |
| src/glossogen/models/compaction\_config.py                                                             |        5 |        0 |        0 |        0 |    100% |           |
| src/glossogen/models/event.py                                                                          |       88 |        0 |        0 |        0 |    100% |           |
| src/glossogen/models/event\_base.py                                                                    |        7 |        0 |        0 |        0 |    100% |           |
| src/glossogen/models/mcp\_responses.py                                                                 |        4 |        0 |        0 |        0 |    100% |           |
| src/glossogen/models/message.py                                                                        |       13 |        2 |        4 |        2 |     76% |    30, 34 |
| src/glossogen/models/model\_consumer.py                                                                |        2 |        0 |        0 |        0 |    100% |           |
| src/glossogen/models/runner\_prompts.py                                                                |        3 |        0 |        0 |        0 |    100% |           |
| src/glossogen/models/thinking\_part\_record.py                                                         |        2 |        0 |        0 |        0 |    100% |           |
| src/glossogen/models/tool\_definition.py                                                               |        4 |        0 |        0 |        0 |    100% |           |
| src/glossogen/models/unread\_channel\_messages.py                                                      |        3 |        0 |        0 |        0 |    100% |           |
| src/glossogen/oauth\_client.py                                                                         |      177 |      133 |       26 |        0 |     22% |54, 68-72, 77-83, 98-111, 116-118, 125-128, 132-153, 158-169, 183-198, 210-223, 233-239, 244-247, 252-257, 267-342, 347, 360-398, 406-410, 415-416 |
| src/glossogen/plugin\_entry\_points.py                                                                 |       23 |        1 |        6 |        1 |     93% |        76 |
| src/glossogen/port\_allocator.py                                                                       |        6 |        4 |        0 |        0 |     33% |     13-16 |
| src/glossogen/prod\_metadata\_sync.py                                                                  |      199 |      126 |       66 |        2 |     30% |101-116, 132-155, 227-230, 252, 261-265, 277, 299-308, 322-361, 376-393, 410-430, 439-526 |
| src/glossogen/prod\_push.py                                                                            |      146 |      117 |       52 |        0 |     15% |69-84, 94-126, 140-159, 164-165, 181-189, 199-230, 244-262, 271-324 |
| src/glossogen/provider\_credentials.py                                                                 |       87 |        1 |       32 |        1 |     98% |       265 |
| src/glossogen/recorded\_scenario\_rebuild.py                                                           |       31 |        5 |        8 |        1 |     85% |38-40, 73-78 |
| src/glossogen/replace\_agent.py                                                                        |      254 |       43 |      140 |       23 |     79% |176-\>180, 200, 212, 302, 304, 358-\>363, 390-\>403, 392-399, 404-409, 443, 445, 450-475, 494, 497, 567, 591, 616, 627, 635, 641, 654-\>668, 657-663, 745-749, 798-801 |
| src/glossogen/replace\_manifest.py                                                                     |       14 |        0 |        2 |        0 |    100% |           |
| src/glossogen/resume\_context\_writer.py                                                               |       34 |        8 |       14 |        3 |     73% |41, 43, 64, 80-88 |
| src/glossogen/resume\_state\_loader.py                                                                 |      142 |        5 |       54 |        6 |     94% |312, 316, 383, 526, 552-\>554, 556 |
| src/glossogen/run\_analysis/\_\_init\_\_.py                                                            |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/run\_analysis/aggregation.py                                                             |       42 |        0 |       24 |        0 |    100% |           |
| src/glossogen/run\_analysis/analysis\_field\_catalog.py                                                |       61 |        1 |       18 |        1 |     97% |        60 |
| src/glossogen/run\_analysis/analysis\_grain.py                                                         |        6 |        0 |        0 |        0 |    100% |           |
| src/glossogen/run\_analysis/analysis\_limits.py                                                        |        3 |        0 |        0 |        0 |    100% |           |
| src/glossogen/run\_analysis/analysis\_query\_engine.py                                                 |       56 |        1 |       12 |        1 |     97% |        88 |
| src/glossogen/run\_analysis/analysis\_query\_models.py                                                 |       41 |        2 |       16 |        3 |     91% |87, 89-\>91, 92 |
| src/glossogen/run\_analysis/analysis\_result\_models.py                                                |       14 |        0 |        0 |        0 |    100% |           |
| src/glossogen/run\_analysis/analysis\_run\_record.py                                                   |       31 |        0 |        4 |        0 |    100% |           |
| src/glossogen/run\_analysis/analysis\_spec\_parsing.py                                                 |       39 |        1 |       10 |        1 |     96% |        66 |
| src/glossogen/run\_analysis/analysis\_text\_table.py                                                   |       53 |        0 |       24 |        2 |     97% |46-\>48, 85-\>88 |
| src/glossogen/run\_analysis/dimension\_filter.py                                                       |       55 |        2 |       24 |        2 |     95% |    83, 93 |
| src/glossogen/run\_analysis/measure\_resolution.py                                                     |       24 |        0 |        0 |        0 |    100% |           |
| src/glossogen/run\_analysis/metric\_inventory.py                                                       |       24 |        0 |       12 |        0 |    100% |           |
| src/glossogen/run\_analysis/observation\_row.py                                                        |        2 |        0 |        0 |        0 |    100% |           |
| src/glossogen/run\_analysis/observation\_table.py                                                      |      111 |        2 |       50 |        2 |     98% |   53, 196 |
| src/glossogen/run\_archive.py                                                                          |       92 |       30 |       32 |        5 |     64% |56, 64, 123-133, 155, 158, 182-183, 198-210, 227-228 |
| src/glossogen/run\_config\_validation.py                                                               |       33 |        7 |       12 |        3 |     69% |32-\>54, 34, 67-72 |
| src/glossogen/run\_export/\_\_init\_\_.py                                                              |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/run\_export/agent\_identity\_columns.py                                                  |       22 |        0 |        8 |        0 |    100% |           |
| src/glossogen/run\_export/agent\_level\_frame.py                                                       |       56 |        3 |       24 |        4 |     91% |55, 85, 102-\>106, 117 |
| src/glossogen/run\_export/archive\_member\_filter.py                                                   |       18 |        0 |       12 |        0 |    100% |           |
| src/glossogen/run\_export/csv\_cell\_text.py                                                           |       48 |        2 |       22 |        2 |     94% |   93, 105 |
| src/glossogen/run\_export/csv\_export\_archive.py                                                      |       77 |        3 |       28 |        3 |     94% |95, 126, 147 |
| src/glossogen/run\_export/csv\_frame.py                                                                |        3 |        0 |        0 |        0 |    100% |           |
| src/glossogen/run\_export/csv\_frame\_writer.py                                                        |       26 |        1 |        6 |        1 |     94% |        63 |
| src/glossogen/run\_export/export\_column\_catalog.py                                                   |       72 |        2 |       30 |        2 |     96% |   74, 136 |
| src/glossogen/run\_export/export\_limits.py                                                            |       17 |        0 |        6 |        0 |    100% |           |
| src/glossogen/run\_export/export\_preview\_models.py                                                   |        4 |        0 |        0 |        0 |    100% |           |
| src/glossogen/run\_export/export\_request\_models.py                                                   |       30 |        0 |        0 |        0 |    100% |           |
| src/glossogen/run\_export/export\_run\_record.py                                                       |       24 |        3 |        0 |        0 |     88% |     49-54 |
| src/glossogen/run\_export/knob\_flattening.py                                                          |       30 |        1 |       12 |        1 |     95% |        63 |
| src/glossogen/run\_export/label\_value\_columns.py                                                     |       18 |        1 |        8 |        1 |     92% |        45 |
| src/glossogen/run\_export/lineage\_columns.py                                                          |       23 |        2 |       12 |        2 |     89% |    29, 31 |
| src/glossogen/run\_export/message\_event\_scan.py                                                      |       64 |        6 |       26 |        5 |     86% |94, 101-102, 107-\>109, 117, 129-130 |
| src/glossogen/run\_export/message\_level\_frame.py                                                     |       50 |        0 |       12 |        1 |     98% | 144-\>148 |
| src/glossogen/run\_export/message\_repetition\_sidecar.py                                              |       30 |        7 |       12 |        4 |     74% |32, 35, 40, 42, 44-48 |
| src/glossogen/run\_export/metric\_column\_projection.py                                                |       42 |        9 |       16 |        0 |     74% |69-71, 76-78, 101-103 |
| src/glossogen/run\_export/model\_weight\_class.py                                                      |       25 |        0 |       12 |        0 |    100% |           |
| src/glossogen/run\_export/primary\_channel\_resolution.py                                              |       24 |        0 |        8 |        0 |    100% |           |
| src/glossogen/run\_export/round\_context\_frame.py                                                     |       67 |        6 |       18 |        3 |     89% |65, 121, 126-131, 137 |
| src/glossogen/run\_export/round\_level\_frame.py                                                       |       39 |        3 |       16 |        3 |     89% |54, 82, 98 |
| src/glossogen/run\_export/run\_context\_columns.py                                                     |       24 |        0 |        6 |        0 |    100% |           |
| src/glossogen/run\_export/run\_level\_frame.py                                                         |       34 |        4 |        8 |        2 |     86% |46-47, 68-69 |
| src/glossogen/run\_export/run\_message\_records.py                                                     |       32 |        0 |        2 |        0 |    100% |           |
| src/glossogen/run\_export/run\_metadata\_columns.py                                                    |        8 |        0 |        0 |        0 |    100% |           |
| src/glossogen/run\_export/run\_selection\_resolution.py                                                |       48 |        3 |       28 |        1 |     92% |     60-62 |
| src/glossogen/run\_export/runs\_zip\_archive.py                                                        |       85 |        0 |       16 |        0 |    100% |           |
| src/glossogen/run\_identity.py                                                                         |        2 |        0 |        0 |        0 |    100% |           |
| src/glossogen/run\_jsonl\_rewriter.py                                                                  |       47 |        2 |       20 |        2 |     94% |   67, 110 |
| src/glossogen/run\_launching.py                                                                        |        7 |        2 |        0 |        0 |     71% |     29-30 |
| src/glossogen/run\_lineage.py                                                                          |       16 |        9 |        4 |        0 |     35% |33-41, 46-47 |
| src/glossogen/runners/\_\_init\_\_.py                                                                  |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/runners/agent\_run\_result.py                                                            |        2 |        0 |        0 |        0 |    100% |           |
| src/glossogen/runners/agent\_runner\_base.py                                                           |        5 |        0 |        0 |        0 |    100% |           |
| src/glossogen/runners/agent\_tools.py                                                                  |       86 |        6 |       22 |        4 |     91% |123, 182, 196-202, 207, 232, 242-\>244 |
| src/glossogen/runners/communication\_protocol.py                                                       |       26 |        0 |        6 |        0 |    100% |           |
| src/glossogen/runners/history\_cleanup\_processor.py                                                   |      113 |       10 |       50 |        9 |     88% |65, 68, 74, 94, 107, 109, 162, 165, 170-171 |
| src/glossogen/runners/pydantic\_ai\_model\_factory.py                                                  |       28 |       13 |       10 |        3 |     47% |24-32, 44-49, 51, 73-83 |
| src/glossogen/runners/pydantic\_ai\_runner.py                                                          |      353 |       59 |      112 |       22 |     77% |89, 92-\>94, 107, 115-116, 211-\>210, 214-220, 272, 346-356, 403, 429, 451-459, 561, 615-628, 697-699, 704-\>712, 752-778, 783-786, 803, 883-\>exit, 899-907, 911, 912-\>exit, 931, 932-\>943, 935-\>943, 937-938, 977-\>exit |
| src/glossogen/runners/read\_notifications\_tool.py                                                     |       56 |        2 |       10 |        3 |     92% |56-\>55, 59, 123 |
| src/glossogen/runtime/\_\_init\_\_.py                                                                  |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/runtime/activity\_notification.py                                                        |       18 |        0 |        0 |        0 |    100% |           |
| src/glossogen/runtime/agent\_session.py                                                                |       61 |        0 |        6 |        0 |    100% |           |
| src/glossogen/runtime/agent\_swap.py                                                                   |       95 |       20 |       10 |        4 |     77% |79, 82, 96, 201-219, 255, 287-288 |
| src/glossogen/runtime/communication\_tools.py                                                          |       29 |        2 |        4 |        2 |     88% |   45, 101 |
| src/glossogen/runtime/game\_clock.py                                                                   |      159 |        7 |       52 |        4 |     95% |61, 66, 148, 199-\>205, 311-315, 402-406 |
| src/glossogen/runtime/notification\_payload.py                                                         |       47 |        2 |       14 |        2 |     93% |   54, 131 |
| src/glossogen/runtime/read\_notifications\_schema.py                                                   |       17 |        0 |        0 |        0 |    100% |           |
| src/glossogen/runtime/scenario\_tool.py                                                                |        3 |        0 |        0 |        0 |    100% |           |
| src/glossogen/runtime/scenario\_world.py                                                               |       94 |       19 |       14 |        2 |     75% |78, 104, 133-150, 165-169 |
| src/glossogen/runtime/scheduled\_events.py                                                             |       40 |        5 |        8 |        1 |     79% |93-94, 118-120 |
| src/glossogen/runtime/scheduler.py                                                                     |       32 |        4 |       12 |        2 |     82% |81, 94-100 |
| src/glossogen/runtime/simulation\_state.py                                                             |      235 |       26 |       62 |        9 |     87% |176, 231, 238, 305, 328, 349-359, 438, 480, 491-505, 553-559, 566 |
| src/glossogen/runtime/wait\_for.py                                                                     |        5 |        0 |        0 |        0 |    100% |           |
| src/glossogen/runtime/wait\_registry.py                                                                |      133 |        3 |       40 |        4 |     96% |201, 240-\>242, 244, 250 |
| src/glossogen/scaffold\_templates/ids.py.jinja                                                         |        6 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scaffold\_templates/knobs\_default.json.jinja                                            |        1 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenario\_api.py                                                                         |        1 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenario\_conformance.py                                                                 |      348 |       62 |      164 |       41 |     79% |80, 114-116, 185-187, 191, 194, 205, 212, 215, 218, 220, 234, 249, 251, 259, 276, 290, 298, 301, 314, 321, 388, 397, 412, 419, 441-447, 469-475, 488, 501, 518, 530, 538, 542, 548, 566, 582, 602, 605-609, 622, 668, 685, 694-696, 716, 734-735, 737, 740, 750, 753 |
| src/glossogen/scenario\_entry\_points.py                                                               |       34 |        0 |       10 |        0 |    100% |           |
| src/glossogen/scenario\_loader.py                                                                      |       89 |        2 |       28 |        0 |     98% |   275-276 |
| src/glossogen/scenario\_package\_checks.py                                                             |      129 |       14 |       54 |       11 |     86% |99, 156-158, 164, 202, 212, 268, 271, 274-\>281, 277, 280, 324-325, 338 |
| src/glossogen/scenario\_path\_loader.py                                                                |      109 |       11 |       32 |        9 |     86% |102, 135, 145-146, 166-167, 199, 218, 243, 260-\>exit, 288, 294 |
| src/glossogen/scenario\_protocol.py                                                                    |      215 |        6 |       24 |        4 |     96% |155, 282, 308, 480, 694, 766 |
| src/glossogen/scenario\_registry.py                                                                    |       12 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenario\_scaffold.py                                                                    |       44 |        0 |        8 |        0 |    100% |           |
| src/glossogen/scenario\_submodule\_discovery.py                                                        |       42 |        1 |       14 |        2 |     95% |83, 111-\>113 |
| src/glossogen/scenario\_target.py                                                                      |       27 |        1 |       10 |        1 |     95% |       100 |
| src/glossogen/scenarios/\_\_init\_\_.py                                                                |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/base\_knobs.py                                                                 |       18 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/channel\_noise.py                                                              |       20 |        3 |        6 |        1 |     85% | 61, 67-68 |
| src/glossogen/scenarios/container\_yard\_stacking/\_\_init\_\_.py                                      |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/container\_yard\_stacking/case\_event\_conversion.py                           |       17 |        0 |        4 |        0 |    100% |           |
| src/glossogen/scenarios/container\_yard\_stacking/case\_rendering.py                                   |        3 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/container\_yard\_stacking/container\_attributes.py                             |        8 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/container\_yard\_stacking/evaluation/\_\_init\_\_.py                           |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/container\_yard\_stacking/evaluation/build\_communication\_rounds.py           |       63 |       38 |       24 |        3 |     32% |42-46, 59, 64-67, 72-95, 102-103, 113-117 |
| src/glossogen/scenarios/container\_yard\_stacking/events.py                                            |       12 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/container\_yard\_stacking/ids.py                                               |       50 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/container\_yard\_stacking/injection\_rendering.py                              |       48 |       13 |       22 |        6 |     64% |39, 43, 75, 96, 107, 113-117, 124-126 |
| src/glossogen/scenarios/container\_yard\_stacking/judging.py                                           |       70 |       22 |       28 |        5 |     60% |42-44, 83, 114-118, 188, 192, 198-200, 205-212 |
| src/glossogen/scenarios/container\_yard\_stacking/knobs.py                                             |       53 |       19 |       28 |        8 |     52% |61, 63, 69, 71, 78, 88-95, 100, 102-114 |
| src/glossogen/scenarios/container\_yard\_stacking/outcome\_reconstruction.py                           |       58 |       46 |       30 |        0 |     14% |40-62, 77-79, 90-120 |
| src/glossogen/scenarios/container\_yard\_stacking/run\_detail\_extension.py                            |       54 |       33 |       18 |        0 |     29% |73, 84-89, 93-95, 102-109, 127-139, 155-158 |
| src/glossogen/scenarios/container\_yard\_stacking/scenario.py                                          |      173 |       26 |       56 |       13 |     79% |107, 121, 211, 227, 238, 252, 262, 282, 301, 310, 317, 344-357, 370, 393-395 |
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
| src/glossogen/scenarios/drive\_module\_repair/evaluation/build\_communication\_rounds.py               |       52 |       29 |       18 |        3 |     37% |40-46, 59-63, 71-91, 98-99, 109-113 |
| src/glossogen/scenarios/drive\_module\_repair/events.py                                                |       12 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/drive\_module\_repair/ids.py                                                   |       24 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/drive\_module\_repair/injection\_rendering.py                                  |       18 |        3 |        6 |        3 |     75% |39, 49, 67 |
| src/glossogen/scenarios/drive\_module\_repair/knobs.py                                                 |       21 |        4 |        8 |        4 |     72% |71, 73, 78, 80 |
| src/glossogen/scenarios/drive\_module\_repair/replacement\_judge.py                                    |       22 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/drive\_module\_repair/run\_detail\_extension.py                                |       42 |       21 |       14 |        0 |     38% |105-134, 146-164, 180-181 |
| src/glossogen/scenarios/drive\_module\_repair/scenario.py                                              |      127 |        7 |       24 |        6 |     91% |207, 219, 221, 229, 231, 233, 324 |
| src/glossogen/scenarios/drive\_module\_repair/team\_declaration.py                                     |       13 |        0 |        2 |        0 |    100% |           |
| src/glossogen/scenarios/drive\_module\_repair/tools.py                                                 |       30 |        5 |       14 |        6 |     75% |38, 40, 45, 47, 50, 59-\>72 |
| src/glossogen/scenarios/drive\_module\_repair/world.py                                                 |      178 |       64 |       68 |       19 |     57% |62-66, 71-73, 105, 121, 123, 130, 145, 149-153, 156-157, 173-180, 203-234, 267, 275, 292, 302, 306, 323, 331, 337, 344, 350-357, 361-362, 371, 373 |
| src/glossogen/scenarios/drive\_module\_repair/world\_state.py                                          |        2 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/hospital\_bed\_assignment\_privacy/\_\_init\_\_.py                             |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/hospital\_bed\_assignment\_privacy/events.py                                   |       12 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/hospital\_bed\_assignment\_privacy/hospital\_cases.py                          |       70 |        1 |       18 |        3 |     95% |195-\>191, 245-\>244, 273 |
| src/glossogen/scenarios/hospital\_bed\_assignment\_privacy/ids.py                                      |       32 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/hospital\_bed\_assignment\_privacy/knobs.py                                    |       30 |        8 |       16 |        8 |     65% |49, 51, 55, 59, 64, 74, 80, 90 |
| src/glossogen/scenarios/hospital\_bed\_assignment\_privacy/scenario.py                                 |      219 |       52 |       94 |       27 |     69% |237, 254, 262, 274, 287, 294, 316, 320, 322, 327-330, 342, 375, 377, 383, 393, 398, 403, 417-\>429, 446, 460, 462, 468, 477, 482, 496, 498-\>509, 527, 567-607 |
| src/glossogen/scenarios/hospital\_bed\_assignment\_privacy/team\_declaration.py                        |       11 |        0 |        2 |        0 |    100% |           |
| src/glossogen/scenarios/hospital\_bed\_assignment\_privacy/world.py                                    |      130 |       19 |       44 |       11 |     80% |114, 129, 178, 183, 188, 195, 199-217, 231, 236, 239, 292, 309-\>311, 314, 316 |
| src/glossogen/scenarios/orbital\_anomaly/\_\_init\_\_.py                                               |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/orbital\_anomaly/actuation\_judge.py                                           |       17 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/orbital\_anomaly/events.py                                                     |        8 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/orbital\_anomaly/ids.py                                                        |       25 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/orbital\_anomaly/injection\_rendering.py                                       |       22 |        3 |        8 |        3 |     80% |37, 55, 73 |
| src/glossogen/scenarios/orbital\_anomaly/knobs.py                                                      |       15 |        4 |        8 |        4 |     65% |47, 49, 55, 57 |
| src/glossogen/scenarios/orbital\_anomaly/orbital\_anomaly\_cases.py                                    |       44 |        1 |        6 |        1 |     96% |       419 |
| src/glossogen/scenarios/orbital\_anomaly/run\_detail\_extension.py                                     |       41 |       21 |       14 |        0 |     36% |82-105, 117-135, 151-152 |
| src/glossogen/scenarios/orbital\_anomaly/scenario.py                                                   |      113 |        5 |       26 |        5 |     93% |182, 194, 204, 208, 226 |
| src/glossogen/scenarios/orbital\_anomaly/team\_declaration.py                                          |       11 |        0 |        2 |        0 |    100% |           |
| src/glossogen/scenarios/orbital\_anomaly/tools.py                                                      |       32 |        6 |       16 |        7 |     73% |35, 37, 39, 41, 44, 53-\>64, 73 |
| src/glossogen/scenarios/orbital\_anomaly/world.py                                                      |      103 |       21 |       36 |       14 |     75% |82, 92, 94, 113, 122-132, 149, 151, 153, 159, 165, 171-178, 180, 184-185, 201, 236 |
| src/glossogen/scenarios/prisoners\_dilemma/\_\_init\_\_.py                                             |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/prisoners\_dilemma/events.py                                                   |        6 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/prisoners\_dilemma/ids.py                                                      |       13 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/prisoners\_dilemma/knobs.py                                                    |       16 |        2 |        4 |        2 |     80% |    43, 48 |
| src/glossogen/scenarios/prisoners\_dilemma/scenario.py                                                 |       91 |        2 |       14 |        2 |     96% |  135, 229 |
| src/glossogen/scenarios/prisoners\_dilemma/tools.py                                                    |       25 |        3 |        4 |        1 |     86% | 30, 35-36 |
| src/glossogen/scenarios/prisoners\_dilemma/world.py                                                    |       57 |        2 |       12 |        2 |     94% |   81, 141 |
| src/glossogen/scenarios/satellite\_contact\_window/\_\_init\_\_.py                                     |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/satellite\_contact\_window/cases.py                                            |       67 |        1 |       10 |        1 |     97% |       352 |
| src/glossogen/scenarios/satellite\_contact\_window/command\_judge.py                                   |       33 |        1 |        4 |        1 |     95% |        45 |
| src/glossogen/scenarios/satellite\_contact\_window/evaluation/\_\_init\_\_.py                          |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/satellite\_contact\_window/events.py                                           |       21 |        2 |        4 |        2 |     84% |    62, 66 |
| src/glossogen/scenarios/satellite\_contact\_window/ids.py                                              |       25 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/satellite\_contact\_window/knobs.py                                            |       20 |        4 |        8 |        4 |     71% |48, 56, 62, 64 |
| src/glossogen/scenarios/satellite\_contact\_window/scenario.py                                         |      184 |       21 |       66 |       19 |     83% |189, 196, 212, 228, 242, 252, 268, 279, 287, 291, 301, 305-308, 311, 315, 420, 425, 427, 430, 510 |
| src/glossogen/scenarios/satellite\_contact\_window/team\_declaration.py                                |       13 |        0 |        2 |        0 |    100% |           |
| src/glossogen/scenarios/satellite\_contact\_window/world.py                                            |      121 |       18 |       34 |       13 |     80% |91, 116, 153-161, 174, 184, 204, 246, 248, 253, 259, 266-275, 277, 281-282, 298, 302 |
| src/glossogen/scenarios/spillway\_release/\_\_init\_\_.py                                              |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/spillway\_release/case\_event\_conversion.py                                   |        4 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/spillway\_release/events.py                                                    |       12 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/spillway\_release/ids.py                                                       |       25 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/spillway\_release/injection\_rendering.py                                      |       28 |        3 |       12 |        3 |     85% |64, 77, 95 |
| src/glossogen/scenarios/spillway\_release/knobs.py                                                     |       31 |        7 |       14 |        7 |     69% |60, 69, 71, 79, 85, 90, 92 |
| src/glossogen/scenarios/spillway\_release/scenario.py                                                  |      109 |        3 |       20 |        3 |     95% |183, 195, 226 |
| src/glossogen/scenarios/spillway\_release/spillway\_cases.py                                           |       85 |        6 |       26 |        4 |     91% |69-70, 77, 204-205, 258 |
| src/glossogen/scenarios/spillway\_release/team\_declaration.py                                         |       13 |        0 |        2 |        0 |    100% |           |
| src/glossogen/scenarios/spillway\_release/tools.py                                                     |       70 |       20 |       38 |       18 |     63% |40, 43, 57, 59, 62, 64, 66, 69-71, 82-\>94, 103, 105, 108, 111-\>120, 124-134, 142, 146, 149, 152-\>159 |
| src/glossogen/scenarios/spillway\_release/world.py                                                     |      113 |       16 |       28 |       10 |     82% |72, 91, 100, 105, 130, 138, 153, 165, 182, 196, 203, 209-216, 220-221, 230 |
| src/glossogen/scenarios/spillway\_release/world\_state.py                                              |       41 |        4 |       16 |        4 |     86% |61, 63, 73, 80 |
| src/glossogen/scenarios/spot\_the\_difference/\_\_init\_\_.py                                          |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/spot\_the\_difference/case\_event\_conversion.py                               |       13 |        0 |        2 |        0 |    100% |           |
| src/glossogen/scenarios/spot\_the\_difference/difference\_judge.py                                     |       41 |        5 |        4 |        1 |     87% |     84-88 |
| src/glossogen/scenarios/spot\_the\_difference/evaluation/\_\_init\_\_.py                               |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/spot\_the\_difference/evaluation/build\_communication\_rounds.py               |       56 |       31 |       24 |        3 |     35% |37-41, 54, 59-61, 66-80, 87-88, 98-102 |
| src/glossogen/scenarios/spot\_the\_difference/events.py                                                |        9 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/spot\_the\_difference/ids.py                                                   |       44 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/spot\_the\_difference/injection\_rendering.py                                  |       23 |        3 |        8 |        3 |     81% |38, 58, 78 |
| src/glossogen/scenarios/spot\_the\_difference/knobs.py                                                 |       61 |       15 |       30 |       15 |     67% |81, 83, 89, 93, 101, 103, 109, 113, 121, 124, 133, 141, 150, 154, 161 |
| src/glossogen/scenarios/spot\_the\_difference/outcome\_reconstruction.py                               |       62 |       52 |       30 |        0 |     11% |43-99, 116-152 |
| src/glossogen/scenarios/spot\_the\_difference/run\_detail\_extension.py                                |       61 |       38 |       22 |        0 |     28% |92, 104-109, 113, 127-139, 153-171, 182-196, 212-214 |
| src/glossogen/scenarios/spot\_the\_difference/scenario.py                                              |      164 |       12 |       48 |       11 |     89% |233, 249, 251, 262, 271, 273, 288, 290, 419, 423, 425, 431 |
| src/glossogen/scenarios/spot\_the\_difference/scene\_generation.py                                     |      221 |        5 |       56 |        4 |     97% |195, 363, 399, 450-455 |
| src/glossogen/scenarios/spot\_the\_difference/scripts/\_\_init\_\_.py                                  |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/spot\_the\_difference/scripts/check\_scene\_generation.py                      |       70 |       70 |       24 |        0 |      0% |    14-142 |
| src/glossogen/scenarios/spot\_the\_difference/team\_declaration.py                                     |       27 |        0 |        8 |        0 |    100% |           |
| src/glossogen/scenarios/spot\_the\_difference/team\_routing.py                                         |       41 |        1 |       20 |        0 |     98% |        88 |
| src/glossogen/scenarios/spot\_the\_difference/tools.py                                                 |       59 |        8 |       22 |        8 |     80% |47, 49, 52, 55, 58, 62, 108, 160 |
| src/glossogen/scenarios/spot\_the\_difference/world.py                                                 |      174 |       26 |       64 |       14 |     81% |100, 105, 123, 209, 221, 236, 264, 284, 289, 298, 305, 312, 316-332, 362, 372, 377, 382-384, 391 |
| src/glossogen/scenarios/spot\_the\_difference/world\_state.py                                          |       60 |        1 |       12 |        3 |     94% |90, 171-\>175, 173-\>175 |
| src/glossogen/scenarios/veyru/\_\_init\_\_.py                                                          |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/veyru/case\_event\_conversion.py                                               |        4 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/veyru/evaluation/\_\_init\_\_.py                                               |        1 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/veyru/evaluation/build\_communication\_rounds.py                               |       46 |       24 |       16 |        3 |     40% |40-46, 59-77, 89-90, 100-104 |
| src/glossogen/scenarios/veyru/evaluation/metrics/\_\_init\_\_.py                                       |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/veyru/events.py                                                                |       12 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/veyru/ids.py                                                                   |       44 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/veyru/injection\_rendering.py                                                  |      107 |       31 |       62 |       14 |     65% |43, 53-59, 69, 86, 124, 135, 137, 141, 160-175, 180-190, 215, 236, 241, 257 |
| src/glossogen/scenarios/veyru/knobs.py                                                                 |       34 |        8 |       22 |        8 |     71% |74, 76, 96, 102, 104, 109, 111, 117 |
| src/glossogen/scenarios/veyru/outcome\_reconstruction.py                                               |       70 |       46 |       36 |        2 |     28% |44, 51, 95-141, 161-166 |
| src/glossogen/scenarios/veyru/run\_detail\_extension.py                                                |       92 |       63 |       42 |        0 |     22% |134-140, 144-171, 183-201, 209-230, 242-259, 275 |
| src/glossogen/scenarios/veyru/scenario.py                                                              |      194 |       27 |       58 |       12 |     81% |201, 265, 292, 334, 339, 343, 351, 368, 373, 375, 378-383, 398-401, 412-413, 428-441, 461-462 |
| src/glossogen/scenarios/veyru/scripts/\_\_init\_\_.py                                                  |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/veyru/scripts/build\_probe\_questions.py                                       |       28 |       28 |        4 |        0 |      0% |    12-105 |
| src/glossogen/scenarios/veyru/scripts/inspect\_replaced\_agent\_input.py                               |       74 |       74 |       30 |        0 |      0% |    22-150 |
| src/glossogen/scenarios/veyru/scripts/repro\_opus47\_refusal.py                                        |      144 |      144 |       50 |        0 |      0% |    22-256 |
| src/glossogen/scenarios/veyru/scripts/run\_baseline\_no\_specialist.py                                 |       79 |       79 |       18 |        0 |      0% |     8-130 |
| src/glossogen/scenarios/veyru/scripts/run\_baseline\_no\_specialist\_opus47.py                         |      118 |      118 |       42 |        0 |      0% |    15-184 |
| src/glossogen/scenarios/veyru/scripts/run\_evals\_no\_specialist.py                                    |       62 |       62 |       16 |        0 |      0% |     9-104 |
| src/glossogen/scenarios/veyru/scripts/run\_smoke\_8.py                                                 |       78 |       78 |       16 |        0 |      0% |     9-128 |
| src/glossogen/scenarios/veyru/stabilization\_judge.py                                                  |       22 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/veyru/team\_declaration.py                                                     |       41 |        0 |       12 |        0 |    100% |           |
| src/glossogen/scenarios/veyru/team\_lifecycle.py                                                       |       55 |       43 |       24 |        1 |     16% |43-102, 107-119, 130-158, 176-181 |
| src/glossogen/scenarios/veyru/tools.py                                                                 |       63 |       20 |       20 |        9 |     65% |42-55, 59, 62-72, 74-84, 88-98, 107-\>118, 138-148, 178, 199-201 |
| src/glossogen/scenarios/veyru/veyru\_cases.py                                                          |       71 |        7 |        8 |        1 |     90% |435, 520-551 |
| src/glossogen/scenarios/veyru/world.py                                                                 |      170 |       34 |       52 |       16 |     77% |130-132, 150, 165, 173, 192, 208-214, 224, 237, 283, 290, 300, 303, 326, 332-337, 368, 370, 388, 402, 409, 419, 423-424, 439, 443 |
| src/glossogen/scenarios/veyru/world\_state.py                                                          |       20 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/warehouse\_robot\_recovery/\_\_init\_\_.py                                     |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/warehouse\_robot\_recovery/evaluation/\_\_init\_\_.py                          |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/warehouse\_robot\_recovery/events.py                                           |        9 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/warehouse\_robot\_recovery/ids.py                                              |       24 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/warehouse\_robot\_recovery/knobs.py                                            |       10 |        2 |        4 |        2 |     71% |    49, 51 |
| src/glossogen/scenarios/warehouse\_robot\_recovery/recovery\_judge.py                                  |       18 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/warehouse\_robot\_recovery/scenario.py                                         |      167 |       18 |       58 |       16 |     84% |190, 206, 220, 230, 244, 255, 263, 267, 277, 281-284, 288, 375, 380, 382, 386, 448 |
| src/glossogen/scenarios/warehouse\_robot\_recovery/team\_declaration.py                                |       13 |        0 |        2 |        0 |    100% |           |
| src/glossogen/scenarios/warehouse\_robot\_recovery/warehouse\_cases.py                                 |       72 |        0 |       16 |        0 |    100% |           |
| src/glossogen/scenarios/warehouse\_robot\_recovery/world.py                                            |      109 |       18 |       34 |       13 |     78% |83, 103, 132-140, 150, 160, 177, 217, 219, 224, 230, 237-246, 248, 252-253, 266, 270 |
| src/glossogen/server/\_\_init\_\_.py                                                                   |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/server/app.py                                                                            |        6 |        6 |        0 |        0 |      0% |      8-15 |
| src/glossogen/server/app\_factory.py                                                                   |      101 |       38 |       18 |        1 |     57% |53-62, 74-77, 86-99, 112-134, 220 |
| src/glossogen/server/error\_logging\_handlers.py                                                       |       15 |        2 |        4 |        2 |     79% |    25, 27 |
| src/glossogen/server/feature\_flags.py                                                                 |       12 |        5 |        2 |        0 |     50% | 21-24, 36 |
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
| src/glossogen/server/mcp/asgi\_context.py                                                              |       41 |       27 |       18 |        0 |     24% |35-38, 41-72, 77-84 |
| src/glossogen/server/mcp/browser.py                                                                    |      195 |      143 |       52 |        0 |     21% |86-87, 100-109, 114-116, 121-128, 157-160, 172-175, 185-188, 202, 236-260, 339-353, 374-397, 407-417, 450-463, 482-597, 623-624, 636-638, 652-665, 675-683, 696-702, 714-715, 732-739, 842-867, 888-903 |
| src/glossogen/server/mcp/in\_memory\_oauth\_storage.py                                                 |       95 |       66 |       26 |        0 |     24% |35-36, 43-47, 55, 59, 67, 73-79, 83, 91, 95-102, 106, 110-111, 119, 123-130, 134, 138-139, 147, 154-160, 164, 177-205 |
| src/glossogen/server/mcp/models.py                                                                     |       30 |        0 |        0 |        0 |    100% |           |
| src/glossogen/server/mcp/oauth\_mounting.py                                                            |       48 |       25 |        6 |        0 |     43% |32, 35, 47, 57-59, 70-107, 125-142 |
| src/glossogen/server/mcp/oauth\_provider.py                                                            |       96 |       69 |       12 |        0 |     25% |65-67, 75, 90-91, 108-132, 146-172, 185-196, 213-217, 229-265, 281-285, 294-328, 342-343, 352-353, 361-368, 391-393 |
| src/glossogen/server/mcp/oauth\_records.py                                                             |        7 |        0 |        0 |        0 |    100% |           |
| src/glossogen/server/mcp/oauth\_storage.py                                                             |      126 |       85 |       24 |        0 |     27% |44, 48, 56-57, 79-87, 95-96, 122-149, 153-154, 162-163, 180-202, 206-207, 211-212, 220-221, 241-262, 266-267, 271-272, 280-281, 303-319, 332-333, 347-361, 370, 375-377 |
| src/glossogen/server/mcp/oauth\_storage\_port.py                                                       |        6 |        0 |        0 |        0 |    100% |           |
| src/glossogen/server/mcp/run\_context.py                                                               |       16 |        5 |        2 |        0 |     61% | 44-49, 54 |
| src/glossogen/server/mcp/whoami\_router.py                                                             |       28 |       17 |       10 |        0 |     29% |     40-62 |
| src/glossogen/server/pdf/\_\_init\_\_.py                                                               |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/server/pdf/export\_data.py                                                               |       78 |       60 |       32 |        0 |     16% |47, 51, 56-63, 131-191, 199, 208-259, 267-293 |
| src/glossogen/server/pdf/html\_renderer.py                                                             |       35 |       22 |        6 |        0 |     32% |27-28, 33, 38, 43-47, 52-71 |
| src/glossogen/server/pdf/router.py                                                                     |       30 |       16 |        6 |        0 |     39% |26-31, 54-79 |
| src/glossogen/server/response\_models.py                                                               |        8 |        0 |        0 |        0 |    100% |           |
| src/glossogen/server/run\_launcher.py                                                                  |       35 |       14 |        2 |        0 |     57% |    61-114 |
| src/glossogen/server/runs/\_\_init\_\_.py                                                              |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/server/runs/analysis\_record\_cache.py                                                   |       40 |        0 |       10 |        1 |     98% | 100-\>102 |
| src/glossogen/server/runs/analysis\_router.py                                                          |       42 |        0 |        0 |        0 |    100% |           |
| src/glossogen/server/runs/archive\_streaming\_response.py                                              |       27 |        0 |        2 |        0 |    100% |           |
| src/glossogen/server/runs/branch\_sources.py                                                           |       48 |       31 |       12 |        0 |     28% |35-47, 56-70, 79-95, 104-106, 115-116 |
| src/glossogen/server/runs/bundle\_router.py                                                            |      166 |      126 |       42 |        0 |     19% |52-75, 86-99, 117-140, 167-185, 194-199, 204-209, 214-230, 240-249, 275-349, 375-423 |
| src/glossogen/server/runs/dashboard\_router.py                                                         |       53 |        1 |        6 |        1 |     97% |        96 |
| src/glossogen/server/runs/derived\_run\_references.py                                                  |       81 |       62 |       30 |        0 |     17% |49-80, 94-102, 113-121, 131-161, 187-190, 203-236 |
| src/glossogen/server/runs/detail\_reader.py                                                            |      248 |      223 |      106 |        0 |      7% |68-103, 108-126, 131-133, 146-173, 187-514, 553, 558-562, 567-577 |
| src/glossogen/server/runs/discovery.py                                                                 |      247 |       33 |      100 |       24 |     83% |94, 101, 109-\>91, 129, 133-\>91, 142-144, 151, 162-\>161, 217, 236-\>232, 261, 268, 285-287, 298-299, 334-336, 360-361, 408, 439, 559, 566, 649-650, 655, 659, 661, 683-684, 689, 693 |
| src/glossogen/server/runs/export\_selection.py                                                         |       13 |        6 |        2 |        0 |     47% |     38-60 |
| src/glossogen/server/runs/label\_description\_router.py                                                |       30 |        0 |        2 |        0 |    100% |           |
| src/glossogen/server/runs/label\_mirror.py                                                             |       75 |       42 |       24 |        1 |     40% |96-112, 127-143, 152, 171-199 |
| src/glossogen/server/runs/listing.py                                                                   |      163 |       41 |       38 |        3 |     75% |88-89, 94-104, 137-145, 365, 384, 459-465, 473-474, 492-493, 552, 557-560, 572-599 |
| src/glossogen/server/runs/lookup.py                                                                    |       46 |       31 |       14 |        1 |     27% |28, 53-83, 110-116, 144-149 |
| src/glossogen/server/runs/manifest\_sources.py                                                         |       55 |       22 |       20 |        4 |     55% |63-64, 82-86, 109, 125-126, 147-193 |
| src/glossogen/server/runs/models.py                                                                    |       70 |        1 |        2 |        1 |     97% |        26 |
| src/glossogen/server/runs/multi\_export\_router.py                                                     |       80 |        0 |       14 |        0 |    100% |           |
| src/glossogen/server/runs/primary\_channel\_resolution.py                                              |       22 |        3 |        4 |        0 |     88% |     49-55 |
| src/glossogen/server/runs/router.py                                                                    |      246 |      165 |       38 |        0 |     29% |152-153, 163-182, 207-228, 247-259, 273-277, 287-297, 307-313, 325-348, 354-373, 390-399, 420-511, 523-541, 572-588, 612-631, 642-649, 655-662, 684-708, 717-718 |
| src/glossogen/server/runs/run\_detail\_types.py                                                        |        5 |        0 |        0 |        0 |    100% |           |
| src/glossogen/server/runs/scenario\_extension.py                                                       |       20 |        1 |        4 |        1 |     92% |        89 |
| src/glossogen/server/runs/streaming\_event.py                                                          |        6 |        0 |        0 |        0 |    100% |           |
| src/glossogen/server/scenarios/\_\_init\_\_.py                                                         |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/server/scenarios/filterable\_knobs.py                                                    |       72 |        2 |       30 |        3 |     95% |59, 139-\>142, 145 |
| src/glossogen/server/scenarios/models.py                                                               |        8 |        0 |        0 |        0 |    100% |           |
| src/glossogen/server/scenarios/router.py                                                               |       37 |       18 |        6 |        0 |     49% |31-44, 73-91 |
| src/glossogen/server/server\_runtime\_config.py                                                        |       12 |        5 |        2 |        0 |     50% | 26-29, 34 |
| src/glossogen/simulation\_server.py                                                                    |       65 |       44 |        6 |        0 |     30% |35-68, 75-85, 90-93, 98-102, 116-142, 150-154 |
| src/glossogen/stream\_manifest.py                                                                      |       36 |       19 |        6 |        2 |     45% |32-35, 48-55, 62-63, 68-74 |
| src/glossogen/telemetry\_bootstrap.py                                                                  |       48 |       33 |        6 |        0 |     28% |44-84, 94-98, 106-109 |
| src/glossogen/telemetry\_round\_processor.py                                                           |       29 |       13 |        6 |        0 |     46% |34, 38-40, 50, 54-60, 70 |
| src/glossogen/telemetry\_settings.py                                                                   |        9 |        2 |        0 |        0 |     78% |    23, 28 |
| src/glossogen/template\_renderer.py                                                                    |        8 |        0 |        0 |        0 |    100% |           |
| src/glossogen/testing/\_\_init\_\_.py                                                                  |        8 |        0 |        0 |        0 |    100% |           |
| src/glossogen/testing/metric\_harness.py                                                               |       55 |        1 |        6 |        1 |     97% |       105 |
| src/glossogen/testing/scenario\_registration.py                                                        |        9 |        0 |        4 |        0 |    100% |           |
| src/glossogen/testing/scenario\_runtime.py                                                             |       92 |       14 |       38 |       14 |     78% |136, 142, 181, 183, 188, 194, 211, 219, 224, 233, 236, 244, 246, 256 |
| src/glossogen/testing/scripted\_agent.py                                                               |       68 |        2 |       20 |        2 |     95% |  140, 144 |
| src/glossogen/testing/simulation\_harness.py                                                           |      133 |       11 |       26 |        3 |     89% |96-101, 122, 139, 332, 355-356 |
| src/glossogen/testing/smoke\_scenario.py                                                               |       91 |        2 |       10 |        2 |     96% |  201, 233 |
| src/glossogen/testing/stub\_llm\_provider.py                                                           |       26 |        1 |        4 |        1 |     93% |        69 |
| src/glossogen/thread\_export/\_\_init\_\_.py                                                           |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/thread\_export/export\_agent\_thread.py                                                  |       56 |       37 |       18 |        0 |     26% |42-44, 54-61, 66-71, 90-155, 172-180 |
| src/glossogen/thread\_export/provider\_thread\_serializer.py                                           |       92 |       79 |       62 |        0 |      8% |49-51, 56, 61, 75-80, 90-139, 152-176, 189-206, 216-239 |
| src/glossogen/thread\_export/thread\_export\_models.py                                                 |       38 |        6 |        4 |        0 |     76% |   117-122 |
| src/glossogen/token\_pricing.py                                                                        |       48 |        3 |       16 |        3 |     91% |91, 94, 97 |
| **TOTAL**                                                                                              | **22882** | **5677** | **6642** |  **995** | **71%** |           |


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
# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/agencyenterprise/GlossoGen/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                                                                                                   |    Stmts |     Miss |   Branch |   BrPart |   Cover |   Missing |
|------------------------------------------------------------------------------------------------------- | -------: | -------: | -------: | -------: | ------: | --------: |
| src/glossogen/\_\_init\_\_.py                                                                          |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/\_\_main\_\_.py                                                                          |        2 |        2 |        0 |        0 |      0% |       3-5 |
| src/glossogen/autonomous\_supervisor.py                                                                |      245 |       89 |       60 |       11 |     59% |53, 89, 134, 180-185, 196-200, 205, 211-223, 230, 240-268, 300, 324-375, 403-\>416, 445-455, 463-466, 523-530, 552-560, 569-572, 580-586, 610-611 |
| src/glossogen/channel\_router.py                                                                       |       89 |        0 |       32 |        0 |    100% |           |
| src/glossogen/cli.py                                                                                   |      725 |      336 |      166 |       19 |     51% |1011-1013, 1016-1018, 1021-1023, 1026-1028, 1031-1033, 1036-1038, 1041-1043, 1051-1053, 1066-1068, 1077, 1087-1088, 1100-1108, 1129-1130, 1134-1142, 1158-1179, 1188, 1205-1217, 1229-1238, 1246-1248, 1281-1290, 1295-1298, 1326-1329, 1352-1524, 1537-1576, 1689, 1708, 1756-1758, 1781, 1820-1821, 1839-1840, 1858-1880, 1899-1900, 1940, 1963-1983, 1988-2004, 2009, 2021-2023, 2032-2039, 2050-2103, 2114-2150, 2165-2181, 2195-2200, 2213-2223, 2237-2313, 2331-2360, 2370-2378, 2387-2405, 2410-2425 |
| src/glossogen/config\_overrides.py                                                                     |       83 |        1 |       38 |        1 |     98% |       145 |
| src/glossogen/cross\_run\_replace\_agent.py                                                            |      131 |      105 |       48 |        0 |     15% |104-117, 132-136, 141, 159-404 |
| src/glossogen/cross\_run\_replace\_manifest.py                                                         |       10 |        1 |        2 |        1 |     83% |        69 |
| src/glossogen/dashboards/dashboard\_models.py                                                          |       37 |        0 |       10 |        0 |    100% |           |
| src/glossogen/dashboards/dashboard\_store.py                                                           |        5 |        0 |        0 |        0 |    100% |           |
| src/glossogen/dashboards/dashboard\_store\_resolution.py                                               |       11 |        1 |        2 |        1 |     85% |        22 |
| src/glossogen/dashboards/filesystem\_dashboard\_store.py                                               |       79 |        0 |       16 |        0 |    100% |           |
| src/glossogen/dashboards/postgres\_dashboard\_store.py                                                 |       62 |       40 |        4 |        0 |     33% |36, 45-46, 63, 67-80, 95-99, 108-113, 122-149, 168-193, 197-203 |
| src/glossogen/db/\_\_init\_\_.py                                                                       |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/db/local\_tenant.py                                                                      |        5 |        0 |        0 |        0 |    100% |           |
| src/glossogen/db/pool.py                                                                               |       25 |       12 |        6 |        1 |     45% |31, 40-51, 56-59 |
| src/glossogen/db/queries.py                                                                            |       89 |       65 |       14 |        0 |     23% |29-37, 45-53, 68-95, 107-108, 121-132, 149-171, 187-199, 213-227, 249-275, 285-286, 299-300, 312-313, 326, 336, 367-368, 393-414, 426-433 |
| src/glossogen/db/rows.py                                                                               |        6 |        0 |        0 |        0 |    100% |           |
| src/glossogen/db/run\_registry.py                                                                      |       22 |       11 |        6 |        1 |     43% |37-55, 82-83 |
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
| src/glossogen/evaluation/metrics/english\_ngram/backoff\_ngram\_metric.py                              |       64 |        6 |       14 |        4 |     87% |82-83, 94-99, 158, 183 |
| src/glossogen/evaluation/metrics/english\_ngram/backoff\_ngram\_model.py                               |      110 |       41 |       44 |        9 |     57% |102, 117, 121, 128, 144, 146, 150, 174-182, 190, 194, 205-221, 242-257, 267-271 |
| src/glossogen/evaluation/metrics/english\_ngram/english\_ngram\_metric.py                              |       62 |        6 |       14 |        4 |     87% |75-76, 87-92, 147, 172 |
| src/glossogen/evaluation/metrics/english\_ngram/english\_ngram\_model.py                               |       73 |       24 |       18 |        1 |     64% |79, 113-121, 131-138, 148-158 |
| src/glossogen/evaluation/metrics/gzip\_compression\_ratio\_metric.py                                   |       51 |        5 |        8 |        3 |     86% |79-80, 91-96, 147 |
| src/glossogen/evaluation/metrics/language\_repetition\_metric.py                                       |      120 |        8 |       36 |        6 |     91% |131-132, 149-150, 210, 236, 239, 344 |
| src/glossogen/evaluation/metrics/language\_strangeness\_metric.py                                      |       38 |        3 |        6 |        2 |     89% | 71-72, 96 |
| src/glossogen/evaluation/metrics/mcm\_metric.py                                                        |       66 |        8 |       20 |        6 |     84% |69-70, 79-84, 139, 142, 165, 172 |
| src/glossogen/evaluation/metrics/mcr\_metric.py                                                        |       59 |        8 |       18 |        5 |     83% |58-59, 68-73, 128, 144, 152-153 |
| src/glossogen/evaluation/metrics/message\_entropy\_metric.py                                           |       51 |        5 |        8 |        3 |     86% |72-73, 84-89, 139 |
| src/glossogen/evaluation/metrics/neologism\_metric.py                                                  |       39 |        3 |        6 |        2 |     89% |67-68, 100 |
| src/glossogen/evaluation/metrics/perplexity\_metric.py                                                 |       70 |        6 |       14 |        3 |     89% |80-81, 97-98, 162, 187 |
| src/glossogen/evaluation/metrics/probe\_usage\_report.py                                               |       14 |        0 |        2 |        0 |    100% |           |
| src/glossogen/evaluation/metrics/protocol\_explanation\_metric.py                                      |      115 |       28 |       32 |        8 |     67% |129, 164-169, 186-194, 221, 249, 260-267, 279-280, 302-311, 317 |
| src/glossogen/evaluation/metrics/protocol\_learned\_after\_swap\_metric.py                             |       62 |        4 |       14 |        3 |     91% |100-101, 108-114, 152-\>154 |
| src/glossogen/evaluation/metrics/protocol\_probe/\_\_init\_\_.py                                       |        5 |        0 |        0 |        0 |    100% |           |
| src/glossogen/evaluation/metrics/protocol\_probe/probe\_agent.py                                       |       33 |        1 |        2 |        1 |     94% |        52 |
| src/glossogen/evaluation/metrics/protocol\_probe/protocol\_probe\_agent\_pair\_similarity\_metric.py   |       90 |        5 |       24 |        3 |     93% |110, 186-190, 206-211 |
| src/glossogen/evaluation/metrics/protocol\_probe/protocol\_probe\_cutoff\_trajectory\_metric.py        |      118 |       13 |       46 |       10 |     86% |119, 125, 141, 163, 202-206, 211-\>209, 214-218, 284-287, 290, 294-297 |
| src/glossogen/evaluation/metrics/protocol\_probe/protocol\_probe\_metric.py                            |       95 |       12 |       22 |        5 |     85% |94-99, 122-127, 130-135, 156-161, 220-227, 275 |
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
| src/glossogen/evaluation/reports/evaluation\_cost.py                                                   |       13 |        0 |        2 |        0 |    100% |           |
| src/glossogen/evaluation/reports/evaluation\_report.py                                                 |       47 |        6 |       10 |        2 |     86% |142, 144-151, 180-182 |
| src/glossogen/evaluation/round\_transcript\_builder.py                                                 |       42 |        5 |       18 |        4 |     82% |73-75, 87-\>89, 90, 93 |
| src/glossogen/evaluation/scenario\_evaluation\_runner.py                                               |       57 |        1 |       16 |        1 |     97% |        68 |
| src/glossogen/event\_bus.py                                                                            |       30 |       11 |        6 |        1 |     61% |38-41, 44-45, 62-64, 68-69 |
| src/glossogen/event\_logger.py                                                                         |       37 |        0 |        6 |        1 |     98% | 67-\>exit |
| src/glossogen/event\_parsing.py                                                                        |       15 |        0 |        6 |        0 |    100% |           |
| src/glossogen/frontend\_container.py                                                                   |       83 |       45 |       20 |        0 |     41% |84-117, 122-131, 138-142, 195-202, 211-228, 236-242, 247-253 |
| src/glossogen/knob\_filter.py                                                                          |      129 |        0 |       62 |        0 |    100% |           |
| src/glossogen/knobs\_resolution.py                                                                     |       26 |        0 |        8 |        0 |    100% |           |
| src/glossogen/llm/\_\_init\_\_.py                                                                      |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/llm/claude\_provider.py                                                                  |       85 |       64 |       26 |        0 |     19% |31-32, 41-45, 61-63, 78-84, 102-159, 172-192, 202-206 |
| src/glossogen/llm/deferred\_provider.py                                                                |       21 |        0 |        4 |        0 |    100% |           |
| src/glossogen/llm/huggingface\_provider.py                                                             |       64 |       44 |       20 |        0 |     24% |28-35, 51-53, 70-78, 98-142, 147-152 |
| src/glossogen/llm/max\_tokens.py                                                                       |       18 |       12 |        4 |        0 |     27% |     28-47 |
| src/glossogen/llm/openai\_provider.py                                                                  |       76 |       57 |       34 |        0 |     17% |22-26, 42-43, 58-65, 84-134, 144-149, 164-174 |
| src/glossogen/llm/provider.py                                                                          |       20 |        0 |        0 |        0 |    100% |           |
| src/glossogen/llm/provider\_factory.py                                                                 |       13 |        7 |        6 |        0 |     32% |     21-27 |
| src/glossogen/llm/token\_counter.py                                                                    |       53 |       27 |        6 |        0 |     47% |53-56, 60-71, 82-85, 89-100, 108, 117-125 |
| src/glossogen/logging\_format.py                                                                       |       21 |       10 |        2 |        0 |     48% |23-33, 45-46, 50-56 |
| src/glossogen/message\_history\_builder.py                                                             |      196 |       77 |      116 |       16 |     58% |86, 92-98, 125, 144-148, 168, 201-228, 237, 267-314, 359-374, 385, 466, 488, 500, 514, 534-\>532, 565, 568 |
| src/glossogen/message\_rewind.py                                                                       |       96 |       74 |       44 |        0 |     16% |154-158, 183-187, 211-307, 336-344, 361-365, 378-382, 397-400 |
| src/glossogen/models/\_\_init\_\_.py                                                                   |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/models/agent\_config.py                                                                  |        8 |        0 |        0 |        0 |    100% |           |
| src/glossogen/models/channel.py                                                                        |        5 |        0 |        0 |        0 |    100% |           |
| src/glossogen/models/compaction\_config.py                                                             |        5 |        0 |        0 |        0 |    100% |           |
| src/glossogen/models/event.py                                                                          |       75 |        0 |        0 |        0 |    100% |           |
| src/glossogen/models/event\_base.py                                                                    |        7 |        0 |        0 |        0 |    100% |           |
| src/glossogen/models/mcp\_responses.py                                                                 |        4 |        0 |        0 |        0 |    100% |           |
| src/glossogen/models/message.py                                                                        |       13 |        2 |        4 |        2 |     76% |    30, 34 |
| src/glossogen/models/model\_consumer.py                                                                |        2 |        0 |        0 |        0 |    100% |           |
| src/glossogen/models/tool\_definition.py                                                               |        3 |        0 |        0 |        0 |    100% |           |
| src/glossogen/oauth\_client.py                                                                         |      177 |      133 |       26 |        0 |     22% |54, 68-72, 77-83, 98-111, 116-118, 125-128, 132-153, 158-169, 183-198, 210-223, 233-239, 244-247, 252-257, 267-342, 347, 360-398, 406-410, 415-416 |
| src/glossogen/plugin\_entry\_points.py                                                                 |       23 |        1 |        6 |        1 |     93% |        76 |
| src/glossogen/port\_allocator.py                                                                       |        6 |        4 |        0 |        0 |     33% |     13-16 |
| src/glossogen/prod\_metadata\_sync.py                                                                  |      169 |      134 |       62 |        0 |     15% |87-102, 118-141, 146-149, 160-184, 196, 218-227, 241-280, 295-312, 329-349, 358-436 |
| src/glossogen/prod\_push.py                                                                            |      146 |      117 |       52 |        0 |     15% |69-84, 94-126, 140-159, 164-165, 181-189, 199-230, 244-262, 271-324 |
| src/glossogen/provider\_credentials.py                                                                 |       87 |        1 |       32 |        1 |     98% |       265 |
| src/glossogen/replace\_agent.py                                                                        |      157 |      127 |       72 |        0 |     13% |91, 113-118, 135-138, 152-158, 179-208, 213, 236-278, 296-301, 312-519 |
| src/glossogen/replace\_manifest.py                                                                     |       10 |        1 |        2 |        1 |     83% |        57 |
| src/glossogen/resume\_context\_writer.py                                                               |       34 |        8 |       14 |        3 |     73% |41, 43, 58, 74-82 |
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
| src/glossogen/run\_archive.py                                                                          |       92 |       48 |       32 |        3 |     44% |56, 64, 114-124, 141-156, 173-174, 189-201, 212-219 |
| src/glossogen/run\_config\_validation.py                                                               |       32 |       10 |       12 |        3 |     57% |28-\>50, 30, 60-68 |
| src/glossogen/run\_export/\_\_init\_\_.py                                                              |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/run\_export/agent\_identity\_columns.py                                                  |       22 |        0 |        8 |        0 |    100% |           |
| src/glossogen/run\_export/agent\_level\_frame.py                                                       |       56 |        4 |       24 |        5 |     89% |55, 85, 93, 102-\>106, 117 |
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
| src/glossogen/run\_export/message\_event\_scan.py                                                      |       61 |        4 |       24 |        5 |     89% |87, 94-95, 100-\>102, 110, 120-\>84 |
| src/glossogen/run\_export/message\_level\_frame.py                                                     |       50 |        0 |       12 |        1 |     98% | 144-\>148 |
| src/glossogen/run\_export/message\_repetition\_sidecar.py                                              |       30 |        7 |       12 |        4 |     74% |32, 35, 40, 42, 44-48 |
| src/glossogen/run\_export/metric\_column\_projection.py                                                |       42 |        9 |       16 |        0 |     74% |69-71, 76-78, 101-103 |
| src/glossogen/run\_export/model\_weight\_class.py                                                      |       25 |        0 |       12 |        0 |    100% |           |
| src/glossogen/run\_export/primary\_channel\_resolution.py                                              |       44 |        5 |       12 |        1 |     89% |70-72, 117-123 |
| src/glossogen/run\_export/round\_context\_frame.py                                                     |       67 |        6 |       18 |        3 |     89% |65, 121, 126-131, 137 |
| src/glossogen/run\_export/round\_level\_frame.py                                                       |       39 |        3 |       16 |        3 |     89% |54, 82, 98 |
| src/glossogen/run\_export/run\_context\_columns.py                                                     |       24 |        0 |        6 |        0 |    100% |           |
| src/glossogen/run\_export/run\_level\_frame.py                                                         |       34 |        4 |        8 |        2 |     86% |46-47, 68-69 |
| src/glossogen/run\_export/run\_message\_records.py                                                     |       32 |        0 |        2 |        0 |    100% |           |
| src/glossogen/run\_export/run\_metadata\_columns.py                                                    |        8 |        0 |        0 |        0 |    100% |           |
| src/glossogen/run\_export/run\_selection\_resolution.py                                                |       48 |        3 |       28 |        1 |     92% |     60-62 |
| src/glossogen/run\_export/runs\_zip\_archive.py                                                        |       63 |        0 |       10 |        0 |    100% |           |
| src/glossogen/run\_jsonl\_rewriter.py                                                                  |       45 |       38 |       20 |        0 |     11% |33-67, 82-102 |
| src/glossogen/run\_lineage.py                                                                          |       16 |        9 |        4 |        0 |     35% |33-41, 46-47 |
| src/glossogen/runners/\_\_init\_\_.py                                                                  |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/runners/agent\_run\_result.py                                                            |        2 |        0 |        0 |        0 |    100% |           |
| src/glossogen/runners/agent\_runner\_base.py                                                           |        6 |        0 |        0 |        0 |    100% |           |
| src/glossogen/runners/communication\_protocol.py                                                       |       10 |        0 |        0 |        0 |    100% |           |
| src/glossogen/runners/history\_cleanup\_processor.py                                                   |      113 |       13 |       50 |       10 |     86% |61-62, 65, 68, 74, 94, 97, 107, 109, 162, 165, 170-171 |
| src/glossogen/runners/pydantic\_ai\_model\_factory.py                                                  |       28 |       13 |       10 |        3 |     47% |24-32, 44-49, 51, 73-83 |
| src/glossogen/runners/pydantic\_ai\_runner.py                                                          |      290 |       70 |      102 |       20 |     69% |81-82, 93, 101-102, 177-187, 231, 259, 276, 287-295, 382, 406-412, 437-455, 458-461, 517-519, 523-\>531, 571-597, 602-605, 621, 697-\>exit, 699, 716-724, 727-731, 749, 750-\>757, 753-\>757, 755-756, 791-\>804, 828 |
| src/glossogen/runtime/\_\_init\_\_.py                                                                  |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/runtime/activity\_notification.py                                                        |       17 |        0 |        0 |        0 |    100% |           |
| src/glossogen/runtime/agent\_session.py                                                                |       76 |        4 |        8 |        2 |     93% |55, 128, 168-169 |
| src/glossogen/runtime/agent\_swap.py                                                                   |       93 |       20 |       10 |        4 |     77% |78, 81, 95, 200-218, 247, 279-280 |
| src/glossogen/runtime/game\_clock.py                                                                   |      139 |       14 |       42 |        8 |     88% |60, 65, 132, 134, 171-\>177, 197-200, 242, 258, 272-276, 357-361 |
| src/glossogen/runtime/mcp\_server.py                                                                   |       45 |        9 |       10 |        1 |     82% |62-63, 103-109 |
| src/glossogen/runtime/mcp\_tools.py                                                                    |      167 |       23 |       36 |        9 |     83% |114, 120-126, 141, 168-173, 182-189, 303-309, 366, 415, 442-465, 515-\>511, 574 |
| src/glossogen/runtime/mcp\_transport.py                                                                |        7 |        0 |        0 |        0 |    100% |           |
| src/glossogen/runtime/scenario\_mcp\_tool.py                                                           |       19 |        5 |        6 |        2 |     64% |     45-56 |
| src/glossogen/runtime/scenario\_world.py                                                               |       97 |       19 |       14 |        2 |     76% |93, 119, 148-165, 180-184 |
| src/glossogen/runtime/scheduled\_events.py                                                             |       40 |        5 |        8 |        1 |     79% |93-94, 118-120 |
| src/glossogen/runtime/scheduler.py                                                                     |       32 |        4 |       12 |        2 |     82% |81, 94-100 |
| src/glossogen/runtime/simulation\_state.py                                                             |      138 |        8 |       28 |        5 |     92% |124, 156, 179, 186, 261, 283-289, 296 |
| src/glossogen/scaffold\_templates/ids.py.jinja                                                         |        6 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scaffold\_templates/knobs\_default.json.jinja                                            |        1 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenario\_api.py                                                                         |        1 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenario\_conformance.py                                                                 |      313 |       60 |      146 |       39 |     78% |79, 113-115, 184-186, 190, 193, 204, 211, 214, 217, 219, 233, 248, 250, 258, 275, 289, 297, 300, 316, 325, 340, 347, 369-375, 397-403, 416, 429, 444, 456, 464, 468, 474, 492, 508, 528, 531-535, 548, 594, 611, 620-622, 642, 660-661, 663, 666, 676, 679 |
| src/glossogen/scenario\_entry\_points.py                                                               |       34 |        0 |       10 |        0 |    100% |           |
| src/glossogen/scenario\_loader.py                                                                      |       89 |        2 |       28 |        0 |     98% |   275-276 |
| src/glossogen/scenario\_package\_checks.py                                                             |      129 |       14 |       54 |       11 |     86% |99, 156-158, 164, 202, 212, 268, 271, 274-\>281, 277, 280, 324-325, 338 |
| src/glossogen/scenario\_path\_loader.py                                                                |      109 |       11 |       32 |        9 |     86% |102, 135, 145-146, 166-167, 199, 218, 243, 260-\>exit, 288, 294 |
| src/glossogen/scenario\_protocol.py                                                                    |      159 |        8 |       24 |        4 |     93% |114, 241, 267, 419, 439, 489, 561, 606 |
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
| src/glossogen/scenarios/container\_yard\_stacking/mcp\_tools.py                                        |       34 |        8 |       12 |        5 |     67% |39, 45, 53-\>68, 92-99, 101 |
| src/glossogen/scenarios/container\_yard\_stacking/outcome\_reconstruction.py                           |       58 |       46 |       30 |        0 |     14% |40-62, 77-79, 90-120 |
| src/glossogen/scenarios/container\_yard\_stacking/run\_detail\_extension.py                            |       54 |       33 |       18 |        0 |     29% |73, 84-89, 93-95, 102-109, 127-139, 155-158 |
| src/glossogen/scenarios/container\_yard\_stacking/scenario.py                                          |      173 |       25 |       56 |       12 |     79% |107, 121, 211, 227, 238, 252, 262, 282, 301, 310, 344-357, 370, 393-395 |
| src/glossogen/scenarios/container\_yard\_stacking/team\_declaration.py                                 |       25 |        1 |        6 |        1 |     94% |       173 |
| src/glossogen/scenarios/container\_yard\_stacking/team\_routing.py                                     |       40 |        0 |       20 |        0 |    100% |           |
| src/glossogen/scenarios/container\_yard\_stacking/world.py                                             |      157 |       18 |       54 |       13 |     85% |103, 108, 125, 130, 138, 149, 158, 180, 190, 206, 213, 224, 243-\>248, 244-\>248, 273, 291, 297-\>exit, 304, 310, 338, 341 |
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
| src/glossogen/scenarios/drive\_module\_repair/mcp\_tools.py                                            |       31 |        5 |       14 |        6 |     76% |39, 41, 46, 48, 51, 60-\>73 |
| src/glossogen/scenarios/drive\_module\_repair/replacement\_judge.py                                    |       22 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/drive\_module\_repair/run\_detail\_extension.py                                |       42 |       21 |       14 |        0 |     38% |105-134, 146-164, 180-181 |
| src/glossogen/scenarios/drive\_module\_repair/scenario.py                                              |      127 |        7 |       24 |        6 |     91% |207, 219, 221, 229, 231, 233, 322 |
| src/glossogen/scenarios/drive\_module\_repair/team\_declaration.py                                     |       13 |        0 |        2 |        0 |    100% |           |
| src/glossogen/scenarios/drive\_module\_repair/world.py                                                 |      178 |       64 |       68 |       19 |     57% |62-66, 71-73, 105, 121, 123, 130, 145, 149-153, 156-157, 173-180, 203-234, 267, 275, 292, 302, 306, 323, 331, 337, 344, 350-357, 361-362, 371, 373 |
| src/glossogen/scenarios/drive\_module\_repair/world\_state.py                                          |        2 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/hospital\_bed\_assignment\_privacy/\_\_init\_\_.py                             |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/hospital\_bed\_assignment\_privacy/events.py                                   |       12 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/hospital\_bed\_assignment\_privacy/hospital\_cases.py                          |       70 |        1 |       18 |        3 |     95% |195-\>191, 245-\>244, 273 |
| src/glossogen/scenarios/hospital\_bed\_assignment\_privacy/ids.py                                      |       32 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/hospital\_bed\_assignment\_privacy/knobs.py                                    |       30 |        8 |       16 |        8 |     65% |49, 51, 55, 59, 64, 74, 80, 90 |
| src/glossogen/scenarios/hospital\_bed\_assignment\_privacy/scenario.py                                 |      221 |       52 |       94 |       27 |     69% |233, 250, 258, 270, 283, 290, 312, 316, 318, 323-326, 338, 372, 374, 380, 390, 395, 400, 414-\>426, 443, 458, 460, 466, 475, 480, 494, 496-\>507, 525, 565-605 |
| src/glossogen/scenarios/hospital\_bed\_assignment\_privacy/team\_declaration.py                        |       11 |        0 |        2 |        0 |    100% |           |
| src/glossogen/scenarios/hospital\_bed\_assignment\_privacy/world.py                                    |      130 |       19 |       44 |       11 |     80% |114, 129, 178, 183, 188, 195, 199-217, 231, 236, 239, 292, 309-\>311, 314, 316 |
| src/glossogen/scenarios/orbital\_anomaly/\_\_init\_\_.py                                               |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/orbital\_anomaly/actuation\_judge.py                                           |       17 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/orbital\_anomaly/events.py                                                     |        8 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/orbital\_anomaly/ids.py                                                        |       25 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/orbital\_anomaly/injection\_rendering.py                                       |       22 |        3 |        8 |        3 |     80% |37, 55, 73 |
| src/glossogen/scenarios/orbital\_anomaly/knobs.py                                                      |       15 |        4 |        8 |        4 |     65% |47, 49, 55, 57 |
| src/glossogen/scenarios/orbital\_anomaly/mcp\_tools.py                                                 |       33 |        6 |       16 |        7 |     73% |36, 38, 40, 42, 45, 54-\>65, 74 |
| src/glossogen/scenarios/orbital\_anomaly/orbital\_anomaly\_cases.py                                    |       44 |        1 |        6 |        1 |     96% |       419 |
| src/glossogen/scenarios/orbital\_anomaly/run\_detail\_extension.py                                     |       41 |       21 |       14 |        0 |     36% |82-105, 117-135, 151-152 |
| src/glossogen/scenarios/orbital\_anomaly/scenario.py                                                   |      113 |        5 |       26 |        5 |     93% |182, 194, 204, 208, 226 |
| src/glossogen/scenarios/orbital\_anomaly/team\_declaration.py                                          |       11 |        0 |        2 |        0 |    100% |           |
| src/glossogen/scenarios/orbital\_anomaly/world.py                                                      |      103 |       21 |       36 |       14 |     75% |82, 92, 94, 113, 122-132, 149, 151, 153, 159, 165, 171-178, 180, 184-185, 201, 236 |
| src/glossogen/scenarios/prisoners\_dilemma/\_\_init\_\_.py                                             |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/prisoners\_dilemma/events.py                                                   |        6 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/prisoners\_dilemma/ids.py                                                      |       13 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/prisoners\_dilemma/knobs.py                                                    |       16 |        2 |        4 |        2 |     80% |    43, 48 |
| src/glossogen/scenarios/prisoners\_dilemma/mcp\_tools.py                                               |       26 |        3 |        4 |        1 |     87% | 31, 36-37 |
| src/glossogen/scenarios/prisoners\_dilemma/scenario.py                                                 |       91 |        2 |       14 |        2 |     96% |  135, 229 |
| src/glossogen/scenarios/prisoners\_dilemma/world.py                                                    |       57 |        2 |       12 |        2 |     94% |   81, 141 |
| src/glossogen/scenarios/satellite\_contact\_window/\_\_init\_\_.py                                     |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/satellite\_contact\_window/cases.py                                            |       67 |        1 |       10 |        1 |     97% |       352 |
| src/glossogen/scenarios/satellite\_contact\_window/command\_judge.py                                   |       33 |        1 |        4 |        1 |     95% |        45 |
| src/glossogen/scenarios/satellite\_contact\_window/evaluation/\_\_init\_\_.py                          |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/satellite\_contact\_window/events.py                                           |       21 |        2 |        4 |        2 |     84% |    62, 66 |
| src/glossogen/scenarios/satellite\_contact\_window/ids.py                                              |       25 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/satellite\_contact\_window/knobs.py                                            |       20 |        4 |        8 |        4 |     71% |48, 56, 62, 64 |
| src/glossogen/scenarios/satellite\_contact\_window/scenario.py                                         |      185 |       21 |       66 |       19 |     83% |189, 196, 212, 228, 242, 252, 268, 279, 287, 291, 301, 305-308, 311, 315, 419, 424, 426, 429, 509 |
| src/glossogen/scenarios/satellite\_contact\_window/team\_declaration.py                                |       13 |        0 |        2 |        0 |    100% |           |
| src/glossogen/scenarios/satellite\_contact\_window/world.py                                            |      121 |       16 |       34 |       12 |     82% |91, 116, 153-161, 174, 184, 204, 246, 248, 253, 259, 266-275, 277, 298, 302 |
| src/glossogen/scenarios/spillway\_release/\_\_init\_\_.py                                              |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/spillway\_release/case\_event\_conversion.py                                   |        4 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/spillway\_release/events.py                                                    |       12 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/spillway\_release/ids.py                                                       |       25 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/spillway\_release/injection\_rendering.py                                      |       28 |        3 |       12 |        3 |     85% |64, 77, 95 |
| src/glossogen/scenarios/spillway\_release/knobs.py                                                     |       31 |        7 |       14 |        7 |     69% |60, 69, 71, 79, 85, 90, 92 |
| src/glossogen/scenarios/spillway\_release/mcp\_tools.py                                                |       74 |       20 |       38 |       18 |     64% |41, 44, 59, 61, 64, 66, 68, 71-73, 84-\>96, 106, 108, 111, 114-\>123, 127-137, 146, 150, 153, 156-\>163 |
| src/glossogen/scenarios/spillway\_release/scenario.py                                                  |      109 |        3 |       20 |        3 |     95% |183, 195, 226 |
| src/glossogen/scenarios/spillway\_release/spillway\_cases.py                                           |       85 |        6 |       26 |        4 |     91% |69-70, 77, 204-205, 258 |
| src/glossogen/scenarios/spillway\_release/team\_declaration.py                                         |       13 |        0 |        2 |        0 |    100% |           |
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
| src/glossogen/scenarios/spot\_the\_difference/mcp\_tools.py                                            |       60 |        8 |       22 |        8 |     80% |48, 50, 53, 56, 59, 63, 109, 161 |
| src/glossogen/scenarios/spot\_the\_difference/outcome\_reconstruction.py                               |       62 |       52 |       30 |        0 |     11% |43-99, 116-152 |
| src/glossogen/scenarios/spot\_the\_difference/run\_detail\_extension.py                                |       61 |       38 |       22 |        0 |     28% |92, 104-109, 113, 127-139, 153-171, 182-196, 212-214 |
| src/glossogen/scenarios/spot\_the\_difference/scenario.py                                              |      164 |       12 |       48 |       11 |     89% |233, 249, 251, 262, 271, 273, 288, 290, 409, 413, 415, 421 |
| src/glossogen/scenarios/spot\_the\_difference/scene\_generation.py                                     |      221 |        5 |       56 |        4 |     97% |195, 363, 399, 450-455 |
| src/glossogen/scenarios/spot\_the\_difference/scripts/\_\_init\_\_.py                                  |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/spot\_the\_difference/scripts/check\_scene\_generation.py                      |       70 |       70 |       24 |        0 |      0% |    14-142 |
| src/glossogen/scenarios/spot\_the\_difference/team\_declaration.py                                     |       27 |        0 |        8 |        0 |    100% |           |
| src/glossogen/scenarios/spot\_the\_difference/team\_routing.py                                         |       41 |        1 |       20 |        0 |     98% |        88 |
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
| src/glossogen/scenarios/veyru/mcp\_tools.py                                                            |       64 |       20 |       20 |        9 |     65% |43-56, 60, 63-73, 75-85, 89-99, 108-\>119, 139-149, 179, 200-202 |
| src/glossogen/scenarios/veyru/outcome\_reconstruction.py                                               |       70 |       46 |       36 |        2 |     28% |44, 51, 95-141, 161-166 |
| src/glossogen/scenarios/veyru/run\_detail\_extension.py                                                |       92 |       63 |       42 |        0 |     22% |134-140, 144-171, 183-201, 209-230, 242-259, 275 |
| src/glossogen/scenarios/veyru/scenario.py                                                              |      194 |       27 |       58 |       12 |     81% |201, 265, 292, 334, 339, 343, 351, 368, 373, 375, 378-383, 398-401, 412-413, 428-441, 461-462 |
| src/glossogen/scenarios/veyru/scripts/\_\_init\_\_.py                                                  |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/veyru/scripts/build\_probe\_questions.py                                       |       28 |       28 |        4 |        0 |      0% |    12-105 |
| src/glossogen/scenarios/veyru/scripts/inspect\_replaced\_agent\_input.py                               |       74 |       74 |       30 |        0 |      0% |    22-149 |
| src/glossogen/scenarios/veyru/scripts/repro\_opus47\_refusal.py                                        |      143 |      143 |       50 |        0 |      0% |    22-255 |
| src/glossogen/scenarios/veyru/scripts/run\_baseline\_no\_specialist.py                                 |       79 |       79 |       18 |        0 |      0% |     8-130 |
| src/glossogen/scenarios/veyru/scripts/run\_baseline\_no\_specialist\_opus47.py                         |      118 |      118 |       42 |        0 |      0% |    15-184 |
| src/glossogen/scenarios/veyru/scripts/run\_evals\_no\_specialist.py                                    |       62 |       62 |       16 |        0 |      0% |     9-104 |
| src/glossogen/scenarios/veyru/scripts/run\_smoke\_8.py                                                 |       78 |       78 |       16 |        0 |      0% |     9-128 |
| src/glossogen/scenarios/veyru/stabilization\_judge.py                                                  |       22 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/veyru/team\_declaration.py                                                     |       41 |        0 |       12 |        0 |    100% |           |
| src/glossogen/scenarios/veyru/team\_lifecycle.py                                                       |       55 |       43 |       24 |        1 |     16% |43-102, 107-119, 130-158, 176-181 |
| src/glossogen/scenarios/veyru/veyru\_cases.py                                                          |       71 |        7 |        8 |        1 |     90% |435, 520-551 |
| src/glossogen/scenarios/veyru/world.py                                                                 |      170 |       34 |       52 |       16 |     77% |130-132, 150, 165, 173, 192, 208-214, 224, 237, 283, 290, 300, 303, 326, 332-337, 368, 370, 388, 402, 409, 419, 423-424, 439, 443 |
| src/glossogen/scenarios/veyru/world\_state.py                                                          |       20 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/warehouse\_robot\_recovery/\_\_init\_\_.py                                     |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/warehouse\_robot\_recovery/evaluation/\_\_init\_\_.py                          |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/warehouse\_robot\_recovery/events.py                                           |        9 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/warehouse\_robot\_recovery/ids.py                                              |       24 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/warehouse\_robot\_recovery/knobs.py                                            |       10 |        2 |        4 |        2 |     71% |    49, 51 |
| src/glossogen/scenarios/warehouse\_robot\_recovery/recovery\_judge.py                                  |       18 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/warehouse\_robot\_recovery/scenario.py                                         |      168 |       18 |       58 |       16 |     84% |190, 206, 220, 230, 244, 255, 263, 267, 277, 281-284, 288, 372, 377, 379, 383, 445 |
| src/glossogen/scenarios/warehouse\_robot\_recovery/team\_declaration.py                                |       13 |        0 |        2 |        0 |    100% |           |
| src/glossogen/scenarios/warehouse\_robot\_recovery/warehouse\_cases.py                                 |       72 |        0 |       16 |        0 |    100% |           |
| src/glossogen/scenarios/warehouse\_robot\_recovery/world.py                                            |      109 |       16 |       34 |       12 |     80% |83, 103, 132-140, 150, 160, 177, 217, 219, 224, 230, 237-246, 248, 266, 270 |
| src/glossogen/server/\_\_init\_\_.py                                                                   |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/server/app.py                                                                            |        6 |        6 |        0 |        0 |      0% |      8-15 |
| src/glossogen/server/app\_factory.py                                                                   |       92 |       33 |       18 |        1 |     58% |51-60, 69-82, 95-116, 201 |
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
| src/glossogen/server/mcp/browser.py                                                                    |      188 |      140 |       52 |        0 |     20% |83-84, 97-106, 111-113, 118-125, 154-157, 169-172, 182-185, 199, 234-258, 337-351, 372-395, 405-415, 448-461, 480-595, 621-622, 634-636, 650-663, 673-681, 694-700, 712-713, 815-841, 858-868 |
| src/glossogen/server/mcp/in\_memory\_oauth\_storage.py                                                 |       97 |       68 |       28 |        0 |     23% |35-36, 43-47, 55-57, 61, 69, 75-81, 85, 93, 97-104, 108, 112-113, 121, 125-132, 136, 140-141, 149, 156-162, 166, 179-207 |
| src/glossogen/server/mcp/models.py                                                                     |       30 |        0 |        0 |        0 |    100% |           |
| src/glossogen/server/mcp/oauth\_mounting.py                                                            |       48 |       25 |        6 |        0 |     43% |32, 35, 47, 57-59, 70-107, 125-142 |
| src/glossogen/server/mcp/oauth\_provider.py                                                            |       92 |       66 |       12 |        0 |     25% |63-65, 73, 88-89, 106-130, 144-170, 183-194, 211-215, 227-263, 279-283, 292-326, 340-341, 350-351, 359-366 |
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
| src/glossogen/server/runs/bundle\_router.py                                                            |      165 |      126 |       42 |        0 |     19% |51-74, 85-98, 116-139, 163-179, 188-193, 198-203, 208-224, 234-243, 269-343, 369-414 |
| src/glossogen/server/runs/dashboard\_router.py                                                         |       53 |        1 |        6 |        1 |     97% |        96 |
| src/glossogen/server/runs/derived\_run\_references.py                                                  |       98 |       74 |       36 |        0 |     18% |72-103, 117-125, 136-144, 154-184, 217-266, 271-274, 287-320 |
| src/glossogen/server/runs/detail\_reader.py                                                            |      241 |      216 |      100 |        0 |      7% |67-102, 107-125, 130-132, 145-172, 186-501, 540, 545-549, 554-564 |
| src/glossogen/server/runs/discovery.py                                                                 |      217 |       41 |       78 |       21 |     77% |68-71, 111, 118, 126-\>108, 135, 137-141, 149-151, 158, 169-\>168, 194, 232-234, 242-243, 273, 277-279, 303-304, 347, 378, 498, 505, 585-586, 591, 595, 597, 618-619, 624, 628 |
| src/glossogen/server/runs/export\_selection.py                                                         |       13 |        6 |        2 |        0 |     47% |     38-60 |
| src/glossogen/server/runs/listing.py                                                                   |      150 |       38 |       34 |        3 |     76% |85-86, 91-101, 134-142, 350, 366, 430-436, 444-445, 463-464, 523, 528-531, 542-565 |
| src/glossogen/server/runs/lookup.py                                                                    |       46 |       31 |       14 |        1 |     27% |28, 53-83, 109-115, 142-147 |
| src/glossogen/server/runs/manifest\_sources.py                                                         |       37 |       17 |       12 |        4 |     49% |28-30, 47-52, 73-77, 91-93 |
| src/glossogen/server/runs/models.py                                                                    |       70 |        1 |        2 |        1 |     97% |        26 |
| src/glossogen/server/runs/multi\_export\_router.py                                                     |       80 |        0 |       14 |        0 |    100% |           |
| src/glossogen/server/runs/primary\_channel\_resolution.py                                              |       15 |        3 |        2 |        0 |     82% |     43-49 |
| src/glossogen/server/runs/router.py                                                                    |      228 |      153 |       36 |        0 |     28% |148-149, 159-171, 196-217, 231-235, 245-255, 265-271, 283-306, 312-331, 348-357, 378-469, 481-499, 530-546, 570-579, 590-597, 603-610, 632-656, 665-666 |
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
| src/glossogen/testing/scenario\_runtime.py                                                             |       70 |       11 |       24 |       11 |     77% |128, 134, 171, 173, 178, 184, 191, 194, 202, 204, 214 |
| src/glossogen/testing/scripted\_agent.py                                                               |       37 |        0 |        8 |        0 |    100% |           |
| src/glossogen/testing/simulation\_harness.py                                                           |       98 |       12 |       22 |        3 |     84% |53-55, 77-82, 103, 120, 183 |
| src/glossogen/testing/smoke\_scenario.py                                                               |       91 |        5 |       10 |        2 |     93% |106, 111-112, 199, 231 |
| src/glossogen/testing/stub\_llm\_provider.py                                                           |       26 |        1 |        4 |        1 |     93% |        69 |
| src/glossogen/thread\_export/\_\_init\_\_.py                                                           |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/thread\_export/export\_agent\_thread.py                                                  |       55 |       36 |       18 |        0 |     26% |39-41, 51-58, 63-68, 87-148, 165-173 |
| src/glossogen/thread\_export/provider\_thread\_serializer.py                                           |       92 |       79 |       62 |        0 |      8% |49-51, 56, 61, 75-80, 90-139, 152-176, 189-206, 216-239 |
| src/glossogen/thread\_export/thread\_export\_models.py                                                 |       38 |        6 |        4 |        0 |     76% |   117-122 |
| src/glossogen/token\_pricing.py                                                                        |       41 |        7 |       14 |        1 |     85% |128-130, 158-160, 176 |
| **TOTAL**                                                                                              | **21251** | **5901** | **6122** |  **905** | **68%** |           |


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
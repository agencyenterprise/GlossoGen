# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/agencyenterprise/GlossoGen/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                                                                                                   |    Stmts |     Miss |   Branch |   BrPart |   Cover |   Missing |
|------------------------------------------------------------------------------------------------------- | -------: | -------: | -------: | -------: | ------: | --------: |
| src/glossogen/\_\_init\_\_.py                                                                          |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/\_\_main\_\_.py                                                                          |        2 |        2 |        0 |        0 |      0% |       3-5 |
| src/glossogen/autonomous\_supervisor.py                                                                |      244 |       89 |       60 |       11 |     59% |53, 89, 134, 180-185, 196-200, 205, 211-223, 230, 240-268, 300, 324-375, 403-\>416, 445-455, 463-466, 518-525, 547-555, 564-567, 575-581, 605-606 |
| src/glossogen/channel\_router.py                                                                       |       89 |        0 |       32 |        0 |    100% |           |
| src/glossogen/cli.py                                                                                   |      494 |      494 |      112 |        0 |      0% |   15-1720 |
| src/glossogen/config\_overrides.py                                                                     |       83 |        1 |       38 |        1 |     98% |       145 |
| src/glossogen/cross\_run\_replace\_agent.py                                                            |      130 |      130 |       50 |        0 |      0% |    13-394 |
| src/glossogen/cross\_run\_replace\_manifest.py                                                         |       10 |        1 |        2 |        1 |     83% |        69 |
| src/glossogen/db/\_\_init\_\_.py                                                                       |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/db/local\_tenant.py                                                                      |        5 |        5 |        0 |        0 |      0% |      9-18 |
| src/glossogen/db/pool.py                                                                               |       25 |       12 |        6 |        1 |     45% |31, 40-51, 56-59 |
| src/glossogen/db/queries.py                                                                            |       89 |       65 |       14 |        0 |     23% |29-37, 45-53, 68-95, 107-108, 121-132, 149-171, 187-199, 213-227, 249-275, 285-286, 299-300, 312-313, 326, 336, 367-368, 393-414, 426-433 |
| src/glossogen/db/rows.py                                                                               |        6 |        0 |        0 |        0 |    100% |           |
| src/glossogen/db/run\_registry.py                                                                      |       22 |       11 |        6 |        1 |     43% |37-55, 82-83 |
| src/glossogen/elapsed\_time.py                                                                         |        9 |        1 |        4 |        2 |     77% |26-\>25, 28 |
| src/glossogen/engine/\_\_init\_\_.py                                                                   |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/engine/round\_outcome\_log.py                                                            |       22 |        1 |        4 |        0 |     96% |        55 |
| src/glossogen/engine/round\_world.py                                                                   |       38 |        1 |       10 |        1 |     96% |       140 |
| src/glossogen/engine/team\_declaration.py                                                              |       13 |        0 |        2 |        0 |    100% |           |
| src/glossogen/engine/team\_structure.py                                                                |       41 |        0 |       14 |        0 |    100% |           |
| src/glossogen/eval\_manifest.py                                                                        |       37 |       37 |        6 |        0 |      0% |      8-71 |
| src/glossogen/evaluation/\_\_init\_\_.py                                                               |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/evaluation/log\_reader.py                                                                |       49 |        0 |       22 |        1 |     99% |   48-\>50 |
| src/glossogen/evaluation/metric\_core/\_\_init\_\_.py                                                  |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/evaluation/metric\_core/character\_entropy.py                                            |        8 |        1 |        2 |        1 |     80% |        22 |
| src/glossogen/evaluation/metric\_core/generic\_metric\_names.py                                        |        1 |        0 |        0 |        0 |    100% |           |
| src/glossogen/evaluation/metric\_core/gzip\_compression.py                                             |       11 |        1 |        2 |        1 |     85% |        34 |
| src/glossogen/evaluation/metric\_core/measurement.py                                                   |        7 |        0 |        0 |        0 |    100% |           |
| src/glossogen/evaluation/metric\_core/metric\_execution\_error.py                                      |        6 |        0 |        0 |        0 |    100% |           |
| src/glossogen/evaluation/metric\_core/metric\_protocol.py                                              |       10 |        0 |        0 |        0 |    100% |           |
| src/glossogen/evaluation/metric\_core/metric\_registry.py                                              |       27 |        0 |        0 |        0 |    100% |           |
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
| src/glossogen/evaluation/metric\_core/surprisal\_stats.py                                              |       10 |        1 |        4 |        1 |     86% |        14 |
| src/glossogen/evaluation/metrics/\_\_init\_\_.py                                                       |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/evaluation/metrics/communication/\_\_init\_\_.py                                         |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/evaluation/metrics/communication/communication\_feature\_presence\_metric.py             |       68 |       15 |       14 |        6 |     72% |70-75, 78-81, 88, 93, 177, 183, 194-195, 206-220 |
| src/glossogen/evaluation/metrics/communication/communication\_open\_coding\_metric.py                  |       40 |        4 |        2 |        1 |     88% |59-64, 126-127 |
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
| src/glossogen/evaluation/metrics/language\_repetition\_metric.py                                       |      110 |        7 |       32 |        5 |     92% |125-126, 143-144, 200, 203, 308 |
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
| src/glossogen/evaluation/metrics/protocol\_probe/protocol\_probe\_agent\_pair\_similarity\_metric.py   |       82 |        5 |       22 |        3 |     92% |105, 181-185, 201-206 |
| src/glossogen/evaluation/metrics/protocol\_probe/protocol\_probe\_cutoff\_trajectory\_metric.py        |      104 |       13 |       38 |       10 |     84% |112, 118, 134, 156, 195-199, 204-\>202, 207-211, 251-254, 257, 261-264 |
| src/glossogen/evaluation/metrics/protocol\_probe/protocol\_probe\_metric.py                            |       95 |       12 |       22 |        5 |     85% |94-99, 122-127, 130-135, 156-161, 220-227, 275 |
| src/glossogen/evaluation/metrics/protocol\_probe/protocol\_probe\_replica\_self\_similarity\_metric.py |       66 |        5 |       14 |        4 |     89% |109, 173-177, 186-\>184, 189-193 |
| src/glossogen/evaluation/metrics/protocol\_probe/response\_models.py                                   |        6 |        0 |        0 |        0 |    100% |           |
| src/glossogen/evaluation/metrics/protocol\_probe/similarity\_core.py                                   |       60 |        7 |       24 |        5 |     86% |52, 58, 61-62, 97, 105, 130 |
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
| src/glossogen/evaluation/reports/evaluation\_report.py                                                 |       37 |        6 |        6 |        2 |     81% |111, 113-120, 149-151 |
| src/glossogen/evaluation/round\_transcript\_builder.py                                                 |       42 |        5 |       18 |        4 |     82% |73-75, 87-\>89, 90, 93 |
| src/glossogen/evaluation/scenario\_evaluation\_runner.py                                               |       52 |        0 |       14 |        0 |    100% |           |
| src/glossogen/event\_bus.py                                                                            |       30 |       11 |        6 |        1 |     61% |38-41, 44-45, 62-64, 68-69 |
| src/glossogen/event\_logger.py                                                                         |       37 |        0 |        6 |        1 |     98% | 67-\>exit |
| src/glossogen/event\_parsing.py                                                                        |       15 |        3 |        6 |        1 |     81% | 39, 49-50 |
| src/glossogen/llm/\_\_init\_\_.py                                                                      |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/llm/claude\_provider.py                                                                  |       85 |       64 |       26 |        0 |     19% |31-32, 41-45, 61-63, 78-84, 102-159, 172-192, 202-206 |
| src/glossogen/llm/deferred\_provider.py                                                                |       21 |        0 |        4 |        0 |    100% |           |
| src/glossogen/llm/huggingface\_provider.py                                                             |       64 |       44 |       20 |        0 |     24% |28-35, 51-53, 70-78, 98-142, 147-152 |
| src/glossogen/llm/max\_tokens.py                                                                       |       18 |       12 |        4 |        0 |     27% |     28-47 |
| src/glossogen/llm/openai\_provider.py                                                                  |       76 |       57 |       34 |        0 |     17% |22-26, 42-43, 58-65, 84-134, 144-149, 164-174 |
| src/glossogen/llm/provider.py                                                                          |       20 |        0 |        0 |        0 |    100% |           |
| src/glossogen/llm/provider\_factory.py                                                                 |       13 |        7 |        6 |        0 |     32% |     21-27 |
| src/glossogen/llm/token\_counter.py                                                                    |       53 |       27 |        6 |        0 |     47% |53-56, 60-71, 82-85, 89-100, 108, 117-125 |
| src/glossogen/logging\_format.py                                                                       |       21 |       21 |        2 |        0 |      0% |      8-56 |
| src/glossogen/message\_history\_builder.py                                                             |      196 |       77 |      116 |       16 |     58% |86, 92-98, 125, 144-148, 168, 201-228, 237, 267-314, 359-374, 385, 466, 488, 500, 514, 534-\>532, 565, 568 |
| src/glossogen/message\_rewind.py                                                                       |       96 |       74 |       44 |        0 |     16% |154-158, 183-187, 211-307, 336-344, 361-365, 378-382, 397-400 |
| src/glossogen/models/\_\_init\_\_.py                                                                   |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/models/agent\_config.py                                                                  |        8 |        0 |        0 |        0 |    100% |           |
| src/glossogen/models/channel.py                                                                        |        5 |        0 |        0 |        0 |    100% |           |
| src/glossogen/models/compaction\_config.py                                                             |        5 |        0 |        0 |        0 |    100% |           |
| src/glossogen/models/event.py                                                                          |       70 |        0 |        0 |        0 |    100% |           |
| src/glossogen/models/event\_base.py                                                                    |        7 |        0 |        0 |        0 |    100% |           |
| src/glossogen/models/mcp\_responses.py                                                                 |        4 |        0 |        0 |        0 |    100% |           |
| src/glossogen/models/message.py                                                                        |       13 |        2 |        4 |        2 |     76% |    30, 34 |
| src/glossogen/models/tool\_definition.py                                                               |        3 |        0 |        0 |        0 |    100% |           |
| src/glossogen/oauth\_client.py                                                                         |      177 |      177 |       26 |        0 |      0% |    11-432 |
| src/glossogen/port\_allocator.py                                                                       |        6 |        6 |        0 |        0 |      0% |      8-16 |
| src/glossogen/prod\_metadata\_sync.py                                                                  |      167 |      167 |       60 |        0 |      0% |    18-432 |
| src/glossogen/prod\_push.py                                                                            |      144 |      144 |       50 |        0 |      0% |    14-321 |
| src/glossogen/replace\_agent.py                                                                        |      156 |      156 |       74 |        0 |      0% |    14-509 |
| src/glossogen/replace\_manifest.py                                                                     |       10 |        1 |        2 |        1 |     83% |        57 |
| src/glossogen/resume\_context\_writer.py                                                               |       34 |        8 |       14 |        3 |     73% |41, 43, 58, 74-82 |
| src/glossogen/run\_archive.py                                                                          |       82 |       48 |       26 |        3 |     36% |56, 64, 114-124, 141-156, 173-174, 189-201, 212-219 |
| src/glossogen/run\_config\_validation.py                                                               |       32 |       32 |       12 |        0 |      0% |      3-71 |
| src/glossogen/run\_jsonl\_rewriter.py                                                                  |       45 |       45 |       20 |        0 |      0% |    11-102 |
| src/glossogen/run\_lineage.py                                                                          |       16 |       16 |        4 |        0 |      0% |     12-47 |
| src/glossogen/runners/\_\_init\_\_.py                                                                  |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/runners/agent\_run\_result.py                                                            |        2 |        0 |        0 |        0 |    100% |           |
| src/glossogen/runners/agent\_runner\_base.py                                                           |        6 |        0 |        0 |        0 |    100% |           |
| src/glossogen/runners/communication\_protocol.py                                                       |       10 |        0 |        0 |        0 |    100% |           |
| src/glossogen/runners/history\_cleanup\_processor.py                                                   |      113 |       13 |       50 |       10 |     86% |61-62, 65, 68, 74, 94, 97, 107, 109, 162, 165, 170-171 |
| src/glossogen/runners/pydantic\_ai\_model\_factory.py                                                  |       28 |       13 |       10 |        3 |     47% |24-32, 44-49, 51, 73-83 |
| src/glossogen/runners/pydantic\_ai\_runner.py                                                          |      290 |       71 |      102 |       22 |     69% |81-82, 93, 101-102, 177-187, 231, 259, 276, 287-295, 333-\>511, 382, 406-412, 437-455, 458-461, 512-519, 523-\>531, 571-597, 602-605, 621, 697-\>exit, 699, 716-724, 727-731, 749, 750-\>757, 753-\>757, 755-756, 791-\>804, 828 |
| src/glossogen/runtime/\_\_init\_\_.py                                                                  |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/runtime/activity\_notification.py                                                        |       17 |        0 |        0 |        0 |    100% |           |
| src/glossogen/runtime/agent\_session.py                                                                |       68 |        4 |        8 |        2 |     92% |53, 95, 135-136 |
| src/glossogen/runtime/agent\_swap.py                                                                   |       92 |       20 |       10 |        4 |     76% |78, 81, 95, 196-214, 243, 275-276 |
| src/glossogen/runtime/game\_clock.py                                                                   |      137 |       14 |       40 |        8 |     88% |60, 65, 122, 124, 161-\>167, 187-190, 232, 248, 262-266, 347-351 |
| src/glossogen/runtime/mcp\_server.py                                                                   |       42 |       10 |       10 |        2 |     77% |46, 48-49, 89-95 |
| src/glossogen/runtime/mcp\_tools.py                                                                    |      167 |       23 |       36 |        9 |     83% |114, 120-126, 141, 168-173, 182-189, 303-309, 366, 415, 442-465, 515-\>511, 574 |
| src/glossogen/runtime/mcp\_transport.py                                                                |        7 |        0 |        0 |        0 |    100% |           |
| src/glossogen/runtime/scenario\_mcp\_tool.py                                                           |       19 |        5 |        6 |        2 |     64% |     45-56 |
| src/glossogen/runtime/scenario\_world.py                                                               |       97 |       19 |       14 |        2 |     76% |93, 119, 148-165, 180-184 |
| src/glossogen/runtime/scheduled\_events.py                                                             |       40 |        5 |        8 |        1 |     79% |93-94, 118-120 |
| src/glossogen/runtime/scheduler.py                                                                     |       32 |        4 |       12 |        2 |     82% |81, 94-100 |
| src/glossogen/runtime/simulation\_state.py                                                             |      138 |        8 |       28 |        5 |     92% |124, 156, 179, 186, 261, 283-289, 296 |
| src/glossogen/scenario\_loader.py                                                                      |        9 |        0 |        2 |        0 |    100% |           |
| src/glossogen/scenario\_protocol.py                                                                    |      124 |        9 |       14 |        2 |     92% |109, 309, 329, 379, 415-416, 451, 496, 563 |
| src/glossogen/scenario\_registry.py                                                                    |       12 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenario\_submodule\_discovery.py                                                        |       21 |        2 |        8 |        1 |     90% |34-35, 48-\>50 |
| src/glossogen/scenarios/\_\_init\_\_.py                                                                |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/base\_knobs.py                                                                 |       18 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/channel\_noise.py                                                              |       20 |        3 |        6 |        1 |     85% | 61, 67-68 |
| src/glossogen/scenarios/container\_yard\_stacking/\_\_init\_\_.py                                      |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/container\_yard\_stacking/case\_event\_conversion.py                           |       17 |        0 |        4 |        0 |    100% |           |
| src/glossogen/scenarios/container\_yard\_stacking/case\_rendering.py                                   |        3 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/container\_yard\_stacking/container\_attributes.py                             |        8 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/container\_yard\_stacking/evaluation/\_\_init\_\_.py                           |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/container\_yard\_stacking/evaluation/build\_communication\_rounds.py           |       63 |       50 |       24 |        0 |     15% |37-54, 59, 64-67, 72-95, 100-104, 111-124 |
| src/glossogen/scenarios/container\_yard\_stacking/events.py                                            |       12 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/container\_yard\_stacking/ids.py                                               |       50 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/container\_yard\_stacking/injection\_rendering.py                              |       48 |       13 |       22 |        6 |     64% |39, 43, 75, 96, 107, 113-117, 124-126 |
| src/glossogen/scenarios/container\_yard\_stacking/judging.py                                           |       70 |       22 |       28 |        5 |     60% |42-44, 83, 114-118, 188, 192, 198-200, 205-212 |
| src/glossogen/scenarios/container\_yard\_stacking/knobs.py                                             |       53 |       19 |       28 |        8 |     52% |61, 63, 69, 71, 78, 88-95, 100, 102-114 |
| src/glossogen/scenarios/container\_yard\_stacking/mcp\_tools.py                                        |       34 |        8 |       12 |        5 |     67% |39, 45, 53-\>68, 92-99, 101 |
| src/glossogen/scenarios/container\_yard\_stacking/outcome\_reconstruction.py                           |       58 |       46 |       30 |        0 |     14% |40-62, 77-79, 90-120 |
| src/glossogen/scenarios/container\_yard\_stacking/run\_detail\_extension.py                            |       54 |       54 |       18 |        0 |      0% |    10-158 |
| src/glossogen/scenarios/container\_yard\_stacking/scenario.py                                          |      173 |       31 |       56 |       10 |     76% |107, 121, 211, 227, 238, 250-273, 282, 301, 310, 344-357, 370, 393-395, 427 |
| src/glossogen/scenarios/container\_yard\_stacking/team\_declaration.py                                 |       25 |        1 |        6 |        1 |     94% |       173 |
| src/glossogen/scenarios/container\_yard\_stacking/team\_routing.py                                     |       40 |        0 |       20 |        0 |    100% |           |
| src/glossogen/scenarios/container\_yard\_stacking/world.py                                             |      157 |       18 |       54 |       13 |     85% |103, 108, 125, 130, 138, 149, 158, 180, 190, 206, 213, 224, 243-\>248, 244-\>248, 273, 291, 297-\>exit, 304, 310, 338, 341 |
| src/glossogen/scenarios/container\_yard\_stacking/world\_state.py                                      |       15 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/container\_yard\_stacking/yard\_cases.py                                       |       45 |        1 |       10 |        1 |     96% |        68 |
| src/glossogen/scenarios/drive\_module\_repair/\_\_init\_\_.py                                          |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/drive\_module\_repair/case\_event\_conversion.py                               |        4 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/drive\_module\_repair/drive\_module\_cases.py                                  |       84 |        9 |       16 |        1 |     82% |121-124, 128-131, 428 |
| src/glossogen/scenarios/drive\_module\_repair/evaluation/\_\_init\_\_.py                               |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/drive\_module\_repair/evaluation/build\_communication\_rounds.py               |       52 |       41 |       18 |        0 |     16% |35-54, 59-63, 71-91, 96-100, 107-120 |
| src/glossogen/scenarios/drive\_module\_repair/events.py                                                |       12 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/drive\_module\_repair/ids.py                                                   |       24 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/drive\_module\_repair/injection\_rendering.py                                  |       18 |        3 |        6 |        3 |     75% |39, 49, 67 |
| src/glossogen/scenarios/drive\_module\_repair/knobs.py                                                 |       21 |        4 |        8 |        4 |     72% |71, 73, 78, 80 |
| src/glossogen/scenarios/drive\_module\_repair/mcp\_tools.py                                            |       31 |        5 |       14 |        6 |     76% |39, 41, 46, 48, 51, 60-\>73 |
| src/glossogen/scenarios/drive\_module\_repair/replacement\_judge.py                                    |       22 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/drive\_module\_repair/run\_detail\_extension.py                                |       42 |       42 |       14 |        0 |      0% |    14-181 |
| src/glossogen/scenarios/drive\_module\_repair/scenario.py                                              |      127 |       11 |       24 |        6 |     89% |85, 207, 219, 221, 229, 231, 233, 293, 297, 309, 322 |
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
| src/glossogen/scenarios/orbital\_anomaly/run\_detail\_extension.py                                     |       41 |       41 |       14 |        0 |      0% |    13-152 |
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
| src/glossogen/scenarios/spillway\_release/injection\_rendering.py                                      |       28 |        4 |       12 |        4 |     80% |34, 64, 77, 95 |
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
| src/glossogen/scenarios/spot\_the\_difference/evaluation/build\_communication\_rounds.py               |       56 |       43 |       24 |        0 |     16% |32-49, 54, 59-61, 66-80, 85-89, 96-109 |
| src/glossogen/scenarios/spot\_the\_difference/events.py                                                |        9 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/spot\_the\_difference/ids.py                                                   |       44 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/spot\_the\_difference/injection\_rendering.py                                  |       23 |        3 |        8 |        3 |     81% |38, 58, 78 |
| src/glossogen/scenarios/spot\_the\_difference/knobs.py                                                 |       61 |       15 |       30 |       15 |     67% |81, 83, 89, 93, 101, 103, 109, 113, 121, 124, 133, 141, 150, 154, 161 |
| src/glossogen/scenarios/spot\_the\_difference/mcp\_tools.py                                            |       60 |        8 |       22 |        8 |     80% |48, 50, 53, 56, 59, 63, 109, 161 |
| src/glossogen/scenarios/spot\_the\_difference/outcome\_reconstruction.py                               |       62 |       52 |       30 |        0 |     11% |43-99, 116-152 |
| src/glossogen/scenarios/spot\_the\_difference/run\_detail\_extension.py                                |       61 |       61 |       22 |        0 |      0% |    11-214 |
| src/glossogen/scenarios/spot\_the\_difference/scenario.py                                              |      164 |       17 |       48 |       11 |     87% |233, 249, 251, 262, 271, 273, 288, 290, 363, 367-368, 377-378, 409, 413, 415, 421 |
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
| src/glossogen/scenarios/veyru/evaluation/build\_communication\_rounds.py                               |       46 |       36 |       16 |        0 |     16% |35-54, 59-77, 87-91, 98-111 |
| src/glossogen/scenarios/veyru/evaluation/metrics/\_\_init\_\_.py                                       |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/veyru/events.py                                                                |       12 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/veyru/ids.py                                                                   |       44 |        0 |        0 |        0 |    100% |           |
| src/glossogen/scenarios/veyru/injection\_rendering.py                                                  |      107 |       31 |       62 |       14 |     65% |43, 53-59, 69, 86, 124, 135, 137, 141, 160-175, 180-190, 215, 236, 241, 257 |
| src/glossogen/scenarios/veyru/knobs.py                                                                 |       34 |        9 |       22 |        9 |     68% |74, 76, 85, 96, 102, 104, 109, 111, 117 |
| src/glossogen/scenarios/veyru/mcp\_tools.py                                                            |       64 |       20 |       20 |        9 |     65% |43-56, 60, 63-73, 75-85, 89-99, 108-\>119, 139-149, 179, 200-202 |
| src/glossogen/scenarios/veyru/outcome\_reconstruction.py                                               |       70 |       46 |       36 |        2 |     28% |44, 51, 95-141, 161-166 |
| src/glossogen/scenarios/veyru/run\_detail\_extension.py                                                |       92 |       92 |       42 |        0 |      0% |    14-275 |
| src/glossogen/scenarios/veyru/scenario.py                                                              |      194 |       40 |       58 |       12 |     75% |105, 201, 265, 292, 304-327, 334, 339, 343, 351, 368, 373, 375, 378-383, 398-401, 412-413, 428-441, 461-462, 517, 535-536, 548-549 |
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
| src/glossogen/server/app.py                                                                            |      129 |      129 |       30 |        0 |      0% |     3-250 |
| src/glossogen/server/error\_logging\_handlers.py                                                       |       15 |       15 |        4 |        0 |      0% |     11-39 |
| src/glossogen/server/feature\_flags.py                                                                 |       12 |       12 |        2 |        0 |      0% |      9-36 |
| src/glossogen/server/identity/\_\_init\_\_.py                                                          |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/server/identity/bootstrap.py                                                             |       12 |       12 |        0 |        0 |      0% |      8-37 |
| src/glossogen/server/identity/clerk\_verifier.py                                                       |       29 |       29 |        6 |        0 |      0% |     23-96 |
| src/glossogen/server/identity/identity\_model.py                                                       |        4 |        4 |        0 |        0 |      0% |      9-22 |
| src/glossogen/server/identity/middleware.py                                                            |      113 |      113 |       40 |        0 |      0% |    29-275 |
| src/glossogen/server/identity/settings.py                                                              |       11 |       11 |        0 |        0 |      0% |     13-37 |
| src/glossogen/server/identity/webhook\_router.py                                                       |       70 |       70 |       22 |        0 |      0% |     8-156 |
| src/glossogen/server/mcp/\_\_init\_\_.py                                                               |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/server/mcp/asgi\_context.py                                                              |       41 |       41 |       18 |        0 |      0% |     10-84 |
| src/glossogen/server/mcp/browser.py                                                                    |      202 |      202 |       62 |        0 |      0% |    14-888 |
| src/glossogen/server/mcp/consent\_router.py                                                            |       67 |       67 |       24 |        0 |      0% |    16-168 |
| src/glossogen/server/mcp/in\_memory\_oauth\_storage.py                                                 |       97 |       97 |       28 |        0 |      0% |    13-207 |
| src/glossogen/server/mcp/models.py                                                                     |       30 |       30 |        0 |        0 |      0% |     3-321 |
| src/glossogen/server/mcp/oauth\_provider.py                                                            |       92 |       92 |       12 |        0 |      0% |    18-368 |
| src/glossogen/server/mcp/oauth\_records.py                                                             |        7 |        7 |        0 |        0 |      0% |      9-36 |
| src/glossogen/server/mcp/oauth\_storage.py                                                             |      126 |      126 |       24 |        0 |      0% |    10-377 |
| src/glossogen/server/mcp/oauth\_storage\_port.py                                                       |        6 |        6 |        0 |        0 |      0% |      9-23 |
| src/glossogen/server/mcp/run\_context.py                                                               |       16 |       16 |        2 |        0 |      0% |     10-54 |
| src/glossogen/server/pdf/\_\_init\_\_.py                                                               |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/server/pdf/export\_data.py                                                               |       78 |       78 |       32 |        0 |      0% |     8-293 |
| src/glossogen/server/pdf/html\_renderer.py                                                             |       35 |       35 |        6 |        0 |      0% |      7-71 |
| src/glossogen/server/pdf/router.py                                                                     |       30 |       30 |        6 |        0 |      0% |      3-79 |
| src/glossogen/server/response\_models.py                                                               |        8 |        8 |        0 |        0 |      0% |      3-26 |
| src/glossogen/server/run\_launcher.py                                                                  |       40 |       40 |        8 |        0 |      0% |     6-110 |
| src/glossogen/server/runs/\_\_init\_\_.py                                                              |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/server/runs/branch\_sources.py                                                           |       48 |       48 |       12 |        0 |      0% |    11-118 |
| src/glossogen/server/runs/bundle\_router.py                                                            |      196 |      196 |       58 |        0 |      0% |    10-474 |
| src/glossogen/server/runs/derived\_run\_references.py                                                  |       98 |       98 |       36 |        0 |      0% |    11-319 |
| src/glossogen/server/runs/detail\_reader.py                                                            |      246 |      246 |      102 |        0 |      0% |     3-584 |
| src/glossogen/server/runs/discovery.py                                                                 |      204 |      204 |       74 |        0 |      0% |     7-601 |
| src/glossogen/server/runs/listing.py                                                                   |      119 |      119 |       24 |        0 |      0% |    14-399 |
| src/glossogen/server/runs/lookup.py                                                                    |       46 |       46 |       14 |        0 |      0% |    11-147 |
| src/glossogen/server/runs/manifest\_sources.py                                                         |       37 |       37 |       12 |        0 |      0% |     10-93 |
| src/glossogen/server/runs/models.py                                                                    |       70 |       70 |        2 |        0 |      0% |     3-736 |
| src/glossogen/server/runs/primary\_channel\_resolution.py                                              |       15 |        5 |        2 |        1 |     65% |35-39, 43-49 |
| src/glossogen/server/runs/router.py                                                                    |      221 |      221 |       36 |        0 |      0% |     3-637 |
| src/glossogen/server/runs/run\_detail\_types.py                                                        |        5 |        5 |        0 |        0 |      0% |     10-40 |
| src/glossogen/server/runs/scenario\_extension.py                                                       |       20 |       20 |        4 |        0 |      0% |     19-97 |
| src/glossogen/server/runs/streaming\_event.py                                                          |        6 |        0 |        0 |        0 |    100% |           |
| src/glossogen/server/scenarios/\_\_init\_\_.py                                                         |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/server/scenarios/models.py                                                               |        6 |        6 |        0 |        0 |      0% |      3-31 |
| src/glossogen/server/scenarios/router.py                                                               |       38 |       38 |        8 |        0 |      0% |      7-85 |
| src/glossogen/simulation\_server.py                                                                    |       65 |       65 |        6 |        0 |      0% |    13-154 |
| src/glossogen/stream\_manifest.py                                                                      |       36 |       36 |        6 |        0 |      0% |      9-74 |
| src/glossogen/telemetry\_bootstrap.py                                                                  |       48 |       48 |        6 |        0 |      0% |    13-109 |
| src/glossogen/telemetry\_round\_processor.py                                                           |       29 |       13 |        6 |        0 |     46% |34, 38-40, 50, 54-60, 70 |
| src/glossogen/telemetry\_settings.py                                                                   |        9 |        9 |        0 |        0 |      0% |      8-28 |
| src/glossogen/template\_renderer.py                                                                    |        8 |        0 |        0 |        0 |    100% |           |
| src/glossogen/thread\_export/\_\_init\_\_.py                                                           |        0 |        0 |        0 |        0 |    100% |           |
| src/glossogen/thread\_export/export\_agent\_thread.py                                                  |       55 |       55 |       18 |        0 |      0% |    10-173 |
| src/glossogen/thread\_export/provider\_thread\_serializer.py                                           |       92 |       92 |       62 |        0 |      0% |    14-239 |
| src/glossogen/thread\_export/thread\_export\_models.py                                                 |       38 |       38 |        4 |        0 |      0% |    15-168 |
| src/glossogen/token\_pricing.py                                                                        |       41 |       19 |       14 |        2 |     51% |126-131, 141-149, 158-160, 176 |
| **TOTAL**                                                                                              | **17111** | **7592** | **4876** |  **688** | **52%** |           |


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
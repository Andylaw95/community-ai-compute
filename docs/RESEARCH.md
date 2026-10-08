# Research starting points

This is an early experiment, not a claim to have invented distributed computing. We should compare reuse, integration, and a separate implementation before building more infrastructure.

Prior project work covers requirements, reward/accounting questions, a technical landscape review, and detailed reading of the three papers below. Their results are not measurements of this prototype. Papers remain at their publishers' links and are not redistributed here.

| Starting point | Question for this project |
| --- | --- |
| [BOINC: replication and validation](https://github.com/BOINC/boinc/wiki/JobReplication) | What can independent batches reuse from replication, application-specific validation, and canonical results? |
| [Petals: Distributed Inference and Fine-tuning of Large Language Models Over the Internet, v1](https://arxiv.org/abs/2312.08361v1) | When is partitioning one model across devices worth communication and recovery complexity? It differs from independent batch distribution. |
| [DiLoCo: Distributed Low-Communication Training of Language Models, v3](https://arxiv.org/abs/2311.08105v3) | Which assumptions allow less frequent synchronization? Less communication does not establish less total computation or malicious-worker resistance. |
| [Verde: Verification via Refereed Delegation for Machine Learning Programs, v1](https://arxiv.org/abs/2502.19405v1) | What reproducibility, honest-participant, and referee assumptions would stronger verification need, and at what cost? |

These are distinct approaches, not integrated components. Short independent chunks, central coordination, and trusted full recomputation form our small baseline. They do not establish distributed training or model-parallel inference as the right first product.

Please state workload, hardware, trust assumptions, permissions, reference implementation, and limitations when proposing an approach. Include verification, retries, loading, transfer, and foreground interference in comparisons. Cite primary sources and distinguish published results from your experiments.

“Use this existing project,” “narrow the problem,” and “this is not viable” are useful conclusions. Cost or energy claims need actual measurements and a comparable baseline.

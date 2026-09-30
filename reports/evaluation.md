# Stage 1 evaluation report

Run: 2026-09-30T09:30:58.834807+00:00
Environment: Python 3.12.8, Darwin x86_64.

## Method

Six demo documents; 12 manually labelled questions. TF-IDF vectors stored in Milvus Lite.
Cosine search with K=2 and minimum score > 0.05. One warm-up, five timed searches per question.
Recall@2 = relevant hits / relevant documents. Precision@2 = relevant hits / 2, including empty slots.
Metrics are averaged over questions. Retrieval latency excludes setup and LLM generation.

## Results

- Recall@2: 1.000
- Precision@2: 0.542
- Mean retrieval latency: 4.47 ms
- P95 retrieval latency: 5.22 ms
- Store setup/load: 1541.03 ms

This report covers retrieval accuracy and latency.
Run `python evaluate.py --with-llm` to include generated-answer metrics and full RAG latency.

| Question | Retrieved IDs | Recall@2 | Precision@2 |
|---|---|---:|---:|
| What are your opening hours? | hours | 1.00 | 0.50 |
| Are you open seven days a week? | hours | 1.00 | 0.50 |
| What are the parking prices? | hours, prices | 1.00 | 0.50 |
| Can I pay by card or cash? | prices | 1.00 | 0.50 |
| Where is the parking entrance? | hours, location | 1.00 | 0.50 |
| What is your address in Warsaw? | location | 1.00 | 0.50 |
| How do I book parking? | booking, hours | 1.00 | 0.50 |
| What details are needed for a reservation? | booking | 1.00 | 0.50 |
| Is live space availability connected? | availability | 1.00 | 0.50 |
| What is the maximum vehicle height? | general | 1.00 | 0.50 |
| How many accessible spaces are there? | general | 1.00 | 0.50 |
| What are your prices and opening hours? | hours, prices | 1.00 | 1.00 |

## Limitations

This is a small demonstration set, not an independent production benchmark. Most questions have one relevant document, so perfect retrieval gives Precision@2=0.5. TF-IDF measures word overlap and can miss paraphrases. The optional keyword check is only a rough answer metric; it cannot establish factual correctness or detect every hallucination. Review the saved answers manually. Privacy rules are heuristic, not a comprehensive PII detector.

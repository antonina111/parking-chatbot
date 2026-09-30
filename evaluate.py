"""Evaluate real retrieval; add --with-llm to also evaluate generated answers."""
import argparse
from datetime import datetime, timezone
import json
from math import ceil
import os
import platform
from statistics import mean
from time import perf_counter

from rag import ROOT, ParkingRAG, build_store, retrieve


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--with-llm", action="store_true")
    args = parser.parse_args()
    cases = json.loads((ROOT / "data/eval.json").read_text())
    start = perf_counter()
    store = build_store()
    setup_ms = (perf_counter() - start) * 1000
    rag = ParkingRAG(store) if args.with_llm else None
    results, latencies, answer_times, answer_scores = [], [], [], []
    # Warm up once, then time five retrieval runs per question.
    retrieve(store, cases[0]["question"])
    for case in cases:
        for _ in range(5):
            start = perf_counter()
            docs = retrieve(store, case["question"], k=2)
            latencies.append((perf_counter() - start) * 1000)
        ids = {doc.metadata["source"] for doc in docs}
        relevant = set(case["relevant"])
        hits = len(ids & relevant)
        row = {"question": case["question"], "retrieved": sorted(ids),
               "recall": hits / len(relevant), "precision": hits / 2}
        if rag:
            start = perf_counter()
            answer = rag.ask(case["question"])
            answer_times.append((perf_counter() - start) * 1000)
            passed = any(word in answer.lower() for word in case["keywords"])
            answer_scores.append(passed)
            row.update(answer=answer, keyword_pass=passed)
        results.append(row)
    lines = [
        "# Stage 1 evaluation report", "",
        f"Run: {datetime.now(timezone.utc).isoformat()}",
        f"Environment: Python {platform.python_version()}, {platform.system()} {platform.machine()}.",
        "", "## Method", "",
        "Six demo documents; 12 manually labelled questions. TF-IDF vectors stored in Milvus Lite.",
        "Cosine search with K=2 and minimum score > 0.05. One warm-up, five timed searches per question.",
        "Recall@2 = relevant hits / relevant documents. Precision@2 = relevant hits / 2, including empty slots.",
        "Metrics are averaged over questions. Retrieval latency excludes setup and LLM generation.",
        "", "## Results", "",
        f"- Recall@2: {mean(r['recall'] for r in results):.3f}",
        f"- Precision@2: {mean(r['precision'] for r in results):.3f}",
        f"- Mean retrieval latency: {mean(latencies):.2f} ms",
        f"- P95 retrieval latency: {sorted(latencies)[ceil(len(latencies) * .95) - 1]:.2f} ms",
        f"- Store setup/load: {setup_ms:.2f} ms", "",
    ]
    if rag:
        lines += [f"- Model: {os.getenv('OLLAMA_MODEL', 'llama3.2:1b')}",
                  f"- Answer keyword pass rate: {mean(answer_scores):.3f}",
                  f"- Mean full RAG latency: {mean(answer_times):.2f} ms", ""]
    else:
        lines += ["This report covers retrieval accuracy and latency.",
                  "Run `python evaluate.py --with-llm` to include generated-answer metrics and full RAG latency.", ""]
    lines += ["| Question | Retrieved IDs | Recall@2 | Precision@2 |",
              "|---|---|---:|---:|"]
    for row in results:
        lines.append(f"| {row['question']} | {', '.join(row['retrieved'])} | {row['recall']:.2f} | {row['precision']:.2f} |")
    lines += ["", "## Limitations", "",
              "This is a small demonstration set, not an independent production benchmark. "
              "Most questions have one relevant document, so perfect retrieval gives Precision@2=0.5. "
              "TF-IDF measures word overlap and can miss paraphrases. The optional keyword check "
              "is only a rough answer metric; it cannot establish factual correctness or detect every hallucination. "
              "Review the saved answers manually. Privacy rules are heuristic, not a comprehensive PII detector.", ""]
    report_dir = ROOT / "reports"
    report_dir.mkdir(exist_ok=True)
    (report_dir / "evaluation.md").write_text("\n".join(lines))
    (report_dir / "evaluation.json").write_text(json.dumps(results, indent=2))
    print("\n".join(lines))


if __name__ == "__main__":
    main()

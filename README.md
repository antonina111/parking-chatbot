# Parking chatbot — Stage 1

A minimal Python terminal app: public parking questions use **LangChain + LangGraph + Milvus Lite + Ollama**. A separate form collects a reservation draft. No website, SQL database, or administrator workflow yet.

## Run

Use Python 3.12. Tested on macOS; Milvus Lite also supports Linux.

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Install [Ollama](https://ollama.com/download), start it, and download the small local model:

```sh
ollama pull llama3.2:1b
python app.py
```

If needed, run `ollama serve` in a separate terminal first. No API key is required. You can select another installed model with `export OLLAMA_MODEL=your-model`.

Try:

- `What are your opening hours?`
- `What are the parking prices?`
- `Where is the entrance?`
- `reserve` — enter first name, surname, car number, start and end times when prompted.
- `cancel` — discard the current draft.
- `quit` — exit and clear the draft.

During reservation collection, replies are treated as form values. Dates use `YYYY-MM-DD HH:MM`; run the app in the parking location's local timezone. Completed drafts stay in memory until cancelled, replaced, or the app exits. They are **not confirmed, persisted, or sent to an administrator**.

## How it works

`Question → privacy filter → LangGraph retrieval node → Milvus public facts → answer node (LangChain prompt + Ollama) → output filter`

`reserve → local validated form → in-memory draft`

`data/parking.json` contains six short, fictional public facts. Each is already a small retrieval chunk. TF-IDF converts text into vectors locally; Milvus stores and searches them using cosine similarity. This is a basic lexical baseline, so paraphrases can be missed. There is no embedding API or large embedding model. Knowledge changes create a new collection automatically.

Prices and opening hours are sample facts, not live values. Availability is explicitly unknown. Edit the sample data to describe your parking location. The optional SQL split is omitted for Stage 1 simplicity.

## Privacy

- Only records explicitly marked `public` enter the vector database; retrieval also filters for public records.
- Reservation fields never enter the LLM, vector database, or LangGraph state.
- Rule-based filters redact email addresses, phone-like numbers, labelled names/plates, and common secret fields during ingestion, question handling, and output.
- Common requests for private data or secrets are refused.
- Only curate public parking facts into the source file. These rules are not a complete PII detector: unlabelled names and unusual formats may pass. There is no claim of complete prompt-injection protection.
- No conversation logging or tracing is configured. Do not enable external tracing for real personal data. Entered values are visible in your terminal.

## Evaluation

```sh
python -m unittest discover -s tests -v
python evaluate.py
python evaluate.py --with-llm
```

The first evaluation measures real Milvus retrieval Recall@2, Precision@2, mean latency, and P95 latency. The last command additionally measures full RAG latency and a simple generated-answer keyword pass rate; it needs Ollama. Both write `reports/evaluation.md` and `reports/evaluation.json` (the latest run replaces the previous report).

The included report covers retrieval accuracy and latency. Seven automated tests passed, covering Milvus retrieval, exclusion of private documents, redaction, reservation validation, and graph wiring with a test LLM.

## References

- [LangChain Milvus integration](https://docs.langchain.com/oss/python/integrations/vectorstores/milvus)
- [LangGraph StateGraph](https://reference.langchain.com/python/langgraph/graph/state/StateGraph)
- [LangChain Ollama integration](https://docs.langchain.com/oss/python/integrations/chat/ollama)

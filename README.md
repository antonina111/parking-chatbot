# Parking chatbot — Stages 1–3

A minimal Python terminal app: public parking questions use **LangChain + LangGraph + Milvus Lite + Ollama**. A second LangChain agent sends completed reservation requests to a REST API for human approval. Approved reservations are saved to text files through MCP.

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
```

If needed, run `ollama serve` in a separate terminal first. No API key is required. You can select another installed model with `export OLLAMA_MODEL=your-model`.

Start the administrator API in one terminal (with the virtual environment activated). Choose two different private tokens:

```sh
export ADMIN_TOKEN='replace-with-your-admin-token'
export BOT_TOKEN='replace-with-your-bot-token'
python admin_api.py
```

In a second terminal, activate the environment and start the chatbot with the same bot token:

```sh
source .venv/bin/activate
export BOT_TOKEN='replace-with-your-bot-token'
python app.py
```

Try:

- `What are your opening hours?`
- `What are the parking prices?`
- `Where is the entrance?`
- `reserve` — enter first name, surname, car number, start and end times when prompted.
- `cancel` — discard the current draft.
- `status` — get the administrator's decision for the current request.
- `retry` — retry a failed submission without creating a duplicate request.
- `quit` — exit and clear the draft.

During reservation collection, replies are treated as form values, except the commands above. Dates use `YYYY-MM-DD HH:MM`; run the app and API in the parking location's local timezone. Completed details are sent automatically to the administrator API, then cleared from the chatbot. A booking stays pending until a human decides. `cancel` only clears an unsent draft; contact the administrator to withdraw a submitted request.

## Administrator approval (Stage 2)

In a third terminal, set the same administrator token and list the inbox:

```sh
export ADMIN_TOKEN='replace-with-your-admin-token'
curl -H "Authorization: Bearer $ADMIN_TOKEN" http://127.0.0.1:8000/requests
```

Copy a request's `id` from that response and confirm it (replace `REQUEST_ID`):

```sh
curl -X POST http://127.0.0.1:8000/requests/REQUEST_ID/decision \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"status": "confirmed"}'
```

Use `{"status": "refused"}` to refuse instead. In the chatbot, type `status` to receive the decision.

The administrator must check availability before confirming. The bot token cannot read the administrator inbox or approve requests. The status endpoint returns only the request ID and status, not personal details.

This is a local, single-worker demo: the inbox and decisions are in memory and reset when the API restarts; saved reservation files remain on disk. The chatbot tracks one outstanding request per session. Keep both processes running during the demonstration. There is no automatic capacity allocation, email integration, or background notification; the user checks with `status`.

## Confirmed reservation storage (Stage 3)

Install the updated `requirements.txt` before running the app. The administrator API automatically starts `reservation_mcp.py` as a local subprocess when processing a confirmation. It uses the open-source MCP Python SDK and calls the `store_confirmed_reservation` tool over stdio. No third server command or port is needed.

Each approved request is stored in `data/confirmed_reservations/REQUEST_ID.txt`:

```text
Anna Example | WX1234 | 2099-01-01 10:00 to 2099-01-02 10:00 | 2026-09-30T12:00:00+00:00
```

The four fields are **Name | Car Number | Reservation Period | Approval Time**. Approval time is generated in UTC when the administrator first confirms. One file per request keeps retries idempotent without an extra database. Files survive process restarts and are excluded from Git and RAG ingestion.

Only the authenticated administrator confirmation route invokes storage. The MCP subprocess has a private pipe and no network listener; access relies on the local operating-system account, so run it under a trusted account. The tool accepts a UUID, not a file path. Field validation prevents extra lines or separators. Storage uses a process lock, an atomic file replacement, disk synchronization, and owner-only directory/file permissions (macOS/Linux).

The API marks a request confirmed only after storage acknowledges success. If saving fails, it returns HTTP 503 and keeps the request pending. Repeat the same confirmation to finish; the timestamp and filename remain unchanged, so a lost acknowledgement cannot duplicate the record. Once confirmation has started, the request cannot switch to refusal during a retry. Pending and refused requests are not written.

The assignment's direct-function alternative is also available: set `export RESERVATION_WRITER=function` in the administrator terminal before starting the API. This calls the same validated storage function without MCP. The default is `mcp`.

## How it works

`Question → privacy filter → LangGraph retrieval node → Milvus public facts → answer node (LangChain prompt + Ollama) → output filter`

`reserve → validated form → AdminAgent (LangChain) → REST inbox → human confirmation → MCP tool → text file → status → user`

`admin_agent.py` is the second agent: a deterministic LangChain workflow formats the approval request and sends it to `admin_api.py`. It also retrieves the human decision. No extra LLM is needed for this handoff, and the agent cannot approve requests itself.

`data/parking.json` contains six short, fictional public facts. Each is already a small retrieval chunk. TF-IDF converts text into vectors locally; Milvus stores and searches them using cosine similarity. This is a basic lexical baseline, so paraphrases can be missed. There is no embedding API or large embedding model. Knowledge changes create a new collection automatically.

Prices and opening hours are sample facts, not live values. Availability is checked by the administrator. Edit the sample data to describe your parking location. The optional SQL split is omitted for simplicity.

## Privacy

- Only records explicitly marked `public` enter the vector database; retrieval also filters for public records.
- Reservation fields never enter the LLM, vector database, or LangGraph state.
- Reservation details are shared only through the administrator workflow; approved details are also stored in private local files. Keep tokens private and keep this demo API bound to localhost.
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

The included Stage 1 report covers retrieval accuracy and latency. Automated tests cover Milvus retrieval, privacy filtering, reservation validation, graph wiring with a test LLM, and the Stage 2 handoff through the API dispatcher using an in-process HTTP transport. Stage 2 tests include both human decisions, token permissions, invalid input, and safe retry after a lost response.

Stage 3 tests cover actual text-file writes, approval-only access, file permissions, invalid fields, atomic-write failure, and retry after a lost storage acknowledgement. MCP protocol discovery is also checked when running with the SDK dependency installed.

## References

- [LangChain Milvus integration](https://docs.langchain.com/oss/python/integrations/vectorstores/milvus)
- [LangGraph StateGraph](https://reference.langchain.com/python/langgraph/graph/state/StateGraph)
- [LangChain Ollama integration](https://docs.langchain.com/oss/python/integrations/chat/ollama)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk/tree/v1.x)

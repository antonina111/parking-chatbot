"""Shared LangGraph orchestration for user turns and authenticated admin events."""
from datetime import datetime, timezone
from typing import TypedDict

from httpx import HTTPError
from langgraph.graph import END, START, StateGraph
from ollama import ResponseError


class WorkflowState(TypedDict, total=False):
    event: str
    route: str
    answer: str
    request_id: str
    decision: str
    code: int
    detail: str


class ParkingWorkflow:
    """One instance per CLI session or single-worker administrator service.

    Personal details stay in the form/inbox, outside graph state and checkpoints.
    The REST API must authenticate administrator events before calling decide().
    """

    def __init__(self, rag=None, reservation=None, requests=None, writer=None):
        self.rag = rag
        self.reservation = reservation
        self.requests = requests if requests is not None else {}
        self.writer = writer
        self._text = ""
        graph = StateGraph(WorkflowState)
        for name in ("user_interaction", "rag_answer", "administrator", "administrator_approval",
                     "data_recording", "finish_decision"):
            graph.add_node(name, getattr(self, "_" + name))
        graph.add_conditional_edges(START, lambda state: state["event"], {
            "user": "user_interaction", "decision": "administrator_approval",
        })
        graph.add_conditional_edges("user_interaction", lambda state: state["route"], {
            "rag": "rag_answer", "admin": "administrator", "done": END,
        })
        graph.add_edge("rag_answer", END)
        graph.add_edge("administrator", END)
        graph.add_conditional_edges("administrator_approval", lambda state: state["route"], {
            "record": "data_recording", "finish": "finish_decision", "error": END,
        })
        graph.add_conditional_edges("data_recording", lambda state: state["route"], {
            "finish": "finish_decision", "error": END,
        })
        graph.add_edge("finish_decision", END)
        self.graph = graph.compile()

    def respond(self, text):
        self._text = text
        try:
            return self.graph.invoke({"event": "user"})["answer"]
        finally:
            self._text = ""

    def decide(self, request_id, decision):
        result = self.graph.invoke({"event": "decision", "request_id": request_id, "decision": decision})
        if result["code"] != 200:
            return result["code"], {"detail": result["detail"]}
        return 200, {"id": request_id, "status": self.requests[request_id]["status"]}

    def _user_interaction(self, state):
        if self._text.strip().lower() in {"status", "retry"}:
            return {"route": "admin"}
        answer = self.reservation.handle(self._text, defer_submit=True)
        if answer is None:
            return {"route": "rag"}
        if answer == "":  # Completed form: the graph owns the next step.
            return {"route": "admin"}
        return {"answer": answer, "route": "done"}

    def _rag_answer(self, state):
        try:
            return {"answer": self.rag.ask(self._text)}
        except (ConnectionError, TimeoutError, HTTPError, ResponseError):
            return {"answer": "Could not generate an answer. Please check the model service and try again."}

    def _administrator(self, state):
        command = self._text.strip().lower()
        answer = (self.reservation.handle(command) if command in {"status", "retry"}
                  else self.reservation.submit())
        return {"answer": answer}

    def _administrator_approval(self, state):
        request = self.requests.get(state["request_id"])
        decision = state["decision"]
        if request is None:
            return {"route": "error", "code": 404, "detail": "Request not found."}
        if decision not in {"confirmed", "refused"}:
            return {"route": "error", "code": 422, "detail": "Invalid decision."}
        if request["status"] not in {"pending", decision}:
            return {"route": "error", "code": 409, "detail": "This request already has a final decision."}
        if "approval_time" in request and decision != "confirmed":
            return {"route": "error", "code": 409,
                    "detail": "Confirmation is in progress. Retry confirmation to finish saving."}
        if decision == "confirmed" and request["status"] != "confirmed":
            request.setdefault("approval_time", datetime.now(timezone.utc).isoformat())
            return {"route": "record"}
        return {"route": "finish"}

    def _data_recording(self, state):
        try:
            self.writer(self.requests[state["request_id"]])
        except Exception:
            return {"route": "error", "code": 503,
                    "detail": "Could not verify storage. Retry the same confirmation."}
        return {"route": "finish"}

    def _finish_decision(self, state):
        self.requests[state["request_id"]]["status"] = state["decision"]
        return {"code": 200}

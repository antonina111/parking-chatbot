"""Second agent: a deterministic LangChain workflow for the human handoff."""
import os

import httpx
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnableLambda


class AdminAgent:
    def __init__(self, client=None):
        self.client = client or httpx.Client(
            base_url=os.getenv("ADMIN_API_URL", "http://127.0.0.1:8000"),
            headers={"Authorization": f"Bearer {os.getenv('BOT_TOKEN', '')}"},
            timeout=10,
        )
        self.prompt = PromptTemplate.from_template(
            "Please confirm or refuse this parking reservation.\n"
            "Name: {first_name} {surname}\nCar: {car_number}\n"
            "From: {start}\nUntil: {end}\n"
            "Check space availability before confirming."
        )
        self.chain = RunnableLambda(self._prepare) | RunnableLambda(self._send)

    def _prepare(self, request):
        return {**request, "message": self.prompt.format(**request["details"])}

    def _send(self, request):
        response = self.client.put(f"/requests/{request['id']}", json={
            "details": request["details"], "message": request["message"],
        })
        response.raise_for_status()
        return response.json()

    def submit(self, request_id, details):
        return self.chain.invoke({"id": request_id, "details": details})

    def status(self, request_id):
        response = self.client.get(f"/requests/{request_id}/status")
        response.raise_for_status()
        return response.json()["status"]

    def close(self):
        self.client.close()

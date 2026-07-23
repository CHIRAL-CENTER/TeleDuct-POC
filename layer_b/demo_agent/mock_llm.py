# layer_b/demo_agent/mock_llm.py
class MockResponse:
    def __init__(self, content):
        self.content = content

class MockLLM:
    """
    Drop-in stand-in for a real ChatOpenAI/SGLang client.
    Same .invoke(prompt) -> object with .content interface,
    so agents.py never needs to change between mock and real.
    """
    def invoke(self, prompt: str) -> MockResponse:
        text = prompt.lower()
        if "transaction" in text and "compliance" in text:
            return MockResponse(
                "This transaction appears compliant with standard "
                "policy thresholds. No red flags detected.")
        return MockResponse("Analysis complete. No issues found.")
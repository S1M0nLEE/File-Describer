"""Summary generation: truncation + optional Ollama LLM."""

import httpx

from src.config import Config
from src.models.file_descriptor import FileDescriptor


class Summarizer:
  def __init__(self, config: Config):
    self.config = config

  def summarize(self, file_node: FileDescriptor) -> str:
    text = file_node.content_text or file_node.summary
    if not text and file_node.path:
      text = f"{file_node.name} ({file_node.extension})"

    if self.config.use_llm_summary and text.strip():
      ai = self._ollama_summarize(text)
      if ai:
        file_node.ai_summary = ai
        file_node.summary = ai[: self.config.summary_max_chars]
        return file_node.summary

    summary = text[: self.config.summary_max_chars]
    file_node.summary = summary
    return summary

  def _ollama_summarize(self, text: str) -> str:
    prompt = f"用一句话概括以下文件内容:\n\n{text[:2000]}"
    try:
      with httpx.Client(timeout=30.0) as client:
        resp = client.post(
          f"{self.config.ollama_base_url}/api/generate",
          json={"model": self.config.ollama_model, "prompt": prompt, "stream": False},
        )
        resp.raise_for_status()
        return resp.json().get("response", "").strip()
    except Exception:
      return ""

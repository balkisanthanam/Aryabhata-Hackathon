import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import google.generativeai as genai
from google.generativeai.types import GenerationConfig

CONFIG_PATH = Path(__file__).with_name("config.json")

def load_config(path: Path) -> Dict:
	with open(path, "r", encoding="utf-8") as f:
		return json.load(f)


def render_prompt(template_path: Path, variables: Dict) -> str:
	text = template_path.read_text(encoding="utf-8")
	# Simple placeholder replacement for {Curriculum}/{Standard}/{Subject} (and lowercase variants)
	mapping = {
		"Curriculum": str(variables.get("curriculum", "CBSE")),
		"Standard": str(variables.get("standard", 11)),
		"Subject": str(variables.get("subject", "Chemistry")),
		"curriculum": str(variables.get("curriculum", "CBSE")),
		"standard": str(variables.get("standard", 11)),
		"subject": str(variables.get("subject", "Chemistry")),
	}
	for k, v in mapping.items():
		text = text.replace("{" + k + "}", v)
	return text


def init_model(model_name: str, generation_config: Dict) -> genai.GenerativeModel:
	# It's recommended to load API keys from environment variables for security.
	# Make sure to set your GOOGLE_API_KEY environment variable.
	try:
		genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
	except KeyError:
		raise EnvironmentError("Error: GOOGLE_API_KEY environment variable not set.")

	return genai.GenerativeModel(
		model_name=model_name,
		generation_config=generation_config
	)


def call_gemini(model: genai.GenerativeModel, prompt: str, unit_uri: str, answer_uri: str, stream: bool = True, timeout: int = 600):
	parts = [
		prompt,
		genai.upload_file(unit_uri, mime_type="application/pdf"),
	]
	if answer_uri:
		parts.append(genai.upload_file(answer_uri, mime_type="application/pdf"))

	print(f"Generating content for {Path(unit_uri).name} (streaming: {stream})...")
	response = model.generate_content(
		contents=parts,
		stream=stream,
		request_options={'timeout': timeout}
	)

	full_response = ""
	for chunk in response:
		full_response += chunk.text
	return full_response


def save_output(base_dir: Path, input_uri: str, text: str) -> Path:
	base_dir.mkdir(parents=True, exist_ok=True)
	stem = Path(input_uri.rstrip("/").split("/")[-1]).stem
	ts = datetime.now().strftime("%Y%m%d_%H%M%S")
	out_path = base_dir / f"{stem}_{ts}.json"
	# Try to pretty-print JSON if valid
	try:
		parsed = json.loads(text)
		out_path.write_text(json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8")
	except Exception:
		out_path.write_text(text, encoding="utf-8")
	return out_path


def process_all(cfg: Dict) -> List[Path]:
	genai_cfg = cfg.get("genai", {})
	model_name = genai_cfg.get("model", "gemini-1.5-pro-latest") # Using 1.5 Pro as it's great for this
	generation_config = genai_cfg.get("generation_config", {"temperature": 0.1, "response_mime_type": "application/json"})
	request_options = genai_cfg.get("request_options", {"stream": True, "timeout": 600})

	model = init_model(model_name, generation_config)

	prompt_template_rel = cfg.get("prompt_template", "Prompts/QuestionAnswerExtraction_Chem.txt")
	prompt_path = Path(__file__).parent / prompt_template_rel
	prompt_text = render_prompt(prompt_path, cfg.get("variables", {}))

	inputs = cfg.get("inputs", {})
	unit_pdfs: List[str] = inputs.get("unit_pdfs", [])
	answer_pdf: str = inputs.get("answer_pdf", "")

	out_dir = Path(__file__).parent / cfg.get("output_dir", "output")

	outputs: List[Path] = []
	for unit_uri in unit_pdfs:
		text = call_gemini(model, prompt_text, unit_uri, answer_pdf, **request_options)
		out_path = save_output(out_dir, unit_uri, text)
		outputs.append(out_path)
	return outputs


def main():
	cfg_path = Path(os.environ.get("AB_EXTRACTION_CONFIG", CONFIG_PATH))
	if not cfg_path.exists():
		raise FileNotFoundError(f"Config not found: {cfg_path}")
	cfg = load_config(cfg_path)
	out_files = process_all(cfg)
	print("Saved:")
	for p in out_files:
		print(" -", p)


if __name__ == "__main__":
	main()

"""ローカルの因果言語モデル（transformers・CPU・貪欲デコード＝決定的）."""

from __future__ import annotations

from typing import Any

from dbr.shared.embed.offline import ONLINE_HINT, apply_offline_default
from dbr.shared.llm import LLMUnavailable


class LocalCausalLM:
    """chat template を持つ instruct モデル（Qwen2.5 系で実測）。"""

    def __init__(self, name: str, *, device: str = "cpu") -> None:
        self.name = name
        apply_offline_default()  # huggingface_hub の import 前
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as exc:  # pragma: no cover - 環境依存
            raise LLMUnavailable(f"transformers/torch 未導入: {exc}") from exc
        try:
            auto_model: Any = (
                AutoModelForCausalLM  # from_pretrained の型付けが厳しすぎる
            )
            self._tok: Any = AutoTokenizer.from_pretrained(name)
            self._model: Any = auto_model.from_pretrained(name, dtype=torch.float32).to(
                device
            )
        except Exception as exc:  # モデル未取得（オフライン）など
            raise LLMUnavailable(
                f"{name} を読み込めません: {exc}。{ONLINE_HINT}"
            ) from exc
        self._model.eval()
        self._torch = torch

    def generate(self, system: str, user: str, *, max_new_tokens: int = 400) -> str:
        msgs = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        text = self._tok.apply_chat_template(
            msgs, tokenize=False, add_generation_prompt=True
        )
        inp = self._tok(text, return_tensors="pt")
        with self._torch.no_grad():
            out = self._model.generate(
                **inp,
                max_new_tokens=max_new_tokens,
                do_sample=False,  # 貪欲＝同入力同出力
                pad_token_id=self._tok.eos_token_id,
            )
        gen = out[0][inp["input_ids"].shape[1] :]
        return str(self._tok.decode(gen, skip_special_tokens=True)).strip()

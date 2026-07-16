"""Thin seam around the LLM provider. Right now this matches scripted demo
rules so both chatbot prototypes work with zero API keys and zero network
risk during a live demo. Swapping to a real model later means only touching
generate_reply() — callers (chat_service) never change, and the scripted
rules/system prompts stay as useful few-shot context for the real model.

Future version (OpenRouter, free-tier model):
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.openrouter_api_key}"},
            json={
                "model": "meta-llama/llama-3.1-8b-instruct:free",
                "messages": [{"role": "system", "content": system_prompt}, *messages],
            },
        )
        return resp.json()["choices"][0]["message"]["content"]
"""


async def generate_reply(message: str, system_prompt: str, rules: list[tuple[tuple[str, ...], str]], default_reply: str) -> str:
    lowered = message.lower()
    for keywords, reply in rules:
        if any(k in lowered for k in keywords):
            return reply
    return default_reply

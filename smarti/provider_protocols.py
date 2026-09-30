"""Protocol adapters for endpoints not interchangeable with Chat Completions."""
from .api_errors import ApiRequestError, api_error_for_reason, analyze_api_error


def openai_responses_arguments(model, messages, reasoning="", tools=(), max_output_tokens=None):
    converted = []
    for message in messages:
        item = {"role": message.get("role", "user"), "content": message.get("content", "")}
        if isinstance(item["content"], list):
            content = []
            for block in item["content"]:
                if block.get("type") == "text":
                    content.append({"type": "input_text", "text": block.get("text", "")})
                elif block.get("type") == "image_url":
                    image = block.get("image_url") or {}
                    image = image if isinstance(image, dict) else {"url": image}
                    content.append({"type": "input_image", "image_url": image.get("url", ""), "detail": image.get("detail", "auto")})
                else:
                    raise ApiRequestError(api_error_for_reason("openai", model, "unsupported_modality", raw_message=f"Responses input block type={block.get('type', 'missing')}"))
            item["content"] = content
        converted.append(item)
    result = {"model": model, "input": converted, "store": False}
    if reasoning:
        result["reasoning"] = {"effort": reasoning}
    if max_output_tokens:
        result["max_output_tokens"] = max_output_tokens
    if tools:
        result["tools"] = [{"type": "function", "name": tool["name"], "description": tool["description"], "parameters": tool["parameters"], "strict": False} for tool in tools]
    return result


def openai_responses_result(response, model):
    data = response.model_dump() if callable(getattr(response, "model_dump", None)) else response
    if not isinstance(data, dict):
        raise ApiRequestError(api_error_for_reason("openai", model, "invalid_response", raw_message="Responses API did not return a structured object"))
    if data.get("error"):
        error = RuntimeError("Responses API failed")
        error.body = data
        error.request_id = getattr(response, "_request_id", "")
        raise ApiRequestError(analyze_api_error("openai", model, error=error))
    text, calls, refusal = [], [], False
    output = data.get("output") or []
    if not isinstance(output, list) or any(not isinstance(item, dict) for item in output):
        raise ApiRequestError(api_error_for_reason("openai", model, "invalid_response", raw_message="Responses output must be a list of objects"))
    for item in output:
        if item.get("type") == "function_call":
            calls.append({"name": item.get("name", ""), "arguments": item.get("arguments", ""), "provider_call_id": item.get("call_id", "")})
        elif item.get("type") == "message":
            content = item.get("content") or []
            if not isinstance(content, list) or any(not isinstance(block, dict) for block in content):
                raise ApiRequestError(api_error_for_reason("openai", model, "invalid_response", raw_message="Responses message content must be a list of objects"))
            for block in content:
                if block.get("type") == "output_text":
                    if not isinstance(block.get("text"), str):
                        raise ApiRequestError(api_error_for_reason("openai", model, "invalid_response", raw_message="Responses output text must be a string"))
                    text.append(block.get("text", ""))
                elif block.get("type") == "refusal":
                    refusal = True
    usage = data.get("usage") or {}
    result_usage = {
        "prompt": int(usage.get("input_tokens", 0) or 0),
        "completion": int(usage.get("output_tokens", 0) or 0),
        "total": int(usage.get("total_tokens", 0) or 0),
        "cached_prompt": int((usage.get("input_tokens_details") or {}).get("cached_tokens", 0) or 0),
        "reasoning": int((usage.get("output_tokens_details") or {}).get("reasoning_tokens", 0) or 0),
    }
    finish = ""
    if data.get("status") == "incomplete":
        finish = "length" if (data.get("incomplete_details") or {}).get("reason") == "max_output_tokens" else "content_filter" if (data.get("incomplete_details") or {}).get("reason") == "content_filter" else "OTHER"
    elif data.get("status") != "completed":
        finish = "OTHER"
    return "\n".join(text).strip(), calls, result_usage, finish, "refusal" if refusal else ""

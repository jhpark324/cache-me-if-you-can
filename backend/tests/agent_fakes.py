"""Deterministic provider doubles that exercise the real create_agent graph."""
from __future__ import annotations

import json
from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage


def request_value(messages):
    return json.loads(next(message.content for message in messages if isinstance(message, HumanMessage)))


def tool_values(messages):
    values = []
    for message in messages:
        if isinstance(message, ToolMessage):
            try:
                value = json.loads(message.content)
            except (ValueError, TypeError):
                continue
            if isinstance(value, dict):
                values.append(value)
    return values


def search_call(query, unit_ids=None, **extra):
    return {'id': f'call_{uuid4().hex}', 'name': 'search_knowledge',
            'args': {'query': query, 'unit_ids': unit_ids or [], **extra}, 'type': 'tool_call'}


def final_message(messages, *, text=None):
    evidence = {item['evidence_id']: item for value in tool_values(messages)
                for item in value.get('evidence', [])}
    return AIMessage(content=json.dumps({'parts': [{
        'kind': 'stored_knowledge' if evidence else 'general_explanation',
        'text': text or ('선택된 근거에서 확인한 내용입니다.' if evidence else '확인할 개인 기록이 없습니다.'),
        'evidence_ids': [next(iter(evidence))] if evidence else [],
    }], 'evidence_status': 'found' if evidence else 'none'}, ensure_ascii=False))


class OfflineModel:
    def __init__(self, *, window=32_000, max_output=1024, first_calls=None, final_text=None):
        self.window, self.max_output = window, max_output
        self.model = 'selected-test-model'
        self.first_calls, self.final_text = first_calls, final_text
        self.calls = []
        self.agent_calls = []
        self.expected_models = []
        self.switch_during_answer = False

    async def model_metadata(self):
        return {'model': self.model, 'context_window': self.window,
                'max_output_tokens': self.max_output, 'source': 'catalog'}

    async def generate_message(self, messages, instructions, *, tools=None, expected_model=None):
        self.expected_models.append(expected_model)
        self.agent_calls.append({'messages': messages, 'instructions': instructions, 'tools': tools})
        if not any(isinstance(message, ToolMessage) for message in messages):
            value = request_value(messages)
            if self.first_calls is not None:
                calls = self.first_calls(value) if callable(self.first_calls) else self.first_calls
            else:
                units = value['source_units']
                selected = units if len(units) <= 8 else units[:7] + units[-1:]
                calls = [search_call(unit['query'], [unit['unit_id']]) for unit in selected]
            return AIMessage(content='', tool_calls=calls) if calls else final_message(messages, text=self.final_text)
        if self.switch_during_answer:
            self.model = 'new-user-selection'
        return final_message(messages, text=self.final_text)

    async def generate(self, prompt, instructions):
        value = json.loads(prompt)
        self.calls.append((value, instructions))
        return json.dumps({'supported_part_ids': [part['part_id'] for part in value['parts']]})

    async def generate_for_model(self, prompt, instructions, expected_model):
        self.expected_models.append(expected_model)
        return await self.generate(prompt, instructions)

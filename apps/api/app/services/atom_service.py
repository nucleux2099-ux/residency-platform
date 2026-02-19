import json
import logging
import os
from typing import AsyncGenerator

from anthropic import AsyncAnthropic
from pydantic import BaseModel

logger = logging.getLogger(__name__)

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    patient_context: dict | None = None
    stream: bool = True

class AtomService:
    def __init__(self):
        # User selected Anthropic
        api_key = os.getenv("ATOM_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
        
        self.client = None
        self.model = os.getenv("ATOM_MODEL", "claude-3-5-sonnet-20240620")
        
        if api_key:
            self.client = AsyncAnthropic(api_key=api_key)
        else:
            logger.warning("AtomService initialized without ANTHROPIC_API_KEY. Chat will fail.")

    async def stream_chat(self, request: ChatRequest) -> AsyncGenerator[str, None]:
        if not self.client:
            yield "data: Error: No AI provider configured. Please set ANTHROPIC_API_KEY.\n\n"
            return

        # 1. Build System Prompt with Context
        system_prompt = self._build_system_prompt(request.patient_context)
        
        # Anthropic handles system prompt separately from messages list
        # We need to filter out any system messages from the request.messages
        # Also Anthropic expects alternating user/assistant roles, starting with user.
        # Ideally the frontend handles this, but we should be robust.
        
        user_messages = [
            {"role": m.role, "content": m.content} 
            for m in request.messages 
            if m.role != "system"
        ]

        # 2. Add PubMed Tool Definition
        tools = [
            {
                "name": "search_pubmed",
                "description": "Search for medical literature and papers on PubMed. Use this when the user asks for research, papers, or evidence.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The search query for PubMed (e.g., 'SVT management guidelines')"
                        }
                    },
                    "required": ["query"]
                }
            }
        ]

        try:
            # We use a loop to handle tool use:
            # 1. Helper sends user message -> AI decides to use tool -> We run tool -> We send result -> AI answers.
            
            # Initial call
            response = await self.client.messages.create(
                max_tokens=1024,
                messages=user_messages,
                system=system_prompt,
                model=self.model,
                temperature=0.3,
                tools=tools
            )

            # Check if it wants to use a tool
            if response.stop_reason == "tool_use":
                # Handle tool use (non-streaming first to get the tool block)
                tool_use_block = next(b for b in response.content if b.type == "tool_use")
                tool_name = tool_use_block.name
                tool_inputs = tool_use_block.input
                
                if tool_name == "search_pubmed":
                    # Run the tool
                    yield f"data: 🔍 Searching PubMed for '{tool_inputs['query']}'...\n\n"
                    from app.services.pubmed_service import search_pubmed
                    results = search_pubmed(tool_inputs["query"])
                    
                    # Format results for the AI
                    tool_result_content = json.dumps(results, indent=2)
                    
                    # Append exchange to history
                    user_messages.append({"role": "assistant", "content": response.content})
                    user_messages.append({
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": tool_use_block.id,
                                "content": tool_result_content
                            }
                        ]
                    })
                    
                    # Follow-up call with tool results (Streaming)
                    async with self.client.messages.stream(
                        max_tokens=1024,
                        messages=user_messages,
                        system=system_prompt,
                        model=self.model,
                        temperature=0.3,
                        tools=tools
                    ) as stream:
                        async for text in stream.text_stream:
                            yield text
            else:
                # No tool use, just stream the text content
                # Since we used .create() above, we need to yield the text from that response manually
                # Or re-run as stream if we want consistent behavior, but that costs double.
                # Optimization: For the initial call, we could use stream=True and robustly parse tool_use chunks,
                # but Anthropic tool streaming is complex.
                # Safest approach for MVP: If not tool use, just yield the text block.
                
                for block in response.content:
                    if block.type == "text":
                        yield block.text

        except Exception as e:
            logger.error(f"Error in chat stream: {e}")
            yield f"Error: {str(e)}"

    def _build_system_prompt(self, context: dict | None) -> str:
        prompt = [
            "You are ATOM, an intelligent clinical assistant for the Residency Platform.",
            "You are helpful, precise, and concise.",
            "Always maintain patient privacy. Do not invent medical facts.",
        ]

        if context:
            prompt.append("\n=== CURRENT PATIENT CONTEXT ===")
            prompt.append(json.dumps(context, indent=2, default=str))
            prompt.append("==============================")
            prompt.append("Use the above context to answer questions about this patient.")
        
        return "\n".join(prompt)

atom_service = AtomService()

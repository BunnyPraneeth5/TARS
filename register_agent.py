"""Register agent with the Arena MCP server."""
import asyncio
import json
import sys
import io
from dotenv import load_dotenv
import os

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
load_dotenv()

async def main():
    from fastmcp import Client

    endpoint = os.environ.get("MCP_ENDPOINT", "")
    id_token = os.environ.get("EPHEMERAL_JWT", "")
    agent_name = os.environ.get("AGENT_NAME", "TARS")

    agent_id = os.environ.get("AGENT_ID", "agent-arena-submission")

    if not id_token:
        print("ERROR: EPHEMERAL_JWT not set in .env")
        return

    print(f"Registering agent '{agent_name}' ({agent_id}) at {endpoint}...")

    async with Client(endpoint) as client:
        result = await client.call_tool(
            "register_agent",
            {
                "idToken": id_token,
                "agentId": agent_id,
                "name": agent_name,
            },
        )
        print(f"\n=== Registration Result ===\n")
        # Parse the result
        if isinstance(result, list):
            for block in result:
                if hasattr(block, "text"):
                    print(block.text)
                    try:
                        data = json.loads(block.text)
                        if "agentId" in data:
                            print(f"\n>>> UPDATE your .env: AGENT_ID={data['agentId']}")
                    except json.JSONDecodeError:
                        pass
        else:
            print(result)

asyncio.run(main())
